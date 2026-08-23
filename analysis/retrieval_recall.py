#!/usr/bin/env python3
"""Measure delta_r: how often the episodic index actually returns the RET target frame.

Assumption 1(ii) of the paper is that query-conditioned retrieval finds the target with
probability >= 1 - delta_r, and Proposition 1's RET bound is 1 - (eps_0 + delta_r). If
delta_r is near 1 the whole comparison degenerates: ASP and Retr-only would fail for a
reason that has nothing to do with access structure, and the experiment would be
measuring the index, not the theory. So delta_r is measured rather than assumed -- and it
costs NOTHING, because the index and the captions are already cached and the ranking is
local computation.

Reported per backbone: recall@k for the k the RET budget actually affords, plus the rank
distribution and the share of misses attributable to the target class being absent from
its own caption (a compressive-channel failure) versus present but out-ranked (a ranking
failure). Those are different defects with different fixes and should not be pooled.

  python analysis/retrieval_recall.py
"""
from __future__ import annotations
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from methods.asp import EpisodicIndex          # noqa: E402
from openrouter_client import IMG_TOKENS, MODELS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data/sew"
K_DEFAULT = 8


def ret_items():
    items = json.loads((DATA / "questions.json").read_text())
    return [it for it in items if it["subset"] == "RET" and it.get("target_t")]


def target_class(question: str) -> str:
    m = re.search(r"You saw a (\w+) exactly once", question)
    return m.group(1) if m else ""


def main():
    out = {}
    for model in MODELS:
        caches = sorted((ROOT / "results/cache").glob(f"{model}_sew_ep*_tau0.0_v*.json"))
        if not caches:
            continue
        per_model = {"n": 0, "hit_at_k": 0, "hit_at_1": 0, "ranks": [],
                     "miss_class_absent_from_caption": 0, "miss_outranked": 0,
                     "k": K_DEFAULT, "incomplete_episodes": []}
        for c in caches:
            blob = json.loads(c.read_text())
            kf, caps = blob["kf"], blob["captions"]
            if len(kf) < 300:
                per_model["incomplete_episodes"].append(f"{c.stem}:{len(kf)}")
            ep = re.search(r"_(ep\d+)_", c.name).group(1)
            index = EpisodicIndex()
            for f, cap in zip(kf, caps):
                index.add(f, cap)
            frame_pos = {p: i for i, p in enumerate(kf)}
            for it in ret_items():
                if it["episode"] != ep:
                    continue
                tgt = it["target_t"][0]
                tgt_path = str(pathlib.Path(it["frames_dir"]) / f"frame_{tgt:04d}.jpg")
                if tgt_path not in frame_pos:
                    continue          # episode truncated before the target
                pos = frame_pos[tgt_path]
                ranked = index.retrieve(it["question"], k=len(kf))
                rank = ranked.index(pos) + 1
                per_model["n"] += 1
                per_model["ranks"].append(rank)
                per_model["hit_at_k"] += int(rank <= K_DEFAULT)
                per_model["hit_at_1"] += int(rank == 1)
                if rank > K_DEFAULT:
                    cls = target_class(it["question"])
                    if cls and cls.lower() not in (caps[pos] or "").lower():
                        per_model["miss_class_absent_from_caption"] += 1
                    else:
                        per_model["miss_outranked"] += 1
        if per_model["n"]:
            r = sorted(per_model["ranks"])
            per_model["recall_at_k"] = round(per_model["hit_at_k"] / per_model["n"], 3)
            per_model["delta_r"] = round(1 - per_model["hit_at_k"] / per_model["n"], 3)
            per_model["median_rank"] = r[len(r) // 2]
            per_model["img_tokens"] = IMG_TOKENS.get(MODELS[model])
            out[model] = per_model
    # S4(a), the retrieval mixing weight, run here because it costs nothing: alpha only
    # reweights the cosine and BM25 terms of an index that is already built, so the whole
    # sweep is local computation. alpha=1 is vision-only, alpha=0 is captions-only.
    sweep = {}
    for alpha in (0.0, 0.25, 0.5, 0.6, 0.75, 1.0):
        hit = n = 0
        for model in MODELS:
            for c in sorted((ROOT / "results/cache").glob(f"{model}_sew_ep*_tau0.0_v*.json")):
                blob = json.loads(c.read_text())
                kf, caps = blob["kf"], blob["captions"]
                ep = re.search(r"_(ep\d+)_", c.name).group(1)
                index = EpisodicIndex(alpha=alpha)
                for f, cap in zip(kf, caps):
                    index.add(f, cap)
                pos = {q: i for i, q in enumerate(kf)}
                for it in ret_items():
                    if it["episode"] != ep:
                        continue
                    tp = str(pathlib.Path(it["frames_dir"]) / f"frame_{it['target_t'][0]:04d}.jpg")
                    if tp not in pos:
                        continue
                    n += 1
                    hit += int(pos[tp] in index.retrieve(it["question"], k=K_DEFAULT))
        sweep[alpha] = round(hit / n, 3) if n else None
        print(f"  alpha={alpha:<5} recall@{K_DEFAULT} = {sweep[alpha]}  (n={n})")
    out["_alpha_sweep"] = sweep

    (ROOT / "analysis/retrieval_recall.json").write_text(json.dumps(out, indent=2))
    print(f"{'backbone':20s} {'n':>4} {'R@1':>6} {'R@8':>6} {'delta_r':>8} {'med rank':>9}  misses (caption/rank)")
    for m, d in out.items():
        if m.startswith("_"):
            continue
        print(f"{m:20s} {d['n']:4d} {d['hit_at_1']/d['n']:6.2f} {d['recall_at_k']:6.2f} "
              f"{d['delta_r']:8.2f} {d['median_rank']:9d}  "
              f"{d['miss_class_absent_from_caption']}/{d['miss_outranked']}"
              + (f"   [INCOMPLETE: {len(d['incomplete_episodes'])} ep]"
                 if d["incomplete_episodes"] else ""))
    print("\nalpha sweep (S4a): " + "  ".join(f"{a}:{r}" for a, r in
          (out.get("_alpha_sweep") or {}).items()))
    print("[retrieval_recall] wrote analysis/retrieval_recall.json")


if __name__ == "__main__":
    main()
