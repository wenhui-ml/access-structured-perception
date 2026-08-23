#!/usr/bin/env python3
"""SEW-Bench: Synthetic Embodied Walkthrough -- a licence-free stand-in for EW-Bench.

WHY THIS EXISTS. EW-Bench as registered needs habitat-sim plus an HM3D/ScanNet licence
(annotation/generate_ewbench.py still raises NotImplementedError). SEW-Bench is what we
can actually build and measure: fully controlled ground truth over streams long enough
that every bound of Sec 3 is non-vacuous.

WHAT IT IS NOT. These are 2-D schematic renders, not egocentric video. They test ACCESS
STRUCTURE under a token budget, which is what Sec 3 is about; they do not test perception
in natural scenes. Every number from this corpus is an SEW-Bench number and is reported
as such -- never as an OpenEQA / VSI-Bench / EgoSchema number.

MAKING THE WALLS BIND. Theorem 1's ceiling is kappa_s = (m/(Nd) + 1)/log2 K, over the
ATTRIBUTE count Nd. The first version of this generator had d = 9, so at N = 150 the
denominator was 1,350 against m ~ 6,144 bits of state and kappa_s = 1.85 > 1: the
theorem said nothing at all. d is now the load-bearing parameter. Each frame carries
OBJ_PER_FRAME objects, each with two attributes drawn uniformly from a K = 8 alphabet
(colour and a printed letter tag), all re-randomised every frame:

    d = 2 * OBJ_PER_FRAME = 32      (room, door state and timestamp are NOT counted --
                                     they are not K-ary, so excluding them keeps d, and
                                     therefore the ceiling, conservative)
    N = 300, so Nd = 9,600  and  kappa_s = (6144/9600 + 1)/3 = 0.547

DESIGN NOTES.
  * Object CLASS is drawn as text; the queried attributes (colour, digit) are read off
    pixels. Labelling the colour would turn every RET item into OCR and hand the verbatim
    channel an advantage that has nothing to do with vision.
  * Filler classes are re-randomised per frame, so the entropy the state must compress is
    real. If fillers were fixed per room the stream would carry only |rooms| x 16 x 2
    attribute values in total and the Nd in the bound would be a fiction.
  * A RET target is a class that appears in EXACTLY ONE frame of the episode, so the
    question has a unique answer. It is not distinguishable from a filler at the time the
    state is written -- the online state builder sees one frame at a time and cannot know
    a class will never recur -- which is what makes the Fano argument apply to the run we
    actually perform.
  * Filler / singleton / tracked / chain class pools are disjoint, so a count question can
    never be contaminated by a filler draw.

  python annotation/generate_synthetic.py --out data/sew --frames 300 --episodes 4
"""
from __future__ import annotations
import argparse
import json
import math
import pathlib
import random

from PIL import Image, ImageDraw, ImageFont

W, H = 640, 480
COLS, ROWS = 4, 4
OBJ_PER_FRAME = COLS * ROWS          # 16
HEADER = 58

# K = 8 colour alphabet, matching Sec 3's K and the log2 K = 3 in every bound.
COLOURS = {
    "red": (198, 48, 48), "blue": (46, 84, 196), "green": (52, 148, 66),
    "yellow": (222, 190, 40), "purple": (140, 62, 172), "orange": (226, 124, 32),
    "brown": (128, 92, 56), "white": (244, 244, 242),
}
COLOUR_NAMES = list(COLOURS)
# Second K = 8 attribute, printed on the object. LETTERS, not digits: with digits, weaker
# backbones read the number printed on an object as "how many of these I have seen" and the
# TRK count questions become a measurement of that confusion instead of of the compressive
# channel. Observed directly -- Gemma-3-12B reported counts of 8 and 9 after six frames.
TAGS = list("ABCDEFGH")

# Disjoint class pools. Nothing in FILLERS may ever be counted or retrieved as a target.
FILLERS = ["cup", "pen", "fan", "rug", "pot", "tray", "bowl", "towel", "brush", "spoon",
           "fork", "plate", "glass", "candle", "soap", "comb", "hat", "sock", "belt", "ruler"]
SINGLETONS = ["kettle", "teapot", "stapler", "thermos", "ladle", "whisk",
              "tongs", "mortar", "decanter", "trivet", "colander", "sieve"]
TRACKED = ["mug", "book", "lamp", "vase"]
CHAINS = ["clock", "radio", "globe", "statue"]
ROOMS = ["living room", "kitchen", "study", "bedroom", "hallway", "pantry"]

_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
try:
    F_HDR = ImageFont.truetype(_FONT_B, 17)
    F_LBL = ImageFont.truetype(_FONT, 13)
    F_DIG = ImageFont.truetype(_FONT_B, 26)
except OSError:                              # pillow default is legible but small
    F_HDR = F_LBL = F_DIG = ImageFont.load_default()


def _dark(rgb) -> bool:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b < 140


def draw_frame(path, room: str, objs: list[tuple[str, str, str]], door_open: bool, t: int):
    """objs is a list of (class, colour_name, tag); rendered into a COLS x ROWS grid."""
    im = Image.new("RGB", (W, H), (238, 236, 231))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, HEADER], fill=(206, 212, 222))
    d.text((10, 6), f"room: {room}", fill=(16, 16, 16), font=F_HDR)
    d.text((10, 32), f"t={t}    door: {'open' if door_open else 'closed'}",
           fill=(16, 16, 16), font=F_HDR)
    cw, ch = W // COLS, (H - HEADER) // ROWS
    for i, (cls, col, tag) in enumerate(objs[:OBJ_PER_FRAME]):
        cx, cy = (i % COLS) * cw, HEADER + (i // COLS) * ch
        rgb = COLOURS[col]
        x0, y0 = cx + 10, cy + 5
        x1, y1 = cx + cw - 12, cy + ch - 26
        d.rectangle([x0, y0, x1, y1], fill=rgb, outline=(24, 24, 24), width=2)
        fg = (250, 250, 250) if _dark(rgb) else (18, 18, 18)
        bb = d.textbbox((0, 0), tag, font=F_DIG)
        d.text(((x0 + x1) / 2 - (bb[2] - bb[0]) / 2, (y0 + y1) / 2 - (bb[3] - bb[1]) / 2 - 3),
               tag, fill=fg, font=F_DIG)
        d.text((x0, y1 + 3), cls, fill=(16, 16, 16), font=F_LBL)
    im.save(path, quality=88)


def build_episode(ep: int, n: int, rng: random.Random, out: pathlib.Path,
                  seed: int = 0):
    fdir = out / f"frames/ep{ep}"
    fdir.mkdir(parents=True, exist_ok=True)

    # route with revisit loops, so recency and relevance dissociate
    route: list[str] = []
    while len(route) < n:
        route += [ROOMS[rng.randrange(len(ROOMS))]] * rng.randint(12, 26)
    route = route[:n]

    lo, hi = 15, n - 15
    free = list(range(lo, hi))
    rng.shuffle(free)

    def take(k: int) -> list[int]:
        # Silently returning fewer slots than asked for would make a count question's gold
        # quietly disagree with what was rendered, so refuse instead. N must be large
        # enough for 8 singletons + up to 36 tracked sightings + 12 chain sightings.
        if len(free) < k:
            raise SystemExit(f"[sew] ep{ep}: only {len(free)} free frames left, need {k}; "
                             f"raise --frames (300 is the calibrated value)")
        got, free[:] = free[:k], free[k:]
        return sorted(got)

    # --- RET: 8 singleton classes, each visible in EXACTLY ONE frame ---
    sing_cls = rng.sample(SINGLETONS, 8)
    sing = []
    for cls, t in zip(sing_cls, take(8)):
        sing.append(dict(cls=cls, t=t, colour=rng.choice(COLOUR_NAMES),
                         tag=rng.choice(TAGS), room=route[t]))

    # --- TRK: 4 counted classes, plus the door series ---
    trk = []
    for cls in TRACKED:
        ts = take(rng.randint(3, 9))
        trk.append(dict(cls=cls, ts=ts, n=len(ts)))
    toggles = sorted(rng.sample(range(5, n - 5), rng.randint(5, 9)))
    door, door_series = False, []
    for t in range(n):
        if t in toggles:
            door = not door
        door_series.append(door)

    # --- CMP: 4 chain classes, 3 sightings each, 3 DISTINCT rooms, 3 DISTINCT colours ---
    chains = []
    for cls in CHAINS:
        ts, cand = [], list(free)
        rng.shuffle(cand)
        rooms_used = set()
        for t in cand:
            if route[t] not in rooms_used:
                ts.append(t)
                rooms_used.add(route[t])
            if len(ts) == 3:
                break
        if len(ts) < 3:
            raise SystemExit(f"[sew] ep{ep}: cannot place a 3-room chain for {cls}")
        for t in ts:
            free.remove(t)
        ts = sorted(ts)
        chains.append(dict(cls=cls, ts=ts, rooms=[route[t] for t in ts],
                           colours=rng.sample(COLOUR_NAMES, 3),
                           tags=rng.sample(TAGS, 3)))

    # --- render ---
    special: dict[int, list[tuple[str, str, str]]] = {}
    for s in sing:
        special.setdefault(s["t"], []).append((s["cls"], s["colour"], s["tag"]))
    for e in trk:
        for t in e["ts"]:
            special.setdefault(t, []).append(
                (e["cls"], rng.choice(COLOUR_NAMES), rng.choice(TAGS)))
    for c in chains:
        for i, t in enumerate(c["ts"]):
            special.setdefault(t, []).append((c["cls"], c["colours"][i], c["tags"][i]))

    for t in range(n):
        objs = list(special.get(t, []))
        n_fill = OBJ_PER_FRAME - len(objs)
        for cls in rng.sample(FILLERS, n_fill):
            objs.append((cls, rng.choice(COLOUR_NAMES), rng.choice(TAGS)))
        rng.shuffle(objs)
        draw_frame(fdir / f"frame_{t:04d}.jpg", route[t], objs, door_series[t], t)

    # --- questions ---
    def q(subset, question, answer, **kw):
        return dict(subset=subset, episode=f"ep{ep}", frames_dir=str(fdir),
                    question=question, answer=answer, **kw)

    qs = []
    for i, s in enumerate(sing):                       # 8 RET: 4 colour, 4 digit
        if i % 2 == 0:
            qs.append(q("RET", f"You saw a {s['cls']} exactly once during the walkthrough. "
                               f"What colour was it?", s["colour"], target_t=[s["t"]], d_q=1))
        else:
            qs.append(q("RET", f"You saw a {s['cls']} exactly once during the walkthrough. "
                               f"What single capital letter was printed on it?", s["tag"],
                        target_t=[s["t"]], d_q=1))
    for e in trk:                                      # 4 + 2 = 6 TRK
        qs.append(q("TRK", f"How many {e['cls']}s did you see in total across the whole "
                           f"walkthrough? Answer with a number.", str(e["n"]), d_q=1))
    qs.append(q("TRK", "Was the door open or closed at the end of the walkthrough?",
                "open" if door_series[-1] else "closed", d_q=1))
    qs.append(q("TRK", "How many times did the door change between open and closed? "
                       "Answer with a number.", str(len(toggles)), d_q=1))
    for c in chains:                                   # 4 + 2 = 6 CMP
        qs.append(q("CMP", f"You saw a {c['cls']} exactly three times, each in a different "
                           f"room. What colour was it the SECOND time you saw it?",
                    c["colours"][1], d_q=2, hop_rooms=c["rooms"]))
    # The order the two singletons are NAMED IN must be randomised, or the gold is a constant.
    # take() returns sorted frame indices, so sing[i]["t"] < sing[i+1]["t"] always held and
    # naming the earlier one first made every one of these items answerable with the single
    # word "before": all 8 in the shipped corpus carry that gold, a blind agent scored 8/8 on
    # them, and a third of the CMP subtest measured a prior instead of access (deviations
    # D-43). The corpus THIS PAPER MEASURED predates this fix and the gold-distribution gate
    # below now refuses to ship it.
    #
    # Two properties are needed here and only one of them is randomness.
    #
    # (1) The draw must come from an ITEM-LOCAL generator, not from `rng`. That is not
    #     fastidiousness: `rng` is a single stream walked across every frame and every
    #     episode, so one extra draw here shifts all downstream sampling and the whole corpus
    #     changes -- which turns the 69-cell CMP re-run this fix exists to enable into a full
    #     207-cell regrid plus 8,400 offline update calls. Deriving the order from a
    #     seed-and-slot string keeps frames, singletons, tracked classes and chains
    #     bit-identical to the shipped corpus and changes only these items.
    #
    # (2) A shuffle is not enough. Shuffling eight binary items independently gave 6 "before"
    #     to 2 "after" at the shipped seed -- inside the gate's tolerance, but a constant
    #     answer still scores 75% on a subtest whose chance level is meant to be 50%. With
    #     n=8 no unbiased coin reliably lands on 4/4, so the balance is CONSTRUCTED instead:
    #     a fixed permutation of four "before" and four "after" is derived once from the
    #     corpus seed and consumed by slot index, and the naming order is then chosen to
    #     realise the assigned gold. The which-item-gets-which is random; the tally is not.
    _bal = list(range(8))
    random.Random(f"cmp-balance|{seed}").shuffle(_bal)
    for idx, (i0, i1) in enumerate(((0, 1), (2, 3))):
        slot = (2 * (ep - 1) + idx) % 8
        want_before = _bal[slot] < 4
        a, b = sing[i0], sing[i1]
        if (a["t"] < b["t"]) != want_before:      # take() sorts, so a["t"] < b["t"] always
            a, b = b, a
        qs.append(q("CMP", f"Did you see the {a['cls']} before or after the {b['cls']}? "
                           f"Answer 'before' or 'after'.",
                    "before" if a["t"] < b["t"] else "after", d_q=2))

    meta = dict(episode=f"ep{ep}", n_frames=n, obj_per_frame=OBJ_PER_FRAME,
                d_attributes=2 * OBJ_PER_FRAME, K=len(COLOURS),
                Nd=n * 2 * OBJ_PER_FRAME, toggles=len(toggles),
                singletons=[{k: s[k] for k in ("cls", "t", "colour", "tag")} for s in sing],
                tracked={e["cls"]: e["n"] for e in trk},
                chains={c["cls"]: dict(ts=c["ts"], rooms=c["rooms"], colours=c["colours"])
                        for c in chains})
    return qs, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sew")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--episodes", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--ls-tokens", type=int, default=512, help="L_s, for the kappa_s report")
    ap.add_argument("--bits-per-token", type=float, default=12.0)
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)

    allq, allm = [], []
    for ep in range(1, a.episodes + 1):
        qs, m = build_episode(ep, a.frames, rng, out, seed=a.seed)
        allq += qs
        allm.append(m)
        print(f"  ep{ep}: N={m['n_frames']} d={m['d_attributes']} Nd={m['Nd']} "
              f"{len(qs)} questions")

    # Refuse to ship an ambiguous item: a confident gold label on an unanswerable question
    # is worse than no item at all, because it surfaces as a model failure.
    bad, seen = [], {}
    for it in allq:
        key = (it["episode"], it["question"])
        if key in seen and seen[key] != it["answer"]:
            bad.append(f"{key} has conflicting golds {seen[key]!r} vs {it['answer']!r}")
        seen[key] = it["answer"]
    pools = [set(FILLERS), set(SINGLETONS), set(TRACKED), set(CHAINS)]
    for i in range(len(pools)):
        for j in range(i + 1, len(pools)):
            if pools[i] & pools[j]:
                bad.append(f"class pools {i},{j} overlap: {pools[i] & pools[j]}")
    # Degenerate gold DISTRIBUTIONS are as damaging as ambiguous golds and the gate above
    # could not see them. Found after measurement: all eight CMP before/after items carried
    # the gold "before", so a blind agent answering a constant scored 8/8 on them and a third
    # of the CMP subtest was answerable with no access to the stream at all -- blind CMP fell
    # from 34-41% to 5-11% once those items were removed in re-analysis (deviations D-43).
    # A gold that is more common than 1/K + slack means the item set can be beaten by a prior.
    import collections as _c
    by_alpha: dict = _c.defaultdict(_c.Counter)
    for it in allq:
        a_ = str(it["answer"]).strip().lower()
        if a_ in ("before", "after"):
            alpha_name, k = "before/after", 2
        elif a_ in ("open", "closed"):
            alpha_name, k = "open/closed", 2
        elif a_.isdigit():
            continue                       # integer counts have no fixed alphabet
        elif len(a_) == 1 and a_.isalpha():
            alpha_name, k = "letter", len(TAGS)
        else:
            alpha_name, k = "colour", len(COLOUR_NAMES)
        by_alpha[(it["subset"], alpha_name, k)][a_] += 1
    for (sub, alpha_name, k), cnt in sorted(by_alpha.items()):
        n = sum(cnt.values())
        if n < 4:
            continue
        top, hits = cnt.most_common(1)[0]
        # Bonferroni-corrected binomial tail. The statistic is the count of the MOST COMMON
        # gold, i.e. a maximum over k categories, so a per-category tail is the wrong test:
        # at K=8 and n=16, six of one colour is ordinary sampling noise (uncorrected tail
        # 0.026, corrected 0.21) and flagging it would make the gate cry wolf. Eight of eight
        # at K=2 is not (corrected 0.008).
        tail = sum(math.comb(n, i) * (1.0 / k) ** i * (1 - 1.0 / k) ** (n - i)
                   for i in range(hits, n + 1))
        if tail * k < 0.05:
            bad.append(f"{sub}/{alpha_name}: gold {top!r} is {hits}/{n} of the items "
                       f"(corrected binomial tail {tail * k:.4f} at K={k}); a constant answer "
                       f"beats chance on this slice, so the subtest would measure a prior "
                       f"rather than access")
    if bad:
        raise SystemExit("[sew] refusing to ship:\n  " + "\n  ".join(bad))

    m_bits = a.ls_tokens * a.bits_per_token
    Nd = allm[0]["Nd"]
    kappa = (m_bits / Nd + 1) / math.log2(len(COLOURS))
    from collections import Counter
    cnt = Counter(it["subset"] for it in allq)
    print(f"validation: {len(seen)} unique items, no conflicting golds, pools disjoint")
    print(f"subsets: {dict(cnt)}")
    print(f"Thm 1 at these parameters: m={m_bits:.0f} bits, Nd={Nd}, K={len(COLOURS)} "
          f"-> kappa_s = {kappa:.3f}  ({'BINDS' if kappa < 1 else 'VACUOUS'})")
    (out / "questions.json").write_text(json.dumps(allq, indent=2))
    (out / "meta.json").write_text(json.dumps(allm, indent=2))
    print(f"wrote {len(allq)} questions to {out}")


if __name__ == "__main__":
    main()
