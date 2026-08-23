#!/usr/bin/env python3
"""ASP: Access-Structured Perception (paper Sec. 4).

Training-free wrapper around a frozen backbone behind an OpenAI-compatible endpoint
(local vLLM = primary arm, OpenRouter = replication arm; set ASP_API_URL to switch).
Components map 1:1 to the paper:
  KeyframeGate      -> Sec 4.1  (SigLIP-class embedding novelty gate)
  SceneState  (C_s) -> Sec 4.2  (structured O(1)-token state, LRU eviction)
  EpisodicIndex(C_v)-> Sec 4.3  (verbatim keyframes + captions + embeddings)
  Router (rho)      -> Sec 4.4  (query classification + budget water-filling)
  access_loop       -> Sec 4.4  (<= R rounds of RETRIEVE/STATE/ANSWER)

Offline embedding model runs locally (sentence-transformers CLIP/SigLIP);
only backbone calls are debited from the budget, matching Def. 2.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field

import numpy as np

# Thread cap, before torch is imported. The grid runs ~24 of these processes at once and
# torch defaults to one thread per core, so 24 x 256 threads fought over 256 cores: load
# average hit 1,400 and the CLIP pass that should take seconds took minutes. The embedder
# is the only local compute here and it is disk-cached, so a small cap costs nothing.
import os as _os0
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    _os0.environ.setdefault(_v, "4")

# device="cpu" is deliberate and must stay. Every backbone call goes to the OpenRouter API;
# the only local computation is this embedder. sentence-transformers grabs CUDA whenever it
# is visible, which would put an unscheduled process on a shared accelerator -- on this
# host GPU work goes through slurm. The embedder is CLIP-ViT-B/32 over a few thousand
# frames, which is seconds of CPU per episode and is cached to disk besides.
try:
    from PIL import Image
    from sentence_transformers import SentenceTransformer
    _EMB = SentenceTransformer("clip-ViT-B-32", device="cpu")
    import torch as _torch
    _torch.set_num_threads(int(_os0.environ.get("OMP_NUM_THREADS", "4")))
except Exception:  # allow import on machines without the package
    _EMB = None
    Image = None

# CRITICAL: sentence-transformers' CLIP encodes a list of *strings* as TEXT. Passing
# frame PATHS therefore embedded filenames, not pixels -- the keyframe gate was
# comparing "frame_0001.jpg" to "frame_0002.jpg" and the episodic index was matching
# natural-language queries against path strings. Both silently produced plausible
# numbers. Images must be opened and handed to encode() as PIL objects.
_IMG_CACHE: dict = {}

# Frame embeddings are pure local computation with no API cost, but the grid re-embeds
# the same episode once per (method, subset) cell -- 1,200 CLIP forward passes x 40-odd
# cells, all identical. One npz per frame directory makes that a one-off.
import hashlib as _hashlib
import os as _os
import pathlib as _pathlib

_EMB_DIR = _pathlib.Path(_os.environ.get(
    "ASP_EMB_CACHE",
    str(_pathlib.Path(__file__).resolve().parents[2] / "results/cache/emb")))
_LOADED_DIRS: set = set()


def _dir_file(d: str) -> _pathlib.Path:
    return _EMB_DIR / (_hashlib.md5(d.encode()).hexdigest() + ".npz")


def _warm(paths: list[str]):
    for d in {_os.path.dirname(p) for p in paths}:
        if d in _LOADED_DIRS:
            continue
        _LOADED_DIRS.add(d)
        f = _dir_file(d)
        if f.exists():
            try:
                z = np.load(f)
                for k in z.files:
                    _IMG_CACHE[_os.path.join(d, k)] = z[k]
            except Exception:
                pass          # a truncated cache is a cache miss, never a failure


_DIRTY: set = set()


def _persist(force: bool = False):
    """Write the per-directory npz. Called with force=False after each batch, so it is a
    no-op until enough new vectors have accumulated: rewriting a 300-entry archive once
    per single-image add turned the offline phase into an O(N^2) disk workload."""
    if not _DIRTY or (not force and len(_IMG_CACHE) % 64):
        return
    _EMB_DIR.mkdir(parents=True, exist_ok=True)
    for d in list(_DIRTY):
        entries = {_os.path.basename(k): v for k, v in _IMG_CACHE.items()
                   if _os.path.dirname(k) == d}
        if entries:
            np.savez(_dir_file(d), **entries)
    _DIRTY.clear()


import atexit as _atexit
_atexit.register(lambda: _persist(force=True))


def embed_images(paths: list[str], batch: int = 32) -> np.ndarray:
    """Visual embeddings for frame paths. Cached in-process and on disk."""
    _warm(paths)
    todo = [p for p in paths if p not in _IMG_CACHE]
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        imgs = [Image.open(p).convert("RGB") for p in chunk]
        vecs = _EMB.encode(imgs, convert_to_numpy=True, normalize_embeddings=True,
                           batch_size=batch)
        for p, v in zip(chunk, vecs):
            _IMG_CACHE[p] = v
        for im in imgs:
            im.close()
    if todo:
        _DIRTY.update(_os.path.dirname(p) for p in todo)
        _persist()
    return np.stack([_IMG_CACHE[p] for p in paths])


def embed_text(texts: list[str]) -> np.ndarray:
    """Text embeddings in the SAME CLIP space, for query-conditioned retrieval."""
    return _EMB.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

from openrouter_client import BudgetedSession, BudgetExhausted

# ---------------- keyframe gate (Sec 4.1) ----------------

def keyframe_gate(frame_paths: list[str], tau_g: float = 0.18) -> list[int]:
    """Novelty gate. tau_g <= 0 means "the input is ALREADY keyframes" -- identity.

    The gate exists to thin a sensor-rate video stream. Applying it to a corpus that
    already emits one frame per discrete moment thins it twice and destroys the very
    condition the walls need: on the synthetic corpus tau_g=0.02 collapsed 300 frames to
    29, giving N/w = 1.9 and a horizon-wall ceiling of 0.58 -- so uniform sampling would
    see most of the stream and Theorem 2 would say almost nothing. tau_g is a per-corpus
    calibration (Sec 5.1) and 0 is the correct setting for a pre-keyframed corpus.
    """
    if tau_g <= 0:
        return list(range(len(frame_paths)))
    embs = embed_images(frame_paths)
    keep, last = [0], embs[0]
    for i in range(1, len(embs)):
        if 1 - float(np.dot(embs[i], last)) > tau_g:
            keep.append(i)
            last = embs[i]
    return keep

# ---------------- compressive channel C_s (Sec 4.2) ----------------

# Caption schema version. It is part of the offline cache key, so a change here can never
# silently mix two caption regimes inside one episode's index.
#
# v2 exists because v1 was measured to break Assumption 1(ii). A v1 caption was a free-form
# one-liner, and with 16 objects in a frame the model named only a handful of them: the
# RET target's class was absent from its OWN frame's caption in 24 of 28 misses, so BM25
# had nothing to match and retrieval recall@8 was 0.06-0.12 (delta_r ~ 0.9,
# analysis/retrieval_recall.py). That is an index failure, not an access-structure result:
# it would have pinned ASP and Retr-only at chance on RET for a reason the theory
# explicitly assumes away. v2 asks for the object-class INVENTORY, which is what a
# retrieval index needs from a caption. It does not leak an answer -- the queried
# attributes (colour, printed letter tag) stay in the pixels, and the caption's job is only to
# make the right frame findable. The same captions are used by every method that reads
# C_v, so no method gains from the change relative to another.
OFFLINE_VERSION = 3
CAPTION_REQUEST = ("CAPTION: <the room, the door state, then a comma-separated list of "
                   "EVERY object class name visible in this frame. Names only -- do NOT "
                   "state their colours or their printed letters.>")

# v3 also changes the STATE schema, for a reason that is a bug rather than a design choice.
# Sec 4.2 says C_s holds "the running reductions retrieval cannot cheaply rebuild", and
# _evict() already protects "counter-bearing entries" -- but nothing ever created one,
# because the update prompt only asked the model to "add/merge objects". Inspecting the v2
# states confirmed it: every backbone stored the CURRENT frame's objects and no cumulative
# quantity at all. A state like that cannot answer a TRK question in principle, so
# State-only would have failed on TRK for an implementation reason and the channel-duality
# contrast of Lemma 3 would have been untestable.
#
# The schema below names GENERIC reductions -- a cumulative count per observed class, a
# binary environment state with its change count, an ordered room trace -- not the specific
# quantities the questions ask about. Insertion order is load-bearing: the state is fed back
# truncated to L_s tokens, so the reductions are serialised FIRST and the truncation eats
# the per-object detail rather than the counters. That is the same priority _evict() already
# encoded.
STATE_SCHEMA = {"counts": {}, "env": {"door": "unknown", "door_changes": 0},
                "rooms_visited": [], "objects": {}, "event_log": []}
UPDATE_PROMPT = """You maintain a compact JSON scene state for an embodied agent. It is your
ONLY memory of the stream: you will never see this frame again, so anything not written down
is lost.
Current state (may be truncated): {state}
Given the new keyframe image, output the updated JSON with these fields:
 "counts": cumulative sightings per object class. For EVERY object class visible in this
   frame, increment its entry by 1 (create it at 1 if absent). NEVER reset or recount --
   these are totals over the whole stream so far.
 "env": the observable binary environment state. Set "door" to its current value, and
   increment "door_changes" by 1 if and only if it differs from the value in the state above.
 "rooms_visited": ordered list of rooms. Append the current room only if it differs from the
   last entry.
 "objects": the classes visible now, each with room and last_seen={t}.
 "event_log": append at most one short string if something changed.
Output the updated JSON, then the caption line."""


@dataclass
class SceneState:
    max_tokens: int = 512          # L_s
    state: dict = field(default_factory=lambda: json.loads(json.dumps(STATE_SCHEMA)))

    def update(self, sess: BudgetedSession, frame: str, t: int) -> str:
        """One bounded backbone call; also returns a one-line caption for C_v."""
        prompt = UPDATE_PROMPT.format(state=json.dumps(self.state)[: self.max_tokens * 4], t=t)
        prompt += "\nThen, on the LAST line only, output " + CAPTION_REQUEST
        out = sess.chat(prompt, images=[frame], max_completion=self.max_tokens + 128,
                        tag="state_update")
        cap = ""
        m = re.search(r"CAPTION:(.*)$", out, re.S)
        if m:
            # A model that emits the CAPTION marker and then nothing must not take the
            # whole episode down: splitlines() on "" is empty, so [0] raised IndexError
            # and killed the offline job at whichever keyframe it first happened.
            lines = m.group(1).strip().splitlines()
            cap = lines[0] if lines else ""
            out = out[: m.start()]
        try:
            self.state = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
        except Exception:
            pass  # keep previous state on parse failure (logged upstream)
        self._evict(t)
        self._reorder()
        return cap

    def _evict(self, t: int, keep: int = 24):
        """LRU over per-object detail only. `counts`, `env` and `rooms_visited` are the
        running reductions of Sec 4.2 and are never evicted -- evicting them would throw
        away precisely the information no per-decision retrieval budget can rebuild."""
        objs = self.state.get("objects", {})
        if isinstance(objs, dict) and len(objs) > keep:
            ranked = sorted(objs.items(),
                            key=lambda kv: (kv[1].get("last_seen", 0)
                                            if isinstance(kv[1], dict) else 0))
            for k, _v in ranked[: len(objs) - keep]:
                objs.pop(k, None)
        self.state["event_log"] = self.state.get("event_log", [])[-20:]

    def _reorder(self):
        """Serialise the reductions first, so the L_s truncation that feeds the state back
        in cuts per-object detail instead of the counters."""
        order = ["counts", "env", "rooms_visited", "objects", "event_log"]
        self.state = {k: self.state[k] for k in order if k in self.state} | \
                     {k: v for k, v in self.state.items() if k not in order}

    def render(self, max_chars: int = 2048) -> str:
        return json.dumps(self.state)[:max_chars]

# ---------------- verbatim channel C_v (Sec 4.3) ----------------

@dataclass
class EpisodicIndex:
    alpha: float = 0.6
    frames: list[str] = field(default_factory=list)
    captions: list[str] = field(default_factory=list)
    embs: list[np.ndarray] = field(default_factory=list)

    def add(self, frame: str, caption: str):
        self.frames.append(frame)
        self.captions.append(caption)
        self.embs.append(embed_images([frame])[0])       # PIXELS, not the path string

    @staticmethod
    def _tok(text: str) -> list[str]:
        """Tokenise on non-alphanumerics, NOT on whitespace.

        This is not a detail. The v2 captions are comma-separated class inventories, and the
        backbones emit them with inconsistent spacing -- "belt, ruler, soap" from one call and
        "belt,ruler,soap" from the next. Under str.split() the first form yields the tokens
        "belt," and "ruler," (which never match the query term "belt") and the second yields
        ONE seventeen-class token (which matches nothing at all). Measured effect: recall@8 on
        the RET targets was 0.00-0.22 with a median target rank of 121 out of 300, while the
        target class name WAS present in its own caption in 29 of 29 checked misses -- the text
        was right and the tokeniser threw it away. Every RET and CMP number produced before
        this fix was an index artefact, not an access-structure result."""
        return re.findall(r"[a-z0-9]+", text.lower())

    def _bm25(self, query: str) -> np.ndarray:
        """Okapi BM25 over captions, as Sec. 4.3 states. The previous code was a
        Jaccard-style overlap ratio, which has no IDF term and so could not do the
        one job the paper assigns this component: disambiguating near-duplicate
        frames of the same room by their rare words ("the SECOND white mug")."""
        k1, b = 1.5, 0.75
        docs = [self._tok(c) for c in self.captions]
        n = len(docs) or 1
        avgdl = (sum(len(d) for d in docs) / n) or 1.0
        df: dict = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        out = np.zeros(n)
        for i, d in enumerate(docs):
            dl, tf = len(d), {}
            for t in d:
                tf[t] = tf.get(t, 0) + 1
            sc = 0.0
            for t in set(self._tok(query)):
                if t not in tf:
                    continue
                idf = np.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                sc += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
            out[i] = sc
        m = out.max()
        return out / m if m > 0 else out          # scale-match the cosine term

    def retrieve_random(self, k: int = 8, seed: int = 0) -> list[int]:
        """Query-independent control for Table 3: same k frames, no query conditioning.
        Deterministic per index size so the ablation is reproducible."""
        import random as _r
        rng = _r.Random(seed * 1000 + len(self.frames))
        return rng.sample(range(len(self.frames)), min(k, len(self.frames)))

    def retrieve(self, query: str, k: int = 8) -> list[int]:
        if not self.frames:
            return []
        q = embed_text([query])[0]
        vis = np.array(self.embs) @ q
        score = self.alpha * vis + (1 - self.alpha) * self._bm25(query)
        return [int(i) for i in np.argsort(-score)[:k]]

# ---------------- router rho + access loop (Sec 4.4, Table 1) ----------------

ALLOC = {  # fractions of (B - B_rho); Table 1 of the paper
    "RET": (0.10, 0.65, 0.25),
    "TRK": (0.55, 0.10, 0.35),
    "CMP": (0.25, 0.35, 0.40),
    "NOW": (0.05, 0.20, 0.75),
}
CLS_PROMPT = """Classify the query for an embodied agent into exactly one class:
RET (asks a visual detail of a specific past moment/object),
TRK (asks a cumulative quantity or final state: counts, open/closed, containment),
CMP (requires chaining multiple dependent spatial/temporal references),
NOW (about the current view only).
Query: {q}
Scene-state summary: {s}
Answer with the class name only."""

def _last_action(out: str) -> str:
    """Pull the agent's action out of a completion.

    Two failure modes this exists for, both observed. (1) Models wrap the action in
    markdown -- "**STATE: objects**" -- so a bare startswith() match fails, the action
    falls through to the NOTE branch, and the access loop silently stops working for that
    backbone. (2) Models add a trailing blank line or a sign-off, so the LAST line is not
    the action. So: strip emphasis, and scan upward for the first line that is one.
    """
    verbs = ("ANSWER:", "RETRIEVE:", "STATE:")
    for raw in reversed((out or "").strip().splitlines()):
        ln = raw.strip().strip("*`_ ").lstrip("-> ").strip()
        up = ln.upper()
        for v in verbs:
            if up.startswith(v):
                return v + ln[len(v):]
    return (out or "").strip().splitlines()[-1] if (out or "").strip() else ""


LOOP_PROMPT = """You are an embodied QA agent with a token budget. You may act in rounds.
Available actions (output exactly one per round):
RETRIEVE: <rewritten visual search query>   -- fetches top matching past keyframes
STATE: <field or 'all'>                     -- reads the compressed scene state
ANSWER: <final answer>
Question: {q}
{context}
Round {r}/{R}. Think briefly, then output one action on the last line."""


def run_asp(sess: BudgetedSession, index: EpisodicIndex, state: SceneState,
            question: str, R: int = 3, k: int = 8, use_cs: bool = True,
            use_cv: bool = True, use_router: bool = True,
            random_retr: bool = False) -> dict:
    """The four keyword flags are the Table 3 ablations, run through the SAME loop as
    the full method so a collapse is attributable to the removed component and not to a
    different code path:
      use_cs=False    -> -C_s   : STATE actions return nothing
      use_cv=False    -> -C_v   : RETRIEVE actions return nothing
      use_router=False-> -rho   : fixed 1/3 split, and no classification call is paid for
      random_retr     -> retrieval ignores the query (control for "is retrieval doing work")
      R=1 / R=5       -> the round-wall ablation
    """
    trace = {"question": question}
    if use_router:
        z = sess.chat(CLS_PROMPT.format(q=question, s=state.render(300)),
                      max_completion=48, tag="router_cls").strip().upper()
        z = z if z in ALLOC else "CMP"
        fs, fr, fc = ALLOC[z]
    else:
        z, (fs, fr, fc) = "FIXED", (1 / 3, 1 / 3, 1 / 3)
    B = sess.remaining()
    Bs, Br, Bc = int(B * fs), int(B * fr), int(B * fc)
    trace.update(cls=z, Bs=Bs, Br=Br, Bc=Bc)

    # Per-channel caps. Previously Bs/Br/Bc were computed and then never enforced:
    # only the TOTAL was tracked, so the water-filling of Sec 4.4 had no effect on
    # behaviour and App. D's registered claim about the realised split was untestable.
    cap = {"Bs": Bs, "Br": Br, "Bc": Bc}

    def afford(ch: str, need: int) -> bool:
        return sess.by_channel[ch] + need <= cap[ch] and sess.remaining() > need

    context, answer = "", None
    for r in range(1, R + 1):
        per_round = max(64, Bc // R)
        if not afford("Bc", per_round):
            break
        try:
            out = sess.chat(LOOP_PROMPT.format(q=question, context=context, r=r, R=R),
                            max_completion=per_round, tag=f"round{r}")
        except BudgetExhausted:
            break
        act = _last_action(out)
        if act.startswith("ANSWER:"):
            answer = act[len("ANSWER:"):].strip()
            break
        if act.startswith("STATE:"):
            if not use_cs:
                context += "\n[NO SCENE STATE AVAILABLE]"
                continue
            left = max(0, cap["Bs"] - sess.by_channel["Bs"])
            if left <= 0:
                context += "\n[STATE BUDGET EXHAUSTED]"
            else:
                # Charge B_s for the tokens the state read ACTUALLY inserts, which is what
                # Sec. 5.6 says this accounting is. Charging the whole remaining cap -- what
                # this did -- had two consequences, both wrong. (1) The first STATE action
                # exhausted B_s outright, so every later round got "[STATE BUDGET EXHAUSTED]"
                # however small the state was; the access loop could therefore read the state
                # at most ONCE per decision, while the worked item of App. B.3 reads it in
                # round 1 and again in round 3, which is exactly the pattern a CMP chain
                # needs. (2) The realised split reported in Sec. 5.6 was dominated by a
                # synthetic number: measured on asp_r1/TRK, the ledger attributed 68.6% to
                # B_s on a decision that spent 963 tokens in total.
                txt = state.render(left * 4)
                context += f"\n[SCENE STATE]\n{txt}"
                sess.by_channel["Bs"] += sess._est_text_tokens(txt)
        elif act.startswith("RETRIEVE:"):
            if not use_cv:
                context += "\n[NO EPISODIC INDEX AVAILABLE]"
                continue
            q2 = act[len("RETRIEVE:"):].strip()
            ids = index.retrieve_random(k=k) if random_retr else index.retrieve(q2, k=k)
            # how many frames the RETRIEVAL channel can still afford, at the
            # calibrated per-image cost rather than a hardcoded 400
            n_aff = max(0, (cap["Br"] - sess.by_channel["Br"]) // max(1, sess.img_tokens))
            # also clamp to the provider's images-per-request limit (8 on the Mistral
            # endpoints); unlike Uniform-w this costs Asp nothing, because a round that
            # wants more frames can ask for them in the NEXT round -- which is the whole
            # point of Thm 4 and is why the cap is a constraint on width, not on depth.
            imgs = [index.frames[i] for i in ids][: int(min(n_aff, sess.img_cap))]
            if not imgs:
                context += "\n[RETRIEVAL BUDGET EXHAUSTED]"
            else:
                try:
                    desc = sess.chat(
                        f"Question: {question}\nDescribe ONLY facts relevant to it in these frames.",
                        images=imgs, max_completion=200, tag=f"read_retr_r{r}")
                except BudgetExhausted:
                    break
                context += f"\n[RETRIEVED for '{q2}']\n{desc}"
        else:
            context += f"\n[NOTE]\n{out[-400:]}"
    if answer is None:
        # Forced best guess at exhaustion (Sec 4.4). Returning the last line of the
        # scratch context instead -- which is what this did -- hands the scorer a
        # bracketed note like "[RETRIEVED for ...]" and records it as the model's answer.
        # Spend one small call on an actual answer when anything is left, and fall back to
        # the last line that is not internal bookkeeping only if nothing is.
        try:
            if sess.remaining() > 96:
                answer = sess.chat(
                    f"Question: {question}\n{context}\n"
                    f"Give ONLY the final short answer, no explanation.",
                    max_completion=48, tag="forced_answer").strip()
        except BudgetExhausted:
            answer = None
        if not answer:
            lines = [ln for ln in context.strip().splitlines()
                     if ln.strip() and not ln.lstrip().startswith("[")]
            answer = lines[-1] if lines else "unknown"
    trace.update(answer=answer, spent=sess.spent, calls=sess.calls,
                 realised_split=sess.split(), rounds_used=r,
                 ablation=dict(R=R, use_cs=use_cs, use_cv=use_cv,
                               use_router=use_router, random_retr=random_retr))
    return trace
