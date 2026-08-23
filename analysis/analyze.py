#!/usr/bin/env python3
"""Post-run analysis: the wall checks, the headline predictions P1-P3, and the
falsification criteria F1-F4 (paper Sec. 5.2 / 5.5).

Reads results/cells/*.json -- the PER-QUESTION records -- because every registered
headline is a paired test on per-question deltas, not a comparison of two means. Prints
a verdict table and writes analysis/verdicts.json for the camera-ready diff.

Wall checks come first and are separate from the predictions: a prediction can be
confirmed while the theorem it was derived from says nothing at these corpus parameters
(that is exactly what happened at d=9, where kappa_s = 1.85 made Thm. 1 vacuous), and
conflating the two would let a measured number stand in for a bound it never tested.
"""
from __future__ import annotations
import json
import math
import pathlib
import statistics

from scipy.stats import wilcoxon

ROOT = pathlib.Path(__file__).resolve().parents[1]
CELLS = ROOT / "results/cells"
SUBSETS = ["RET", "TRK", "CMP"]
PARAMS = {"ministral-3b": 3, "qwen3-vl-8b": 8, "gemma-3-12b": 12, "ministral-14b": 14,
          "qwen3.8-27b": 27, "qwen3-vl-30b-a3b": 30, "gemma-4-31b": 31}
FLAGSHIP = "qwen3.8-27b"
ALPHA = 0.01                        # registered

# SEW-Bench corpus parameters (annotation/generate_synthetic.py, data/sew/meta.json)
N_FRAMES, D_ATTR, K = 300, 32, 8
L_S, BITS_PER_TOKEN = 512, 12.0
M_BITS = L_S * BITS_PER_TOKEN


def load(model, method, subset, budget=4096):
    f = CELLS / f"{model}__{method}__sew_{subset}__B{budget}.json"
    return json.loads(f.read_text()) if f.exists() else None


def scores(model, method, subset, budget=4096):
    c = load(model, method, subset, budget)
    return [r["score"] for r in c["items"]] if c else None


def mean(model, method, subset, budget=4096):
    v = scores(model, method, subset, budget)
    return statistics.fmean(v) if v else None


def mean_clean(model, method, subset, budget=4096):
    """Cell mean restricted to items whose gold is not answerable without the stream.

    Identical to mean() on RET and TRK, which carry no degenerate golds; on CMP it drops
    the eight before/after items of D-43. Exists so that F3 -- a criterion about the SHAPE
    of the ablation matrix -- can be recomputed on uncontaminated items from the released
    records, without re-running a single cell.
    """
    c = load(model, method, subset, budget)
    if not c:
        return None
    v = [r["score"] for r in c["items"] if not is_degenerate(r)]
    return statistics.fmean(v) if v else None


def grand(model, method, budget=4096):
    vs = [mean(model, method, s, budget) for s in SUBSETS]
    vs = [v for v in vs if v is not None]
    return statistics.fmean(vs) if vs else None



# Items answerable WITHOUT the stream, i.e. beatable by a constant answer. This used to be
# the hardcoded set {"before", "after"} -- correct only by accident, because in the pre-fix
# corpus every before/after item carried the gold "before" (D-43). Keyed on the answer VALUE
# that predicate is meaningless the moment the corpus is balanced: it would flag all eight
# items of a 4-4 slice as degenerate and quietly delete a third of the subtest.
#
# So degeneracy is now MEASURED from whichever corpus is on disk, with the same statistic the
# generator's answerability gate uses: group items by (subset, answer alphabet), and flag a
# slice whose most common gold beats a Bonferroni-corrected binomial tail at that alphabet's
# K. The max-over-k-categories form matters -- a per-category tail cries wolf at K=8 (see
# annotation/generate_synthetic.py). On the pre-fix corpus this flags exactly the eight
# before/after items; on the corrected corpus it flags nothing, and every "clean" statistic
# below collapses to its plain counterpart, which is the intended behaviour rather than a bug.
CORPUS = ROOT / "data/sew/questions.json"
_TAGS_K, _COLOURS_K = 8, 8


def _alphabet(gold: str):
    g = str(gold).strip().lower()
    if g in ("before", "after"):
        return "before/after", 2
    if g in ("open", "closed"):
        return "open/closed", 2
    if g.isdigit():
        return None                          # integer counts have no fixed alphabet
    if len(g) == 1 and g.isalpha():
        return "letter", _TAGS_K
    return "colour", _COLOURS_K


def _degenerate_keys(path=CORPUS) -> set:
    """(episode, question) keys sitting in a slice a constant answer beats."""
    if not path.exists():
        return set()
    items = json.loads(path.read_text())
    buckets: dict = {}
    for it in items:
        a = _alphabet(it["answer"])
        if a is None:
            continue
        buckets.setdefault((it["subset"], *a), []).append(it)
    flagged = set()
    for (sub, _name, k), group in buckets.items():
        n = len(group)
        if n < 4:
            continue
        counts: dict = {}
        for it in group:
            g = str(it["answer"]).strip().lower()
            counts[g] = counts.get(g, 0) + 1
        hits = max(counts.values())
        tail = sum(math.comb(n, i) * (1.0 / k) ** i * (1 - 1.0 / k) ** (n - i)
                   for i in range(hits, n + 1))
        if tail * k < 0.05:
            flagged |= {(it["episode"], it["question"]) for it in group}
    return flagged


DEGENERATE_KEYS = _degenerate_keys()


def is_degenerate(rec) -> bool:
    return (rec.get("episode"), rec.get("q")) in DEGENERATE_KEYS


def holm(pvals: dict, alpha: float = ALPHA) -> dict:
    """Holm-Bonferroni over a family of tests. Reported alongside the uncorrected values
    because the paper runs 7 backbones x 6 baselines = 42 paired tests at alpha=0.01 and
    quoted each one against alpha unadjusted. Holm rather than plain Bonferroni: it is
    uniformly more powerful and needs no independence assumption."""
    items = sorted(((k, v) for k, v in pvals.items() if v is not None), key=lambda kv: kv[1])
    m, out, rejected_so_far = len(items), {}, True
    for i, (k, p) in enumerate(items):
        thresh = alpha / (m - i)
        if rejected_so_far and p <= thresh:
            out[k] = dict(p=p, threshold=thresh, sig_holm=True)
        else:
            rejected_so_far = False
            out[k] = dict(p=p, threshold=thresh, sig_holm=False)
    for k, v in pvals.items():
        if v is None:
            out[k] = dict(p=None, threshold=None, sig_holm=False)
    return out


def paired(model, a, b, budget_a=4096, budget_b=4096, subsets=None,
           drop_degenerate=False):
    """One-sided Wilcoxon signed-rank on per-question deltas: is `a` > `b`?

    `drop_degenerate` removes the items whose gold is answerable without the stream
    (DEGENERATE_GOLDS); it is how the restricted CMP reading is computed from the same
    per-question records rather than from a second run."""
    xs, ys = [], []
    for sub in (subsets or SUBSETS):
        ca, cb = load(model, a, sub, budget_a), load(model, b, sub, budget_b)
        if not ca or not cb:
            continue
        by_q = {r["q"]: r["score"] for r in cb["items"]}
        for r in ca["items"]:
            if drop_degenerate and is_degenerate(r):
                continue
            if r["q"] in by_q:
                xs.append(r["score"])
                ys.append(by_q[r["q"]])
    if len(xs) < 6 or all(x == y for x, y in zip(xs, ys)):
        return dict(n=len(xs), delta=None, p=None,
                    note="no variation in the paired deltas" if xs else "no paired items")
    st = wilcoxon(xs, ys, alternative="greater", zero_method="wilcox")
    return dict(n=len(xs), delta=round(statistics.fmean(xs) - statistics.fmean(ys), 2),
                p=float(st.pvalue), sig=bool(st.pvalue < ALPHA))


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def walls(v: dict):
    models = [m for m in PARAMS if load(m, "asp", "RET")]
    kappa = (M_BITS / (N_FRAMES * D_ATTR) + 1) / math.log2(K)
    v["thm1_kappa_s"] = round(kappa, 3)
    v["thm1_binds"] = kappa < 1.0
    v["thm1_state_only_RET"] = {m: mean(m, "state_only", "RET") for m in models}
    v["thm1_violations"] = [m for m in models
                            if (mean(m, "state_only", "RET") or 0) > 100 * kappa]

    v["thm2_ceiling_RET"] = {}
    for m in models:
        c = load(m, "uniform16", "RET")
        ws = [r["w_realised"] for r in (c["items"] if c else []) if r.get("w_realised")]
        if not ws:
            continue
        w = max(ws)
        ceil = 100 * (w / N_FRAMES + (1 - w / N_FRAMES) / K)
        v["thm2_ceiling_RET"][m] = dict(w=w, ceiling=round(ceil, 1),
                                        measured=mean(m, "uniform16", "RET"),
                                        under_bound=(mean(m, "uniform16", "RET") or 0) <= ceil)

    v["lem3_ceiling_TRK"] = round(100 / K, 1)
    v["lem3_retr_only_TRK"] = {m: mean(m, "retr_only", "TRK") for m in models}

    v["cor1_dominance"] = {}
    for m in models:
        best = max([grand(m, "state_only") or 0, grand(m, "retr_only") or 0])
        a = grand(m, "asp")
        v["cor1_dominance"][m] = dict(asp=round(a, 1) if a else None,
                                      best_single=round(best, 1),
                                      gap=round((a or 0) - best, 1))


def main():
    v: dict = {}
    models = [m for m in PARAMS if load(m, "asp", "RET")]
    v["backbones_measured"] = models
    if not models:
        raise SystemExit("[analyze] no cells in results/cells -- run scripts/run_grid.py first")

    walls(v)

    # ---- P1 / F1: the embodied scissors gap on SEW-RET ----
    v["P1"] = {m: dict(state_only=mean(m, "state_only", "RET"),
                       uniform=mean(m, "uniform16", "RET"),
                       asp=mean(m, "asp", "RET"),
                       gap_asp_minus_uniform=round((mean(m, "asp", "RET") or 0)
                                                   - (mean(m, "uniform16", "RET") or 0), 1))
               for m in models}
    big = [m for m in models if PARAMS[m] >= 27]
    v["F1_uniform_within_10_of_asp_on_a_big_backbone"] = [
        m for m in big
        if (mean(m, "asp", "RET") or 0) - (mean(m, "uniform16", "RET") or 0) < 10]

    # ---- P2 / F2: capability convergence ----
    xs = [PARAMS[m] for m in models]
    v["P2_rho_scale"] = {}
    for method in ("uniform16", "asp"):
        ys = [grand(m, method) for m in models]
        if all(y is not None for y in ys):
            v["P2_rho_scale"][method] = round(spearman(xs, ys), 3)
    if len(v["P2_rho_scale"]) == 2:
        drop = v["P2_rho_scale"]["uniform16"] - v["P2_rho_scale"]["asp"]
        v["P2_rho_drop"] = round(drop, 3)
        v["F2_pass"] = drop >= 0.2

    # ---- P3 / F4: reallocation beats growth ----
    v["P3"] = {}
    for m in models:
        a, u = grand(m, "asp", 4096), grand(m, "uniform16", 16384)
        if a is None or u is None:
            continue
        # P3 asks whether restructuring access beats BUYING CONTEXT. On a backbone whose
        # provider caps images per request, the extra budget cannot buy context at all, so
        # the cell measures the cap and not the question. Flag it and keep it out of the
        # verdict, rather than letting a constraint we do not control read as confirmation.
        lims = []
        for sub in SUBSETS:
            c = load(m, "uniform16", sub, 16384)
            if c:
                lims += [r["w_limited_by"] for r in c["items"] if r.get("w_limited_by")]
        capped = bool(lims) and lims.count("provider") > len(lims) / 2
        v["P3"][m] = dict(asp_4k=round(a, 1), uniform_16k=round(u, 1),
                          delta=round(a - u, 1), provider_capped=capped,
                          test=paired(m, "asp", "uniform16", 4096, 16384))
    v["P3_excluded_provider_capped"] = [m for m, d in v["P3"].items() if d["provider_capped"]]
    v["F4_uniform16k_beats_asp4k"] = [m for m, d in v["P3"].items()
                                      if d["delta"] <= 0 and not d["provider_capped"]]

    # ---- F3: the ablation collapse pattern must not be crossed ----
    expect = {"asp_no_cv": "RET", "asp_no_cs": "TRK", "asp_r1": "CMP"}

    def f3_matrix(cell):
        """The collapse matrix under a given cell statistic (all items, or clean items)."""
        out = {}
        for var, sub in expect.items():
            full = {s: cell(FLAGSHIP, "asp", s) for s in SUBSETS}
            abl = {s: cell(FLAGSHIP, var, s) for s in SUBSETS}
            if any(x is None for x in list(full.values()) + list(abl.values())):
                continue
            drops = {s: round(full[s] - abl[s], 1) for s in SUBSETS}
            worst = max(drops, key=lambda s: drops[s])
            out[var] = dict(expected=sub, largest_drop=worst, drops=drops,
                            pattern_holds=worst == sub)
        return out

    v["F3"] = f3_matrix(mean)
    v["F3_pass"] = all(d["pattern_holds"] for d in v["F3"].values()) if v["F3"] else None

    # The same criterion on the 16 non-degenerate CMP items. This is the answer to the
    # obvious objection that F3's verdict was computed on a contaminated subtest: the
    # criterion is an ARGMAX over the three drops of one ablation, so it moves only if the
    # restriction changes which column is largest. It does not -- see D-43 in the paper.
    v["F3_clean"] = f3_matrix(mean_clean)
    v["F3_clean_pass"] = (all(d["pattern_holds"] for d in v["F3_clean"].values())
                          if v["F3_clean"] else None)
    v["F3_verdict_invariant"] = (
        v["F3_pass"] == v["F3_clean_pass"]
        and all(v["F3"][k]["pattern_holds"] == v["F3_clean"][k]["pattern_holds"]
                and v["F3"][k]["largest_drop"] == v["F3_clean"][k]["largest_drop"]
                for k in v["F3"] if k in v["F3_clean"])
    ) if v["F3"] and v["F3_clean"] else None

    # Flagship ablation CMP levels, both readings, for the abstract and Sec. 5.
    v["cmp_flagship"] = {
        var: dict(all=round(mean(FLAGSHIP, var, "CMP") or -1, 1),
                  clean=round(mean_clean(FLAGSHIP, var, "CMP") or -1, 1))
        for var in ("asp", "asp_no_cs", "asp_no_cv", "asp_no_rho", "asp_r1", "retr_only")
        if mean(FLAGSHIP, var, "CMP") is not None
    }

    # ---- ASP vs every baseline, paired, per backbone ----
    BASELINES = ("blind", "uniform16", "socratic", "retr_only", "state_only", "egagent")
    v["paired_vs_asp"] = {m: {b: paired(m, "asp", b) for b in BASELINES} for m in models}

    # Holm-Bonferroni over the WHOLE family actually reported. 7 backbones x 6 baselines is
    # 42 tests; quoting each against an unadjusted alpha=0.01 inflates the family-wise error
    # rate to roughly 1-(0.99)^42 = 34%. The corrected column is what any claim in Sec. 5
    # should rest on.
    fam = {f"{m}|{b}": v["paired_vs_asp"][m][b].get("p") for m in models for b in BASELINES}
    v["holm"] = holm(fam)
    v["n_tests"] = len(fam)
    for m in models:
        for b in BASELINES:
            v["paired_vs_asp"][m][b]["sig_holm"] = v["holm"][f"{m}|{b}"]["sig_holm"]
    v["holm_survivors"] = sum(1 for k in v["holm"] if v["holm"][k]["sig_holm"])
    v["holm_uncorrected"] = sum(1 for m in models for b in BASELINES
                                if v["paired_vs_asp"][m][b].get("sig"))

    # What the D-43 defect was actually worth, now that the affected cells have been re-run
    # against the corrected corpus. This is the only place the superseded cells are read: the
    # pre-fix CMP column is kept in results/cells_pre_cmpfix/ so the size of a measurement
    # error can be reported rather than merely regretted. Both columns are 24 items at chance
    # 25.0% -- balancing the before/after golds removes an exploitable PRIOR (a constant now
    # scores 50% on that slice instead of 100%), it does not move the chance level.
    PRE = ROOT / "results/cells_pre_cmpfix"
    v["CMP_prepost"] = {}
    if PRE.exists():
        for m in models:
            row = {}
            for meth in ("asp", "retr_only", "blind", "uniform16", "state_only", "socratic",
                         "egagent"):
                f = PRE / f"{m}__{meth}__sew_CMP__B4096.json"
                post = mean(m, meth, "CMP")
                if not f.exists() or post is None:
                    continue
                pre = statistics.fmean([r["score"]
                                        for r in json.loads(f.read_text())["items"]])
                row[meth] = dict(pre=round(pre, 1), post=round(post, 1),
                                 delta=round(post - pre, 1))
            if row:
                v["CMP_prepost"][m] = row
        # Flagship ablations too: F3 and the abstract live on these.
        v["CMP_prepost_abl"] = {}
        for meth in ("asp", "asp_no_cs", "asp_no_cv", "asp_no_rho", "asp_r1", "asp_r5",
                     "asp_rand_retr"):
            f = PRE / f"{FLAGSHIP}__{meth}__sew_CMP__B4096.json"
            post = mean(FLAGSHIP, meth, "CMP")
            if not f.exists() or post is None:
                continue
            pre = statistics.fmean([r["score"] for r in json.loads(f.read_text())["items"]])
            v["CMP_prepost_abl"][meth] = dict(pre=round(pre, 1), post=round(post, 1),
                                              delta=round(post - pre, 1))

    # CMP restricted to the items whose gold is not answerable without the stream (D-43).
    v["CMP_clean"] = {}
    for m in models:
        row = {}
        for meth in ("asp", "retr_only", "blind", "uniform16", "state_only", "egagent"):
            c = load(m, meth, "CMP")
            if not c:
                continue
            keep = [r["score"] for r in c["items"] if not is_degenerate(r)]
            drop = [r["score"] for r in c["items"] if is_degenerate(r)]
            row[meth] = dict(n_kept=len(keep), n_dropped=len(drop),
                             mean_all=round(c["mean"], 1),
                             mean_clean=round(statistics.fmean(keep), 1) if keep else None,
                             mean_dropped=round(statistics.fmean(drop), 1) if drop else None)
        v["CMP_clean"][m] = row
    v["CMP_clean_paired_asp_vs_retr"] = {
        m: paired(m, "asp", "retr_only", subsets=["CMP"], drop_degenerate=True)
        for m in models}

    (ROOT / "analysis/verdicts.json").write_text(json.dumps(v, indent=2))
    splice_verdicts(v, models)
    report(v, models)
    print("\n[analyze] wrote analysis/verdicts.json (full detail)")


PAPER = ROOT / "paper/asp/asp.tex"
MODEL_TEX = {"ministral-3b": r"Ministral~3B", "qwen3-vl-8b": r"Qwen3-VL-8B",
             "gemma-3-12b": r"Gemma~3~12B", "ministral-14b": r"Ministral~14B",
             "qwen3.8-27b": r"Qwen3.8-27B",
             "qwen3-vl-30b-a3b": r"Qwen3-VL-30B-A3B", "gemma-4-31b": r"Gemma~4~31B"}


def splice_verdicts(v: dict, models: list):
    r"""Write the F1-F4 outcomes into asp.tex as \newcommands.

    Sec 5.5 has to say whether each frozen criterion fired. Typing that by hand is exactly
    the place where a paper starts disagreeing with its own data -- and here the direction of
    the error is always flattering, because the author knows which answer they want. So the
    sentences are assembled from verdicts.json and the prose only references them."""
    def names(keys):
        return ", ".join(MODEL_TEX.get(k, k) for k in keys)

    f1 = v.get("F1_uniform_within_10_of_asp_on_a_big_backbone") or []
    f4 = v.get("F4_uniform16k_beats_asp4k") or []
    out = {
        "VFone": (rf"\textbf{{fires}} on {names(f1)}" if f1 else "does not fire"),
        "VFtwo": ("does not fire" if v.get("F2_pass") else r"\textbf{fires}")
                 if "F2_pass" in v else "not evaluated",
        "VFthree": ("does not fire" if v.get("F3_pass") else r"\textbf{fires}")
                   if v.get("F3") else "not evaluated",
        "VFthreeClean": ("does not fire" if v.get("F3_clean_pass") else r"\textbf{fires}")
                        if v.get("F3_clean") else "not evaluated",
        "VFthreeInvariant": ("unchanged" if v.get("F3_verdict_invariant") else
                             r"\textbf{changed}"),
        "VFfour": (rf"\textbf{{fires}} on {names(f4)}" if f4 else "does not fire"),
        "VrhoUnif": f"{v['P2_rho_scale'].get('uniform16', float('nan')):+.2f}"
                    if "uniform16" in v.get("P2_rho_scale", {}) else "--",
        "VrhoAsp": f"{v['P2_rho_scale'].get('asp', float('nan')):+.2f}"
                   if "asp" in v.get("P2_rho_scale", {}) else "--",
        "VrhoDrop": f"{v['VrhoDropRaw']:.2f}" if "VrhoDropRaw" in v
                    else (f"{v['P2_rho_drop']:.2f}" if "P2_rho_drop" in v else "--"),
        "VthmOneViol": ("no backbone exceeds it"
                        if not v.get("thm1_violations")
                        else rf"exceeded by {names(v['thm1_violations'])}"),
    }
    # Flagship ASP-vs-Uniform paired test, quoted in the main-results paragraph.
    t = (v.get("paired_vs_asp", {}).get(FLAGSHIP, {}) or {}).get("uniform16", {})
    out["VpairedFlagDelta"] = f"{t['delta']:+.1f}" if t.get("delta") is not None else "--"
    out["VpairedFlagP"] = (f"{t['p']:.1e}".replace("e-0", r"\times10^{-").replace("e-", r"\times10^{-") + "}"
                           if t.get("p") is not None else "--")
    out["VpairedFlagN"] = t.get("n", "--")
    # How many of the six backbones show ASP > every baseline, significantly.
    base = ["blind", "uniform16", "socratic", "retr_only", "state_only", "egagent"]
    dom = [m for m in models
           if all((v["paired_vs_asp"][m].get(b, {}).get("delta") or -1) > 0 for b in base)]
    sig = [m for m in models
           if all(v["paired_vs_asp"][m].get(b, {}).get("sig") for b in base)]
    out["VdomCount"], out["VsigCount"] = len(dom), len(sig)
    out["VnBackbones"] = len(models)
    # Multiple-comparison accounting, so Sec. 5 cannot quote an uncorrected count.
    out["VnTests"] = v.get("n_tests", "--")
    out["VsigUncorr"] = v.get("holm_uncorrected", "--")
    out["VsigHolm"] = v.get("holm_survivors", "--")
    rh = [d for d in (v["paired_vs_asp"][m].get("retr_only") for m in models) if d]
    out["VretrHolmSurv"] = sum(1 for d in rh if d.get("sig_holm"))
    out["VretrRawSurv"] = sum(1 for d in rh if d.get("sig"))
    out["VretrNeg"] = sum(1 for d in rh if (d.get("delta") or 0) < 0)
    # Flagship CMP, both readings, so the abstract cannot quote only the contaminated one.
    cf = v.get("cmp_flagship", {})
    for key, mac in (("asp", "AspCmp"), ("asp_no_cs", "NoCsCmp"), ("asp_r1", "RoneCmp"),
                     ("asp_no_cv", "NoCvCmp"), ("asp_no_rho", "NoRhoCmp")):
        d = cf.get(key, {})
        out["V" + mac + "All"] = f"{d['all']:.1f}" if d else "--"
        out["V" + mac + "Clean"] = f"{d['clean']:.1f}" if d else "--"

    # \renewcommand, because make_tables.py has already \providecommand-ed defaults.
    body = "\n".join(rf"\renewcommand{{\{k}}}{{{val}}}" for k, val in out.items())
    src = PAPER.read_text(encoding="utf-8")
    b, e = ("% ===== BEGIN GENERATED VERDICTS",
            "% ===== END GENERATED VERDICTS =====")
    i, j = src.find(b), src.find(e)
    if i < 0 or j < 0:
        print("[analyze] WARNING: VERDICTS markers not found in asp.tex; "
              "Sec 5.5 will keep whatever it had")
        return
    head = src.find("\n", i) + 1
    PAPER.write_text(src[:head] + body + "\n" + src[j:], encoding="utf-8")
    print(f"[analyze] spliced {len(out)} verdict macros into paper/asp/asp.tex")


def _f(x, w=6, nd=1):
    return f"{x:{w}.{nd}f}" if isinstance(x, (int, float)) else f"{'--':>{w}}"


def report(v, models):
    """Human-readable summary. The JSON stays the artefact of record; this is what a
    reader (or an author writing Sec 5.6) should be able to check the prose against."""
    print("=" * 78)
    print("WALL CHECKS  (a bound that does not bind cannot be evidence for anything)")
    print("=" * 78)
    k = v["thm1_kappa_s"]
    print(f"Thm 1  Shannon      kappa_s = {k:.3f}  "
          f"({'BINDS' if v['thm1_binds'] else 'VACUOUS'}): State-only RET <= {100*k:.1f}%")
    for m in models:
        so = v["thm1_state_only_RET"].get(m)
        flag = "  <-- ABOVE THE CEILING" if m in v["thm1_violations"] else ""
        print(f"         {m:20s} State-only RET = {_f(so)}{flag}")
    print()
    print(f"Thm 2  Horizon      ceiling = w/N + (1-w/N)/K at N=300, K=8")
    for m, d in v["thm2_ceiling_RET"].items():
        print(f"         {m:20s} w={d['w']:3d}  ceiling {_f(d['ceiling'])}  "
              f"measured {_f(d['measured'])}  {'under' if d['under_bound'] else 'OVER'}")
    print()
    print(f"Lem 3  No tracking without C_s: Retr-only TRK <= "
          f"{v['lem3_ceiling_TRK']}%  (1/K)")
    for m in models:
        print(f"         {m:20s} Retr-only TRK = {_f(v['lem3_retr_only_TRK'].get(m))}")
    print()
    print("Cor 1  Dominance over the BETTER single channel (mean over subtests)")
    for m, d in v["cor1_dominance"].items():
        print(f"         {m:20s} ASP {_f(d['asp'])}  best single {_f(d['best_single'])}  "
              f"gap {_f(d['gap'])}")

    print()
    print("=" * 78)
    print("REGISTERED PREDICTIONS")
    print("=" * 78)
    print("P1 scissors gap on RET")
    for m, d in v["P1"].items():
        print(f"   {m:20s} State-only {_f(d['state_only'])}  Uniform {_f(d['uniform'])}  "
              f"ASP {_f(d['asp'])}   ASP-Uniform {_f(d['gap_asp_minus_uniform'])}")
    f1 = v["F1_uniform_within_10_of_asp_on_a_big_backbone"]
    print(f"   F1 (fires if Uniform within 10 pts of ASP on a >=27B backbone): "
          f"{'FIRES on ' + ', '.join(f1) if f1 else 'does not fire'}")
    print()
    if "P2_rho_drop" in v:
        r = v["P2_rho_scale"]
        print(f"P2 convergence   rho(params, score): Uniform {r['uniform16']:+.2f} -> "
              f"ASP {r['asp']:+.2f}   drop {v['P2_rho_drop']:+.2f}")
        print(f"   F2 (fires if the drop is < 0.20): "
              f"{'does not fire' if v['F2_pass'] else 'FIRES'}")
        print("   NOTE: the registered OpenEQA 8B-vs-27B sub-clause is NOT EVALUATED "
              "(benchmark not run)")
    print()
    print("P3 reallocation beats growth (ASP@4k vs Uniform-w@16k, mean over subtests)")
    for m, d in v["P3"].items():
        t = d["test"]
        sig = ("p=%.2g%s" % (t["p"], " *" if t.get("sig") else "")) if t.get("p") else t.get("note", "")
        print(f"   {m:20s} ASP@4k {_f(d['asp_4k'])}  Unif@16k {_f(d['uniform_16k'])}  "
              f"delta {_f(d['delta'])}   n={t['n']} {sig}")
    f4 = v["F4_uniform16k_beats_asp4k"]
    print(f"   F4 (fires where Uniform@16k >= ASP@4k): "
          f"{'FIRES on ' + ', '.join(f4) if f4 else 'does not fire'}")
    print("   NOTE: the registered OpenEQA clause is NOT EVALUATED (benchmark not run)")
    print()
    print("F3 ablation collapse pattern (largest drop must be in the predicted column)")
    for var, d in v["F3"].items():
        print(f"   {var:16s} expected {d['expected']}  largest drop {d['largest_drop']}  "
              f"{d['drops']}  {'OK' if d['pattern_holds'] else 'CROSSED'}")
    print(f"   F3: {'does not fire' if v.get('F3_pass') else 'FIRES'}")
    print("F3 recomputed on the 16 non-degenerate CMP items (D-43)")
    for var, d in v.get("F3_clean", {}).items():
        print(f"   {var:14s} expected {d['expected']}  largest drop {d['largest_drop']}  "
              f"{d['drops']}  {'ok' if d['pattern_holds'] else 'CROSSED'}")
    print(f"   F3(clean): {'does not fire' if v.get('F3_clean_pass') else 'FIRES'}"
          f"   -- verdict {'INVARIANT' if v.get('F3_verdict_invariant') else 'CHANGED'}")
    print()
    print("=" * 78)
    print("ASP vs each baseline, paired one-sided Wilcoxon over per-question scores "
          f"(alpha={ALPHA})")
    print("=" * 78)
    base = ["blind", "uniform16", "socratic", "retr_only", "state_only", "egagent"]
    print(f"{'backbone':20s}" + "".join(f"{b[:9]:>12s}" for b in base))
    for m in models:
        row = ""
        for b in base:
            t = v["paired_vs_asp"][m][b]
            if t.get("p") is None:
                row += f"{'--':>12s}"
            else:
                row += f"{t['delta']:+8.1f}{'*' if t['sig'] else ' ':>2s}  "
        print(f"{m:20s}{row}")
    print("   * = significant at alpha=%s; delta is the mean paired difference in points"
          % ALPHA)


if __name__ == "__main__":
    main()
