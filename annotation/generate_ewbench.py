#!/usr/bin/env python3
"""EW-Bench generator (paper App. B).

Renders 60 walkthroughs from HM3D/ScanNet via habitat-sim with scripted revisit
loops, then programmatically emits 300/300/300 RET/TRK/CMP questions from
ground-truth annotations. This file implements the QUESTION side end-to-end and
stubs the rendering call (server needs habitat-sim + HM3D license).

Output: data/ewbench/{questions.json, frames/<episode>/*.jpg, meta.json}

Question templates (K=8 effective alphabet; visibility multiplicity logged):
  RET: "What color/material was the <class> on the <surface> in the <room>?"
       target attribute visible in exactly 1-2 keyframes (strict subset flagged).
  TRK: "How many <class> did you see across all rooms?" /
       "Was the <door/cabinet> open or closed at the end?" (>=4 toggles) /
       "Where is <obj> now?" (containment after >=3 moves).
  CMP: chains of d_q in {3,4,5} dependent references, e.g.
       "The object that was on the table you passed AFTER the red chair -- where is it now?"
       Surface forms paraphrased by an LLM and human-verified (2 annotators).
"""
import argparse, itertools, json, pathlib, random

COLORS = ["red", "blue", "green", "black", "white", "yellow", "brown", "gray"]  # K=8

def render_walkthrough(scene_id: str, out_dir: pathlib.Path, seed: int):
    """TODO(server): habitat-sim render at 1-2 m/s with scripted revisit loop,
    dump frames + per-frame GT (visible objects, attrs, room, pose) to meta."""
    raise NotImplementedError("run on server with habitat-sim installed")

def make_questions(meta: dict, rng: random.Random):
    qs = []
    # --- RET: single/double-visibility attribute queries ---
    for obj in meta["objects"]:
        vis = obj["visible_keyframes"]
        if 1 <= len(vis) <= 2 and obj.get("color") in COLORS:
            qs.append(dict(subset="RET", strict=(len(vis) == 1),
                           question=f"What color was the {obj['class']} on the "
                                    f"{obj.get('surface','floor')} in the {obj['room']}?",
                           answer=obj["color"], target_kf=vis))
    # --- TRK: running reductions ---
    counts = {}
    for obj in meta["objects"]:
        counts[obj["class"]] = counts.get(obj["class"], 0) + 1
    for cls, n in counts.items():
        if n >= 2:
            qs.append(dict(subset="TRK", question=f"How many {cls}s did you see in total?",
                           answer=str(n)))
    for d in meta.get("doors", []):
        if len(d["toggles"]) >= 4:
            qs.append(dict(subset="TRK",
                           question=f"Was the {d['name']} open or closed at the end?",
                           answer=d["final_state"]))
    # --- CMP: dependent reference chains (d_q = 3..5) ---
    for chain in meta.get("chains", []):
        if 3 <= chain["d_q"] <= 5:
            qs.append(dict(subset="CMP", d_q=chain["d_q"],
                           question=chain["surface_form"], answer=chain["answer"]))
    rng.shuffle(qs)
    return qs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", type=int, default=60)
    ap.add_argument("--per-subset", type=int, default=300)
    ap.add_argument("--out", default="data/ewbench")
    ap.add_argument("--seed", type=int, default=20260821)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    all_qs = []
    for s in range(args.scenes):
        ep = f"ep{s:03d}"
        meta_p = out / "frames" / ep / "meta.json"
        if not meta_p.exists():
            render_walkthrough(scene_id=f"hm3d_{s}", out_dir=out / "frames" / ep, seed=s)
        meta = json.loads(meta_p.read_text())
        for q in make_questions(meta, rng):
            q.update(episode=ep, frames_dir=str(out / "frames" / ep))
            all_qs.append(q)
    balanced = list(itertools.chain.from_iterable(
        [q for q in all_qs if q["subset"] == s][: args.per_subset]
        for s in ("RET", "TRK", "CMP")))
    (out / "questions.json").write_text(json.dumps(balanced, indent=2))
    print(f"wrote {len(balanced)} questions -> {out/'questions.json'}")

if __name__ == "__main__":
    main()
