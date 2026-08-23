#!/usr/bin/env python3
"""Equal-budget baselines of Table 2. Each consumes the SAME BudgetedSession
and the SAME keyframe set as ASP; only the access structure differs.

blind      : question only (floor)
uniform16  : w uniformly spaced keyframes in one pass (horizon-wall witness)
socratic   : per-frame captions (precomputed by the same backbone under the
             per-keyframe update allowance) + text-only QA
retr_only  : C_v without C_s (VideoAgent-style)
state_only : C_s without C_v (MovieChat/MA-LMM-style)
"""
from __future__ import annotations
import numpy as np

from openrouter_client import BudgetedSession, BudgetExhausted
from methods.asp import EpisodicIndex, SceneState, LOOP_PROMPT


def blind(sess: BudgetedSession, question: str) -> str:
    return sess.chat(f"Answer concisely: {question}", max_completion=64, tag="blind")


def uniform(sess: BudgetedSession, keyframes: list[str], question: str,
            w: int | None = None, max_completion: int = 128) -> str:
    """Uniform-w. w SHRINKS to whatever actually fits B, and the realised value is logged.

    Equal-budget means equal TOKENS, not equal frames. At the paper's own stated
    230-280 tokens/frame, w=16 needs 3.9k-4.7k tokens for the images alone, so at
    B=4096 it fits only at the bottom of that range -- for a backbone at 280 it
    overruns by ~570 before the prompt or the answer is counted. Silently sending 16
    anyway is what made this an unequal-budget comparison; refusing outright would
    drop the cell. So we send the largest w the budget affords and record it, which
    keeps the comparison honest and makes the shortfall a measured quantity.
    """
    prompt = (f"These frames are uniformly sampled from an egocentric walkthrough, in order. "
              f"Answer concisely: {question}")
    afford = (sess.remaining() - sess._est_text_tokens(prompt) - max_completion) // sess.img_tokens
    ceiling = len(keyframes) if w is None else min(w, len(keyframes))
    w_real = int(max(0, min(ceiling, afford, sess.img_cap)))
    w = ceiling if w is None else w
    # WHICH limit bound is a load-bearing fact, not a diagnostic. On the Mistral backbones the
    # provider refuses more than eight images per request, so at the 16k budget of the P3
    # reallocation-versus-growth test the "growth" arm cannot actually buy more frames -- and a
    # P3 result on those backbones would then be true for a provider reason rather than for the
    # reason P3 is testing. Recorded here so analysis can exclude those cells by name.
    limited_by = ("request" if w_real == ceiling else
                  "provider" if sess.img_cap <= afford else "budget")
    sess.calls.append({"tag": "uniform_plan", "tokens": 0, "channel": "Br",
                       "w_requested": w, "w_realised": w_real,
                       "w_limited_by": limited_by,
                       "img_cap": sess.img_cap, "afford": int(afford),
                       "img_tokens": sess.img_tokens})
    if w_real == 0:
        raise BudgetExhausted(
            f"Uniform-{w} cannot fit B={sess.budget} at {sess.img_tokens} tokens/frame")
    ids = np.linspace(0, len(keyframes) - 1, num=w_real, dtype=int)
    return sess.chat(prompt, images=[keyframes[i] for i in ids],
                     max_completion=max_completion, tag="uniform")


def socratic(sess: BudgetedSession, captions: list[str], question: str,
             max_completion: int = 128) -> str:
    """Socratic: per-keyframe captions as text, then text-only QA.

    How much caption text fits is derived from B rather than from a hardcoded 8,000
    characters. That number silently gave this baseline whatever the constant happened to
    allow -- sometimes more than B, sometimes far less -- and the whole point of the
    comparison is that every method spends the SAME budget. The captions kept are the most
    recent ones that fit, and the count is logged, because the resulting horizon limit is
    a measured quantity here, not an implementation detail."""
    head = "Per-keyframe captions of a walkthrough:\n"
    tail = f"\n\nAnswer concisely: {question}"
    room = (sess.remaining() - max_completion
            - sess._est_text_tokens(head + tail)) * 4      # ~4 chars per token
    lines = [f"[t={i}] {c}" for i, c in enumerate(captions)]
    kept, used = [], 0
    for ln in reversed(lines):
        if used + len(ln) + 1 > room:
            break
        kept.append(ln)
        used += len(ln) + 1
    kept.reverse()
    sess.calls.append({"tag": "socratic_plan", "tokens": 0, "channel": "Bs",
                       "captions_available": len(lines), "captions_kept": len(kept)})
    return sess.chat(head + "\n".join(kept) + tail,
                     max_completion=max_completion, tag="socratic")


def retr_only(sess: BudgetedSession, index: EpisodicIndex, question: str, k: int = 8) -> str:
    prompt = (f"Retrieved keyframes possibly relevant to the question. "
              f"Answer concisely: {question}")
    afford = (sess.remaining() - sess._est_text_tokens(prompt) - 128) // sess.img_tokens
    ids = index.retrieve(question, k=k)[: int(max(1, min(k, afford, sess.img_cap)))]
    return sess.chat(prompt, images=[index.frames[i] for i in ids],
                     max_completion=128, tag="retr_only")


def state_only(sess: BudgetedSession, state: SceneState, question: str,
               max_completion: int = 128) -> str:
    """State-only: the compressive channel without the verbatim one. The state is rendered
    to whatever B affords rather than to a hardcoded 6,000 characters, for the same reason
    as socratic() above."""
    head = "Compressed scene state of the walkthrough:\n"
    tail = f"\n\nAnswer concisely: {question}"
    room = (sess.remaining() - max_completion
            - sess._est_text_tokens(head + tail)) * 4
    return sess.chat(head + state.render(max(200, room)) + tail,
                     max_completion=max_completion, tag="state_only")


def build_entity_graph(captions: list[str]) -> dict:
    """Text entity scene graph for the EGAgent reimplementation, built offline from the
    SAME captions C_v uses (text-only, per the original). Nodes are entities with the
    time intervals they were mentioned in; this is deliberately a *text* structure, which
    is the configuration Thm. 1 bounds on episodic-appearance queries -- the whole point
    of the head-to-head. Without this the egagent arm had no graph to search."""
    import collections, re as _re
    STOP = {"a", "an", "the", "is", "are", "of", "in", "on", "at", "with", "and", "to",
            "this", "that", "there", "it", "its", "into", "from", "for", "by", "as"}
    spans: dict = collections.defaultdict(list)
    for t, cap in enumerate(captions):
        toks = [w for w in _re.findall(r"[a-z]+", (cap or "").lower())
                if w not in STOP and len(w) > 2]
        for w in set(toks):
            spans[w].append(t)
    nodes = {}
    for w, ts in spans.items():
        if len(ts) >= 2:                      # drop hapax noise from caption jitter
            nodes[w] = {"first": ts[0], "last": ts[-1], "n": len(ts)}
    # co-occurrence edges, capped so the graph stays inside the text budget
    edges = []
    keys = sorted(nodes, key=lambda w: -nodes[w]["n"])[:60]
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            shared = set(spans[a]) & set(spans[b])
            if len(shared) >= 2:
                edges.append({"a": a, "b": b, "t": sorted(shared)[:4]})
    return {"nodes": nodes, "edges": edges[:200]}


def egagent_reimpl(sess: BudgetedSession, index: EpisodicIndex, question: str,
                   entity_graph: dict, k: int = 8) -> str:
    """Reimplementation of EGAgent (Rege et al., ACL 2026) under our budget
    accounting: text entity scene graph search + visual search tools, planner
    loop. Graph is built offline from the same captions used by C_v (text-only,
    per the original). See docs/EGAGENT_REIMPL.md for parity checklist against
    facebookresearch/egagent."""
    import json as _json
    graph_txt = _json.dumps(entity_graph)[:6000]
    plan = sess.chat(
        f"Entity scene graph (nodes: people/objects/places; edges with time "
        f"intervals):\n{graph_txt}\n\nQuestion: {question}\n"
        f"Decompose into subtasks; if visual verification is needed output "
        f"VSEARCH: <query> on the last line, else ANSWER: <answer>.",
        max_completion=256, tag="egagent_plan")
    # An empty or whitespace-only plan is a REFUSAL, not a parse error: two backbones return
    # one on some CMP items, and splitlines()[-1] then raises IndexError and kills the cell.
    # Treated as "the planner produced no tool call", which is the same path an unparseable
    # plan already takes -- the model is scored on what it actually emitted (nothing), which
    # exact-match counts as wrong. Charging it a VSEARCH it never asked for would flatter the
    # baseline, and dropping the item would silently shrink n for one method only.
    # NOTE: when `plan` is non-empty this function is byte-for-byte the behaviour it had
    # before the guard, so cells that completed under the old code are unaffected.
    lines = plan.strip().splitlines()
    if not lines:
        return ""
    last = lines[-1]
    if last.startswith("VSEARCH:"):
        ids = index.retrieve(last[len("VSEARCH:"):].strip(), k=k)
        return sess.chat(f"Question: {question}\nAnswer concisely from these frames.",
                         images=[index.frames[i] for i in ids][:min(6, sess.img_cap)],
                         max_completion=96, tag="egagent_vsearch")
    return last[len("ANSWER:"):].strip() if last.startswith("ANSWER:") else plan
