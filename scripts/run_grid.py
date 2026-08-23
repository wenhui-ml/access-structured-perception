#!/usr/bin/env python3
"""Drive the whole SEW-Bench grid over OpenRouter: offline phase, main table,
ablations, and the B=16k arm of P3.

Every cell is one `run_eval.py` subprocess, so a failure is isolated to its own cell and
the rest of the grid still finishes. `--resume` skips cells whose per-question record
already exists, which makes the grid restartable after a rate-limit storm.

Phases, in dependency order:
  offline    one job per (backbone, episode). SERIAL within an episode -- the scene state
             is a fold over the stream -- so the only available parallelism is across
             (backbone, episode) pairs. Every later phase reads these caches, so running
             this first turns 7 methods x 3 subsets of repeated update calls into one.
  main       backbones x methods x subsets at B = 4,096   -> Table 2
  ablation   flagship x ASP variants x subsets at B = 4,096 -> Table 3
  p3         Uniform-w at B = 16,384                       -> P3 (reallocation vs growth)

  python scripts/run_grid.py --phase offline --jobs 12
  python scripts/run_grid.py --phase main --jobs 12 --resume
"""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
# -u: the per-cell logs are the only progress signal, and block buffering
# hides them until the job ends.
RUN = [sys.executable, "-u", str(ROOT / "scripts/run_eval.py")]

# Backbone ladder. Parameter counts are the x-axis of P2 (capability convergence), so the
# ladder has to span the class rather than repeat a size. Two of the five REGISTERED
# backbones do not exist on OpenRouter (qwen2.5-vl-7b, qwen3-omni-30b-a3b -- verified with
# scripts/check_models.py against the live catalogue); the substitutions are marked and
# recorded in notes/deviations.md, not silently swapped.
BACKBONES = [
    ("ministral-3b",      3,  "substitute for the 7B slot"),
    ("qwen3-vl-8b",       8,  "registered"),
    ("gemma-3-12b",      12,  "added: fills the 8->27 gap in the ladder"),
    ("ministral-14b",     14,  "added: second gap-filler, different provider to gemma-3-12b"),
    ("qwen3.8-27b",      27,  "registered (flagship)"),
    ("qwen3-vl-30b-a3b", 30,  "substitute for Qwen3-Omni-30B-A3B (MoE, 3B active)"),
    ("gemma-4-31b",      31,  "registered"),
]
MODELS = [m for m, _, _ in BACKBONES]
FLAGSHIP = "qwen3.8-27b"
METHODS = ["blind", "uniform16", "socratic", "retr_only", "state_only", "egagent", "asp"]
ABLATIONS = ["asp_no_cv", "asp_no_cs", "asp_no_rho", "asp_r1", "asp_r5", "asp_rand_retr"]
SUBSETS = ["RET", "TRK", "CMP"]
DATA = "data/sew"
EPISODES = ["ep1", "ep2", "ep3", "ep4"]
TAU_G = 0.0          # SEW emits one frame per discrete moment: the gate must be identity


def jobs_for(phase: str, only_subset: str | None = None) -> list[tuple[str, list[str]]]:
    """Build the cell list for one phase.

    `only_subset` exists for targeted re-runs of a single witness subtest -- the CMP re-run
    after the D-43/D-45 corpus fix, where the offline caches are keyed by
    (backbone, episode, tau_g) and hold no question, so they are reused verbatim and only the
    scored decisions are repaid. It filters the SAME job list the full grid builds, so the
    re-run is not a different code path with a different set of defaults.
    """
    todo: list = []
    if phase == "offline":
        for m in MODELS:
            for ep in EPISODES:
                todo.append((f"offline:{m}:{ep}",
                            ["--model", m, "--method", "asp", "--bench", "sew",
                             "--data", DATA, "--episode", ep, "--build-cache-only"]))
    elif phase == "main":
        for m in MODELS:
            for meth in METHODS:
                for sub in SUBSETS:
                    todo.append((f"main:{m}:{meth}:{sub}",
                                ["--model", m, "--method", meth, "--bench", "sew",
                                 "--subset", sub, "--data", DATA, "--budget", "4096"]))
    elif phase == "ablation":
        for meth in ABLATIONS:
            for sub in SUBSETS:
                todo.append((f"abl:{meth}:{sub}",
                            ["--model", FLAGSHIP, "--method", meth, "--bench", "sew",
                             "--subset", sub, "--data", DATA, "--budget", "4096",
                             "--out", "results/ablation.json"]))
    elif phase == "sweep":
        # Figure 6(a) is a budget-capability CURVE, so it needs more than the 4k and 16k
        # points the main grid and P3 already have. Flagship only: the sweep is on the
        # priciest backbone and the claim it supports is about budget, not about scale.
        for b in ("1024", "2048", "8192", "16384"):
            for meth in ("uniform16", "asp"):
                for sub in SUBSETS:
                    outfile = f"results/sweep_B{b}.json"
                    todo.append((f"sweep:{meth}@{b}:{sub}",
                                 ["--model", FLAGSHIP, "--method", meth, "--bench", "sew",
                                  "--subset", sub, "--data", DATA, "--budget", b,
                                  "--out", outfile]))
    elif phase == "p3":
        for m in MODELS:
            for sub in SUBSETS:
                todo.append((f"p3:{m}:uniform16@16k:{sub}",
                            ["--model", m, "--method", "uniform16", "--bench", "sew",
                             "--subset", sub, "--data", DATA, "--budget", "16384",
                             "--out", "results/budget16k.json"]))
    else:
        raise SystemExit(f"unknown phase {phase}")
    if only_subset:
        if phase == "offline":
            raise SystemExit("--only-subset is meaningless for the offline phase: the "
                             "keyframe caches carry no question and serve every subtest")
        todo = [t for t in todo if t[0].endswith(f":{only_subset}")]
        if not todo:
            raise SystemExit(f"no {phase} cells for subset {only_subset}")
    return todo


def run_one(name: str, argv: list[str], resume: bool, log_dir: pathlib.Path) -> tuple:
    cmd = RUN + argv + ["--tau-g", str(TAU_G)] + (["--resume"] if resume else [])
    log = log_dir / (name.replace(":", "__").replace("@", "_at_") + ".log")
    t0 = time.time()
    with log.open("w") as fh:
        r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
    return name, r.returncode, round(time.time() - t0, 1), log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True,
                    choices=["offline", "main", "ablation", "p3", "sweep"])
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--only-subset", dest="only_subset", default=None,
                    choices=["RET", "TRK", "CMP"],
                    help="re-run just one witness subtest. Used for the CMP re-run after "
                         "the corpus fix of notes/deviations.md D-43/D-45.")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is not set")
    os.environ.setdefault("JUDGE_MODEL", "google/gemma-3-27b-it")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    if a.phase == "offline" and not a.dry_run:
        # Embed every frame once, in one process, before fanning out. Twenty-four jobs each
        # embedding the same 300 frames with torch on all cores is what drove the load
        # average to ~1,400; done once it takes 25 s for the whole corpus.
        subprocess.run([sys.executable, "-u", str(ROOT / "scripts/warm_embeddings.py"),
                        DATA], cwd=ROOT, check=True)

    todo = jobs_for(a.phase, a.only_subset)
    log_dir = ROOT / "results/logs" / a.phase
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"[grid] phase={a.phase} cells={len(todo)} jobs={a.jobs} "
          f"resume={a.resume} logs={log_dir}")
    if a.dry_run:
        for n, argv in todo:
            print("   ", n, " ".join(argv))
        return

    ok, bad = 0, []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(run_one, n, argv, a.resume, log_dir) for n, argv in todo]
        for i, f in enumerate(cf.as_completed(futs), 1):
            name, rc, secs, log = f.result()
            if rc == 0:
                ok += 1
                print(f"[{i}/{len(todo)}] OK   {name}  {secs}s")
            else:
                bad.append((name, log))
                tail = log.read_text(errors="replace").strip().splitlines()[-2:]
                print(f"[{i}/{len(todo)}] FAIL {name}  rc={rc}  {secs}s\n"
                      f"        {' | '.join(t[:150] for t in tail)}")
    print(f"\n[grid] {a.phase}: {ok} ok, {len(bad)} failed")
    for name, log in bad:
        print(f"   FAILED {name}  -> {log}")
    (ROOT / f"results/logs/{a.phase}_summary.json").write_text(
        json.dumps({"ok": ok, "failed": [n for n, _ in bad]}, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
