#!/usr/bin/env python3
"""Run one (backbone x method x benchmark) cell and append to results/measured.json.

Usage:
  export OPENROUTER_API_KEY=...
  python scripts/run_eval.py --model qwen3.8-27b --method asp \
      --bench ewbench --subset RET --data data/ewbench --budget 4096

  python scripts/run_eval.py --model qwen3.8-27b --method uniform16 \
      --bench openeqa --data data/openeqa --budget 4096

Benchmark adapters expect:
  openeqa  : data/openeqa/{questions.json, frames/<episode>/*.jpg} (EM-EQA setup;
             follow the official repo to dump episode frames), LLM-Match scored
             by scripts/llm_match.py with a judge model DISJOINT from backbones.
  vsibench / egoschema : analogous adapters (frames pre-extracted).
  ewbench  : produced by annotation/generate_ewbench.py.

Each finished cell writes measured.json in the SAME schema as
registered_predictions.json, so analysis/make_tables.py backfills the paper
automatically (dagger removed for measured cells).
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from openrouter_client import BudgetedSession, BudgetExhausted
from methods.asp import EpisodicIndex, SceneState, keyframe_gate, run_asp
from methods import baselines

ROOT = pathlib.Path(__file__).resolve().parents[1]
BENCH_COL = {"openeqa": 0, "vsibench": 1, "egoschema": 2,
             "ewbench:RET": 3, "ewbench:TRK": 4, "ewbench:CMP": 5,
             # SEW-Bench occupies the same three witness columns as EW-Bench: it is the
             # licence-free stand-in actually measured (annotation/generate_synthetic.py),
             # and the table header says so. EW-Bench itself needs habitat-sim + HM3D.
             "sew:RET": 3, "sew:TRK": 4, "sew:CMP": 5}

# Table 3 ablations. Each is the SAME run_asp loop with one component disabled, so a
# collapse is attributable to the removed component rather than to a different code path.
ABLATIONS = {
    "asp":             dict(),
    "asp_no_cv":       dict(use_cv=False),
    "asp_no_cs":       dict(use_cs=False),
    "asp_no_rho":      dict(use_router=False),
    "asp_r1":          dict(R=1),
    "asp_r5":          dict(R=5),
    "asp_rand_retr":   dict(random_retr=True),
}


def load_items(bench: str, data: pathlib.Path, subset: str | None):
    qfile = data / "questions.json"
    items = json.loads(qfile.read_text())
    if subset:
        items = [it for it in items if it.get("subset") == subset]
    # item schema: {episode, question, answer, subset?, frames_dir}
    return items


def build_stream(sess_factory, frames: list[str], need_state: bool, need_index: bool,
                 tau_g: float = 0.18, cache_key: str | None = None,
                 checkpoint_every: int = 20):
    """Per-episode offline phase: gate + bounded per-keyframe update calls.

    Update calls are metered separately (per-keyframe allowance), not from the
    per-decision budget, matching Def. 2's online/decision split.

    CACHED TO DISK, AND RESUMABLE. The online phase depends only on (backbone, episode,
    tau_g), not on the method or the subset, but run_eval is invoked once per (method,
    subset) cell -- so without a cache the same N update calls are paid once per method.
    At N=300 and ~5 s of provider latency per call an episode takes half an hour, so a
    crash at keyframe 280 must not throw away 280 paid calls: the cache is written every
    `checkpoint_every` keyframes and a PREFIX of the target keyframe list is resumed
    from rather than discarded.
    """
    keys = keyframe_gate(frames, tau_g=tau_g)
    print(f"[gate] tau_g={tau_g}: kept {len(keys)}/{len(frames)} frames")
    kf = [frames[i] for i in keys]

    cpath = (ROOT / "results/cache" / f"{cache_key}.json") if cache_key else None
    state, index, captions, start = SceneState(), EpisodicIndex(), [], 0
    if cpath is not None and cpath.exists():
        blob = json.loads(cpath.read_text())
        got = blob.get("kf") or []
        if got == kf[:len(got)]:
            state.state, captions, start = blob["state"], blob["captions"], len(got)
            if start >= len(kf):
                if need_index:
                    for f, c in zip(kf, captions):
                        index.add(f, c)
                print(f"[cache] reused online phase for {cache_key} "
                      f"({len(kf)} keyframes, 0 API calls)")
                return kf, state, index, captions
            print(f"[cache] resuming {cache_key} from keyframe {start}/{len(kf)}")
        else:
            print(f"[cache] {cache_key} does not prefix-match the current keyframes "
                  f"-- rebuilding from scratch")
            captions, start = [], 0

    if not (need_state or need_index):
        return kf, state, index, captions
    if need_index and kf:
        # Embed every keyframe in ONE batched pass. index.add() otherwise embeds one image
        # per call, which is both slower per image and repeated for each of the 40-odd
        # cells that read this episode.
        from methods.asp import embed_images
        embed_images(kf)
    for f, c in zip(kf[:start], captions):
        if need_index:
            index.add(f, c)

    # Sec 4.5 bounds ONE update call at L_s + L_x. That is a PER-CALL bound, not a pool:
    # sizing the pool at 912 x N assumed L_x = 400, but a real call costs
    # L_s(512) + image + instruction(~200) + output(<=512), so the pool ran dry around
    # keyframe 117 of 150 and BudgetExhausted escaped uncaught. Size it from the measured
    # per-image cost, and give the two-call frames (a state update that emits no CAPTION
    # needs a second call) room by budgeting 2x.
    probe = sess_factory(budget=1)
    per_kf = 2 * (SceneState().max_tokens + probe.img_tokens + 200 + 512)   # L_s + L_x
    upd = sess_factory(budget=per_kf * (len(kf) - start + 2))

    def flush():
        if cpath is None:
            return
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps({"kf": kf[:len(captions)], "state": state.state,
                                     "captions": captions}, indent=1))

    # Always build BOTH channels once: a single update call yields the state AND the
    # caption, so computing both is nearly free and makes the cache serve every method.
    for t in range(start, len(kf)):
        f = kf[t]
        try:
            cap = state.update(upd, f, t)
            if not cap:
                # 64 tokens could not hold a 16-object inventory, which is half the
                # reason v1 captions were unsearchable.
                from methods.asp import CAPTION_REQUEST
                cap = upd.chat(CAPTION_REQUEST.replace("CAPTION: ", "Describe this frame: "),
                               images=[f], max_completion=192, tag="caption")
        except BudgetExhausted:
            # Truncating the online phase is a real deviation, so say so loudly rather
            # than committing a cell built on a partial stream.
            print(f"[online] WARNING: allowance exhausted at keyframe {t}/{len(kf)}; "
                  f"the remaining keyframes are NOT in the state or the index")
            break
        captions.append(cap)
        index.add(f, cap)
        if (t + 1) % checkpoint_every == 0:
            flush()
            print(f"[online] {t+1}/{len(kf)} keyframes, {upd.spent} tokens spent")
    kf = kf[:len(captions)]
    flush()
    if cpath is not None:
        print(f"[cache] wrote {cpath.name} ({upd.spent} tokens, reusable by every cell)")
    return kf, state, index, captions


def answer_one(method: str, model: str, budget: int, kf, state, index, captions, q: str):
    sess = BudgetedSession(model, budget=budget)
    if method in ABLATIONS:
        return run_asp(sess, index, state, q, **ABLATIONS[method])["answer"], sess
    if method == "blind":
        return baselines.blind(sess, q), sess
    if method == "uniform16":
        # w = "as many uniformly spaced keyframes as B affords", not a hardcoded 16.
        # At the measured 259-432 tokens/frame, 16 frames do not fit B=4096 for ANY
        # backbone; and the B=16k arm of P3 must be allowed to spend its whole budget,
        # or "reallocation beats growth" would be tested against a crippled baseline.
        return baselines.uniform(sess, kf, q, w=None), sess
    if method == "socratic":
        return baselines.socratic(sess, captions, q), sess
    if method == "retr_only":
        return baselines.retr_only(sess, index, q), sess
    if method == "state_only":
        return baselines.state_only(sess, state, q), sess
    if method == "egagent":
        # Table 2's headline comparison. Was defined in baselines.py but wired to
        # nothing, so the paper's strongest baseline could not be run at all.
        return baselines.egagent_reimpl(sess, index, q,
                                        baselines.build_entity_graph(captions)), sess
    raise ValueError(method)


def score(bench: str, pred: str, gold: str, question: str = "") -> float:
    """Always returns a value already on the [0,100] scale.

    The previous version returned 0/1 for MCQ but [0,100] for LLM-Match, and commit()
    then multiplied everything except OpenEQA by 100 -- so every EW free-form cell
    (all of EW-CMP, and the non-MCQ ~20% of EW-RET/TRK) was inflated up to 100x.
    Normalising here means commit() never rescales anything."""
    if bench == "sew":
        # Registered metric for these three columns is ACCURACY, so match exactly; the
        # judge is only a fallback for phrasings the rule cannot resolve (scripts/sew_score.py).
        from sew_score import sew_score
        return sew_score(pred, gold, question)
    if bench in ("vsibench", "egoschema") or gold.strip().upper() in list("ABCDEFGH"):
        return 100.0 * float(pred.strip().upper().startswith(gold.strip().upper()))
    from llm_match import llm_match  # OpenEQA-style 1-5 judge -> [0,100]
    return llm_match(pred, gold, question)


def cell_path(model, method, bench, subset, budget):
    sub = f"_{subset}" if subset else ""
    return ROOT / "results/cells" / f"{model}__{method}__{bench}{sub}__B{budget}.json"


def commit(model: str, method: str, col: int, value: float, out_name: str | None = None):
    # docs/PILOT.md forbids pilot numbers reaching the paper. make_tables.py reads only
    # measured.json, so routing by file is what actually enforces it -- a rule that lives
    # only in prose gets broken by the first hurried run (it was, on the first smoke test).
    pilot = bool(os.environ.get("ASP_PILOT"))
    path = ROOT / (out_name or ("results/pilot.json" if pilot else "results/measured.json"))
    data = json.loads(path.read_text()) if path.exists() else {"main": {}}
    cell = data["main"].setdefault(model, {}).setdefault(method, {})
    meas = cell.setdefault("measured", [None] * 6)
    meas[col] = round(value, 1)
    path.write_text(json.dumps(data, indent=2))
    print(f"[commit] {path.name}: main.{model}.{method}.measured[{col}] = {value:.1f}"
          + ("   (PILOT -- never enters the paper)" if pilot else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--method", required=True,
                    choices=["blind", "uniform16", "socratic", "retr_only", "state_only",
                             "egagent"] + list(ABLATIONS))
    ap.add_argument("--bench", required=True,
                    choices=["openeqa", "vsibench", "egoschema", "ewbench", "sew"])
    ap.add_argument("--subset", default=None, help="RET|TRK|CMP for ewbench/sew")
    ap.add_argument("--data", required=True)
    ap.add_argument("--budget", type=int, default=4096)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--episode", default=None,
                    help="restrict to one episode; used to fan the offline phase out "
                         "across processes, since it is serial within an episode")
    ap.add_argument("--out", default=None,
                    help="results file to commit into; default measured.json "
                         "(pilot.json under ASP_PILOT). The B=16k arm of P3 writes its "
                         "own file so it can never overwrite the B=4k main table.")
    ap.add_argument("--resume", action="store_true",
                    help="skip the cell if its per-question record already exists")
    ap.add_argument("--build-cache-only", action="store_true",
                    help="run the offline phase for every episode and exit. Lets the N "
                         "per-keyframe update calls be paid ONCE, in parallel across "
                         "episodes, before the grid fans out over methods.")
    ap.add_argument("--tau-g", dest="tau_g", type=float, default=0.18,
                    help="keyframe-gate novelty threshold; calibrated per corpus (Sec 5.1). "
                         "0.18 targets N in [380,520] on EW-Bench walkthroughs and is far "
                         "too aggressive on short or synthetic streams; use 0 for a corpus "
                         "that already emits one frame per discrete moment.")
    args = ap.parse_args()

    cpath = cell_path(args.model, args.method, args.bench, args.subset, args.budget)
    if args.resume and cpath.exists() and not args.build_cache_only:
        print(f"[resume] {cpath.name} exists -- skipping")
        return

    items = load_items(args.bench, pathlib.Path(args.data), args.subset)
    if args.episode:
        items = [it for it in items if it["episode"] == args.episode]
    items = items[: args.limit]
    need_state = args.method in ("state_only",) or args.method in ABLATIONS
    need_index = args.method in ("retr_only", "socratic", "egagent") or args.method in ABLATIONS
    if args.build_cache_only:
        need_state = need_index = True

    def stream_for(it):
        frames = sorted(str(p) for p in pathlib.Path(it["frames_dir"]).glob("*.jpg"))
        # The caption schema is part of the key: v1 captions produce a different index
        # (see methods/asp.CAPTION_VERSION), and reusing them across a schema change
        # would mix two retrieval regimes inside one episode.
        from methods.asp import OFFLINE_VERSION
        ck = (f"{args.model}_{args.bench}_{it['episode']}_tau{args.tau_g}"
              f"_v{OFFLINE_VERSION}")
        return build_stream(lambda budget: BudgetedSession(args.model, budget),
                            frames, need_state, need_index,
                            tau_g=args.tau_g, cache_key=ck)

    cache: dict = {}
    if args.build_cache_only:
        for ep in dict.fromkeys(it["episode"] for it in items):
            it = next(x for x in items if x["episode"] == ep)
            stream_for(it)
        print(f"[cache] offline phase ready for {args.model} on {args.bench}")
        return

    recs = []
    for it in items:
        ep = it["episode"]
        if ep not in cache:
            cache[ep] = stream_for(it)
        kf, state, index, captions = cache[ep]
        try:
            pred, sess = answer_one(args.method, args.model, args.budget,
                                    kf, state, index, captions, it["question"])
        except BudgetExhausted as e:
            # A method that cannot fit B at all is a MEASUREMENT, not a crash: it scores
            # zero for that item and the reason is recorded. Uniform-w at 432 tokens/frame
            # is the case that actually happens.
            pred, sess = "", BudgetedSession(args.model, budget=args.budget)
            print(f"[budget] {args.method}: {e}")
        s = score(args.bench, pred, it["answer"], it["question"])
        # Sec 5.1 promises the REALISED w per cell and App. D registers a prediction about
        # the realised (B_s, B_r, B_c) split. Both live in sess.calls and were being
        # discarded, which made those two claims unreportable.
        plan = [c for c in sess.calls if c.get("tag") == "uniform_plan"]
        recs.append({"episode": ep, "subset": it.get("subset"), "q": it["question"],
                     "gold": it["answer"], "pred": pred, "score": s,
                     "spent": sess.spent, "n_calls": len(sess.calls),
                     "w_realised": plan[0]["w_realised"] if plan else None,
                     # Which constraint actually bound w. On the Mistral backbones the
                     # provider refuses more than 8 images per request, so at the 16k budget
                     # of the P3 growth arm w is provider-limited rather than budget-limited
                     # and that cell cannot speak to "reallocation beats growth". Recorded
                     # per item so analysis can exclude such cells by name rather than by
                     # my recollection of which endpoint had which limit.
                     "w_limited_by": plan[0].get("w_limited_by") if plan else None,
                     "split": sess.split()})
        print(f"  [{len(recs)}/{len(items)}] {s:5.1f}  gold={it['answer']!r} "
              f"pred={pred[:60]!r}")

    if not recs:
        raise SystemExit("[run_eval] no items scored -- refusing to commit an empty cell")
    mean = sum(r["score"] for r in recs) / len(recs)

    # Per-question records are what make the registered paired Wilcoxon tests possible;
    # a committed mean alone cannot support any of P1-P3's significance claims.
    cpath.parent.mkdir(parents=True, exist_ok=True)
    n_defer = 0
    if args.bench == "sew":
        from sew_score import DEFERRED
        n_defer = DEFERRED["n"]
    cpath.write_text(json.dumps({"model": args.model, "method": args.method,
                                 "bench": args.bench, "subset": args.subset,
                                 "budget": args.budget, "tau_g": args.tau_g,
                                 "judge_deferred": n_defer,
                                 "mean": round(mean, 2), "items": recs}, indent=1))
    print(f"[cell] wrote {cpath.name}  mean={mean:.1f}  n={len(recs)}  "
          f"judge-deferred={n_defer}/{len(recs)}")

    key = f"{args.bench}:{args.subset}" if args.bench in ("ewbench", "sew") else args.bench
    commit(args.model, args.method, BENCH_COL[key], mean, out_name=args.out)


if __name__ == "__main__":
    main()
