#!/usr/bin/env python3
"""Measure Assumption 1 (representational sufficiency) directly. This is Table tab:probe,
which the pre-registration named and the first pass did not run.

WHY THIS IS NOW LOAD-BEARING. Every bound in Sec. 3 is a bound on ACCESS, and every positive
statement about Asp (Prop. 1) is conditioned on the backbone being able to read an attribute
off a keyframe that is IN CONTEXT, with error at most eps_0. The measured grid sits near
chance for most methods, and there are two completely different explanations:

  (a) access structure is the binding constraint  -> the paper's thesis
  (b) these backbones cannot read the frames at all -> Assumption 1 fails, and NOTHING in the
      grid is evidence about access structure, in either direction

The two are indistinguishable from the grid alone, because a retrieval success followed by a
misread scores exactly like a retrieval failure. This script separates them by removing access
from the problem entirely: it asks the RET question with the target frame handed to the model,
which is the best case Assumption 1 describes.

  eps_0 : single-keyframe attribute accuracy. The exact RET question, one image, the RIGHT
          image. Chance is 1/K = 12.5%.
  eps_1 : one composition step. Two frames of the same class with their indices rendered in
          the header, asked which came first. Chance is 50%, so this is the weaker probe of
          the two and is reported as such.

Costs one single-image call per item, so the whole table is ~400 calls. No GPU: the backbone
is the OpenRouter API and the scoring is the same rule-first scorer the grid uses.

Run: python scripts/probe_assumption.py [--models a,b] [--out results/probe.json]
"""
from __future__ import annotations
import argparse
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from openrouter_client import MODELS, BudgetedSession, BudgetExhausted   # noqa: E402
from sew_score import rule_match                                        # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data/sew"


def frame(ep: str, t: int) -> str:
    return str(DATA / f"frames/{ep}/frame_{t:04d}.jpg")


def load_items():
    qs = json.load(open(DATA / "questions.json"))
    meta = {m["episode"]: m for m in json.load(open(DATA / "meta.json"))}
    ret, cmp_ = [], []
    for q in qs:
        if q["subset"] != "RET":
            continue
        ts = json.loads(q["target_t"]) if isinstance(q["target_t"], str) else q["target_t"]
        ret.append({"ep": q["episode"], "t": int(ts[0]), "q": q["question"],
                    "gold": q["answer"]})
    # one-step composition: two sightings of the same chain class, which came first
    rng = random.Random(11)
    for ep, m in meta.items():
        for cls, c in m["chains"].items():
            ts = sorted(c["ts"])
            i, j = 0, 2                       # first vs last: the least ambiguous pair
            pair = [(ts[i], "first"), (ts[j], "second")]
            rng.shuffle(pair)
            cmp_.append({"ep": ep, "ts": [p[0] for p in pair], "cls": cls,
                         "gold": "first" if pair[0][1] == "first" else "second"})
    return ret, cmp_


ATTR_PROMPT = ("This is a single frame from a walkthrough. It shows a grid of objects; each "
               "object is a coloured rectangle with a printed capital letter on it and its "
               "class name written underneath.\n{q}\nAnswer with one word only.")
STEP_PROMPT = ("These are two frames from the same walkthrough, in the order shown. Each "
               "frame's header gives its frame index. Both frames contain a {cls}.\n"
               "Was the {cls} in the FIRST image seen earlier in the walkthrough than the "
               "{cls} in the SECOND image? Answer exactly 'first' or 'second' -- 'first' if "
               "the first image came earlier, 'second' if the second image came earlier.")


def probe(model: str, ret, cmp_, budget: int) -> dict:
    out = {"model": model, "slug": MODELS[model], "attr": [], "step": []}
    for it in ret:
        sess = BudgetedSession(model, budget=budget)
        try:
            pred = sess.chat(ATTR_PROMPT.format(q=it["q"]), images=[frame(it["ep"], it["t"])],
                             max_completion=24, tag="probe_attr")
        except (BudgetExhausted, RuntimeError) as e:
            out["attr"].append({"ep": it["ep"], "t": it["t"], "gold": it["gold"],
                                "pred": None, "score": None, "error": str(e)[:160]})
            continue
        s = rule_match(pred, it["gold"])
        if s is not None:
            s = s / 100.0            # rule_match is on the grid's 0-100 accuracy scale
        out["attr"].append({"ep": it["ep"], "t": it["t"], "gold": it["gold"],
                            "pred": pred.strip()[:60], "score": s})
    for it in cmp_:
        sess = BudgetedSession(model, budget=budget)
        imgs = [frame(it["ep"], t) for t in it["ts"]]
        try:
            pred = sess.chat(STEP_PROMPT.format(cls=it["cls"]), images=imgs,
                             max_completion=24, tag="probe_step")
        except (BudgetExhausted, RuntimeError) as e:
            out["step"].append({"ep": it["ep"], "cls": it["cls"], "gold": it["gold"],
                                "pred": None, "score": None, "error": str(e)[:160]})
            continue
        low = pred.strip().lower()
        s = (1.0 if ("first" in low) == (it["gold"] == "first") and
             ("first" in low or "second" in low) else 0.0)
        if "first" not in low and "second" not in low:
            s = None                     # unparseable: counted as a deferral, not as a miss
        out["step"].append({"ep": it["ep"], "cls": it["cls"], "gold": it["gold"],
                            "pred": pred.strip()[:60], "score": s})
    return out


def summarise(rec: dict) -> dict:
    def agg(rows):
        got = [r["score"] for r in rows if r.get("score") is not None]
        defer = sum(1 for r in rows if r.get("score") is None and not r.get("error"))
        err = sum(1 for r in rows if r.get("error"))
        return {"n": len(rows), "scored": len(got),
                "acc": (sum(got) / len(got)) if got else None,
                "deferred": defer, "errors": err}
    return {"model": rec["model"], "attr": agg(rec["attr"]), "step": agg(rec["step"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--budget", type=int, default=4096)
    ap.add_argument("--out", default="results/probe.json")
    a = ap.parse_args()

    ret, cmp_ = load_items()
    print(f"[probe] {len(ret)} attribute items, {len(cmp_)} one-step items per backbone")
    outp = ROOT / a.out
    recs = json.load(open(outp)) if outp.exists() else {}
    for model in [m.strip() for m in a.models.split(",") if m.strip()]:
        if model in recs:
            print(f"[probe] {model}: cached, skipping")
            continue
        print(f"[probe] {model} ...", flush=True)
        recs[model] = probe(model, ret, cmp_, a.budget)
        outp.parent.mkdir(parents=True, exist_ok=True)
        json.dump(recs, open(outp, "w"), indent=1)
        s = summarise(recs[model])
        print(f"[probe] {model}: attr {s['attr']}  step {s['step']}")

    print(f"\n{'backbone':20s} {'1-eps_0':>9} {'n':>4} {'1-eps_1':>9} {'n':>4}   "
          f"(chance 12.5% / 50%)")
    for model, rec in recs.items():
        s = summarise(rec)
        a0 = s["attr"]["acc"]
        a1 = s["step"]["acc"]
        print(f"{model:20s} "
              f"{(f'{100*a0:8.1f}%' if a0 is not None else '        -')} "
              f"{s['attr']['scored']:4d} "
              f"{(f'{100*a1:8.1f}%' if a1 is not None else '        -')} "
              f"{s['step']['scored']:4d}")
    print(f"\n[probe] written to {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
