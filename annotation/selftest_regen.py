#!/usr/bin/env python3
"""Regression test for the regeneration contract asserted in the paper (App. C.1).

The two corrections of Sec. 5.6 (item-local RNG, constructed gold balance) are only safe
because they leave the rest of the corpus untouched: the generator walks ONE Random across
every frame of every episode, so a fix that consumes a draw from that stream changes all
downstream sampling -- which invalidates the offline keyframe caches and every one of the 207
measured cells, turning a 69-cell CMP re-run into a full regrid.

The paper states that property as a number, so it is tested rather than trusted:

  * all 1,200 frames and meta.json regenerate byte-identical at the shipped seed
  * exactly four of the eighty questions change (the ones whose naming order had to flip)
  * the before/after gold tally is exactly 4-4, not merely "not flagged by the gate"

Needs no API key and no network. Exits non-zero on any violation.
"""
from __future__ import annotations
import collections
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE = ROOT / "data/sew"
# Frames and meta.json are compared against the LIVE corpus (they must be byte-stable across
# the fix, which is the whole point). Questions are compared against the ARCHIVED pre-fix item
# set, because data/sew now holds the corrected one -- comparing it against itself would make
# the "exactly four questions change" assertion vacuous.
SHIPPED = ROOT / "data/sew_pre_cmpfix" if (ROOT / "data/sew_pre_cmpfix/questions.json").exists() \
    else LIVE
GEN = ROOT / "annotation/generate_synthetic.py"
SEED = 7                                  # the shipped corpus seed
EXPECT_CHANGED = 4                        # items whose naming order flips
EXPECT_BALANCE = {"before": 4, "after": 4}

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'ok ' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def main() -> int:
    if not (SHIPPED / "questions.json").exists() or not (LIVE / "meta.json").exists():
        print(f"no shipped corpus at {SHIPPED}; nothing to compare against")
        return 0

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="sew-regen-"))
    try:
        r = subprocess.run([sys.executable, str(GEN), "--out", str(tmp),
                            "--seed", str(SEED)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout + r.stderr)
            check(False, "generator exits 0", f"rc={r.returncode}")
            return 1
        check(True, "generator exits 0 (answerability gate passes)")

        # --- frames must be byte-identical, or every offline cache is void ---
        shipped_frames = sorted((LIVE / "frames").rglob("*.jpg"))
        regen_frames = sorted((tmp / "frames").rglob("*.jpg"))
        check(len(shipped_frames) == len(regen_frames) and len(shipped_frames) > 0,
              "frame count matches", f"{len(shipped_frames)} vs {len(regen_frames)}")
        differing = [a.name for a, b in zip(shipped_frames, regen_frames)
                     if a.read_bytes() != b.read_bytes()]
        check(not differing, "all frames byte-identical",
              f"{len(differing)} differ" if differing else f"{len(regen_frames)} frames")

        check((LIVE / "meta.json").read_bytes() == (tmp / "meta.json").read_bytes(),
              "meta.json byte-identical")
        check((SHIPPED / "meta.json").read_bytes() == (tmp / "meta.json").read_bytes(),
              "meta.json unchanged since the pre-fix corpus")

        # --- questions: only the items the fix is about may move ---
        old = json.loads((SHIPPED / "questions.json").read_text())
        new = json.loads((tmp / "questions.json").read_text())
        check(len(old) == len(new), "question count matches", f"{len(old)} vs {len(new)}")
        changed = [(a, b) for a, b in zip(old, new)
                   if a["question"] != b["question"] or a["answer"] != b["answer"]]
        check(len(changed) == EXPECT_CHANGED,
              f"exactly {EXPECT_CHANGED} questions change", f"got {len(changed)}")
        stray = [a["subset"] for a, _ in changed if a["subset"] != "CMP"]
        check(not stray, "every change is in CMP", f"also touched {set(stray)}" if stray else "")

        moved = [(a, b) for a, b in zip(old, new)
                 if a["subset"] != "CMP" and (a["question"] != b["question"]
                                              or a["answer"] != b["answer"])]
        check(not moved, "no RET/TRK item moved (the 138 un-rerun cells stay valid)",
              f"{len(moved)} moved" if moved else "")

        # --- the point of the fix: the tally is constructed, not sampled ---
        bal = dict(collections.Counter(i["answer"] for i in new
                                       if i["answer"] in ("before", "after")))
        check(bal == EXPECT_BALANCE, "before/after gold tally is exactly 4-4", str(bal))

        # --- and the shipped corpus is genuinely the degenerate one being replaced ---
        old_bal = dict(collections.Counter(i["answer"] for i in old
                                           if i["answer"] in ("before", "after")))
        check(len(old_bal) == 1, "shipped corpus was degenerate (documents D-43)", str(old_bal))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nFAILURES: {len(fails)}")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
