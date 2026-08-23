#!/usr/bin/env python3
"""Splice the data tables into paper/asp/asp.tex from results/cells/*.json.

asp.tex is a single complete file (no \\input components); every generated table is
rewritten in place between BEGIN/END GENERATED markers.

SINGLE SOURCE OF TRUTH is results/cells/ -- one JSON per (backbone, method, subset,
budget) holding the PER-QUESTION records. Cell means are recomputed here rather than
read from a summary file, so a table can never disagree with the records the paired
significance tests in analysis/analyze.py run on.

results/registered_predictions.json still supplies the dagger-marked predictions for the
three benchmarks that were registered but NOT run (OpenEQA, VSI-Bench, EgoSchema: no
licence-free data path). Those stay in the appendix as registered predictions instead of
being deleted, so the pre-registration remains auditable.

  python analysis/make_tables.py && cd paper/asp && latexmk -pdf asp.tex
"""
from __future__ import annotations
import json
import math
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
CELLS = ROOT / "results/cells"
PAPER = ROOT / "paper/asp/asp.tex"
REG = json.loads((ROOT / "results/registered_predictions.json").read_text())

SUBSETS = ["RET", "TRK", "CMP"]
BACKBONES = [
    ("ministral-3b",      r"Ministral~3B",        3),
    ("qwen3-vl-8b",       r"Qwen3-VL-8B",         8),
    ("gemma-3-12b",       r"Gemma~3~12B",        12),
    ("ministral-14b",     r"Ministral~14B",       14),
    ("qwen3.8-27b",       r"Qwen3.8-27B",        27),
    ("qwen3-vl-30b-a3b",  r"Qwen3-VL-30B-A3B",   30),
    ("gemma-4-31b",       r"Gemma~4~31B",        31),
]
FLAGSHIP = "qwen3.8-27b"
METHODS = [
    ("blind",      r"\textsc{Blind}"),
    ("uniform16",  r"\textsc{Uniform-}$w$"),
    ("socratic",   r"\textsc{Socratic}"),
    ("retr_only",  r"\textsc{Retr-only}"),
    ("state_only", r"\textsc{State-only}"),
    ("egagent",    r"\textsc{EGAgent} (reimpl.)"),
    ("asp",        r"\ASP{} (ours)"),
]
ABL = [
    ("asp",            r"\ASP{} (full)",                        None),
    ("asp_no_cv",      r"$-\ \cv$ (no episodic index)",         "RET"),
    ("asp_no_cs",      r"$-\ \cs$ (no scene state)",            "TRK"),
    ("asp_no_rho",     r"$-\ \rho$ (fixed 1/3 split)",          None),
    ("asp_r1",         r"$R{=}1$ (single pass)",                "CMP"),
    ("asp_r5",         r"$R{=}5$",                              None),
    ("asp_rand_retr",  r"random retrieval ($k{=}8$)",           None),
]


def load(model: str, method: str, subset: str, budget: int = 4096) -> dict | None:
    f = CELLS / f"{model}__{method}__sew_{subset}__B{budget}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def mean_of(model, method, subset, budget=4096):
    c = load(model, method, subset, budget)
    if not c or not c["items"]:
        return None
    return statistics.fmean(r["score"] for r in c["items"])


def fmt(v, bold=False, arrow=False):
    if v is None:
        return "--"
    s = f"{v:.1f}"
    if bold:
        s = rf"\textbf{{{s}}}"
    if arrow:
        s += r"\,$\downarrow$"
    return s


def splice(banner: str, body: str):
    src = PAPER.read_text(encoding="utf-8")
    begin, end = f"% ===== BEGIN GENERATED {banner}", f"% ===== END GENERATED {banner} ====="
    i, j = src.find(begin), src.find(end)
    if i < 0 or j < 0:
        raise SystemExit(
            f"[make_tables] FATAL: markers for {banner} not found in {PAPER}. "
            f"Restore the '% ===== BEGIN/END GENERATED {banner} =====' lines and re-run; "
            f"refusing to write a table nobody would see.")
    head_end = src.find("\n", i) + 1
    PAPER.write_text(src[:head_end] + body.rstrip("\n") + "\n" + src[j:], encoding="utf-8")


def realised_w(model: str) -> str:
    ws = []
    for sub in SUBSETS:
        c = load(model, "uniform16", sub)
        if c:
            ws += [r["w_realised"] for r in c["items"] if r.get("w_realised")]
    return str(max(ws)) if ws else "--"


def tab_main():
    n_items = {s: len(load(FLAGSHIP, "asp", s)["items"]) if load(FLAGSHIP, "asp", s) else 0
               for s in SUBSETS}
    lines = [
        r"\begin{table}[!htbp]",
        r"\centering\footnotesize\setlength{\tabcolsep}{5pt}",
        r"\caption{\textbf{SEW-Bench at a fixed per-decision budget $B{=}4{,}096$ tokens.} "
        r"Accuracy (\%) by exact match on the closed answer alphabet "
        r"(\S\ref{sec:setup}); $n{=}" + str(n_items["RET"]) + r"$ / $" + str(n_items["TRK"])
        + r"$ / $" + str(n_items["CMP"]) + r"$ questions for RET / TRK / CMP over four "
        r"$N{=}300$-frame episodes. \emph{Mean} is the unweighted mean of the three "
        r"witness subtests. \textsc{Uniform-}$w$ uses the largest $w$ the budget affords "
        r"at that backbone's measured tokens/frame (rightmost column); no backbone affords "
        r"the $w{=}16$ of the pre-registration. \textbf{Chance is $12.5\%$ on RET and TRK "
        r"($K{=}8$) but $25.0\%$ on CMP}, which mixes sixteen $K{=}8$ colour items with eight "
        r"binary ones whose golds are balanced $4$--$4$ by construction. The CMP cells here "
        r"are a re-run against the corrected corpus, after eight of those items were found to "
        r"carry a degenerate gold in the corpus first measured; "
        r"Table~\ref{tab:cmpfix} gives both runs and \S\ref{sec:cmpdefect} the account. "
        r"Every value is measured -- the "
        r"three registered benchmarks with no licence-free data path stay in "
        r"Table~\ref{tab:registered} as predictions.}",
        r"\label{tab:main}",
        r"\begin{tabular}{llcccc@{\hskip 10pt}c}",
        r"\toprule",
        r"Backbone & Method & SEW-RET & SEW-TRK & SEW-CMP & Mean & $w$ \\",
        r"\midrule",
    ]
    for bi, (model, tex, _p) in enumerate(BACKBONES):
        rows = []
        best = {}
        for sub in SUBSETS:
            vals = [(m, mean_of(model, m, sub)) for m, _ in METHODS]
            vals = [(m, v) for m, v in vals if v is not None]
            best[sub] = max((v for _, v in vals), default=None)
        for method, mtex in METHODS:
            cells = []
            for sub in SUBSETS:
                v = mean_of(model, method, sub)
                cells.append(fmt(v, bold=(v is not None and v == best[sub])))
            vs = [mean_of(model, method, s) for s in SUBSETS]
            mean = statistics.fmean([v for v in vs if v is not None]) if any(
                v is not None for v in vs) else None
            w = realised_w(model) if method == "uniform16" else ""
            rows.append(f" & {mtex} & " + " & ".join(cells) +
                        f" & {fmt(mean, bold=method == 'asp')} & {w} " + r"\\")
        lines.append(rf"\multirow{{{len(METHODS)}}}{{*}}{{{tex}}}")
        lines += rows
        if bi < len(BACKBONES) - 1:
            lines.append(r"\midrule")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    splice("TAB_MAIN", "\n".join(lines))


def tab_ablation():
    lines = [
        r"\begin{table}[!t]",
        r"\centering\small",
        r"\caption{\textbf{Ablations on " + FLAGSHIP.replace("qwen3.8-27b", "Qwen3.8-27B")
        + r", $B{=}4{,}096$.} Each variant is the same access loop with one component "
        r"disabled, so a drop is attributable to the removed component and not to a "
        r"different code path. $\downarrow$ marks the cell the pre-registration predicts "
        r"will collapse: $-\cv$ on RET (Thm.~\ref{thm:shannon}), $-\cs$ on TRK "
        r"(Lem.~\ref{lem:vtrack}), $R{=}1$ on CMP (Thm.~\ref{thm:rounds}).}",
        r"\label{tab:ablation}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Variant & SEW-RET & SEW-TRK & SEW-CMP & Mean \\",
        r"\midrule",
    ]
    for var, tex, collapse in ABL:
        cells, vs = [], []
        for sub in SUBSETS:
            v = mean_of(FLAGSHIP, var, sub)
            vs.append(v)
            cells.append(fmt(v, arrow=(collapse == sub)))
        mean = statistics.fmean([v for v in vs if v is not None]) if any(
            v is not None for v in vs) else None
        lines.append(f"{tex} & " + " & ".join(cells) + f" & {fmt(mean)} " + r"\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    splice("TAB_ABLATION", "\n".join(lines))


CAPPED_ROWS: list = []


def tab_p3():
    CAPPED_ROWS.clear()
    lines = [
        r"\begin{table}[!t]",
        r"\centering\small",
        r"\caption{\textbf{P3: reallocation versus growth.} \ASP{} at $B{=}4{,}096$ against "
        r"\textsc{Uniform-}$w$ given \emph{four times} the budget, $B{=}16{,}384$. A "
        r"positive $\Delta$ means restructuring access beats buying context.}",
        r"\label{tab:p3}",
        r"\begin{tabular}{lccc@{\hskip 10pt}c}",
        r"\toprule",
        r"Backbone & \ASP{} @ 4k & \textsc{Uniform-}$w$ @ 16k & $w$ @ 16k & $\Delta$ \\",
        r"\midrule",
    ]
    for model, tex, _p in BACKBONES:
        a = [mean_of(model, "asp", s) for s in SUBSETS]
        u = [mean_of(model, "uniform16", s, 16384) for s in SUBSETS]
        am = statistics.fmean([v for v in a if v is not None]) if any(a) else None
        um = statistics.fmean([v for v in u if v is not None]) if any(u) else None
        ws, lims = [], []
        for sub in SUBSETS:
            c = load(model, "uniform16", sub, 16384)
            if c:
                ws += [r["w_realised"] for r in c["items"] if r.get("w_realised")]
                lims += [r["w_limited_by"] for r in c["items"] if r.get("w_limited_by")]
        d = (am - um) if (am is not None and um is not None) else None
        # A row whose w was capped by the PROVIDER (Mistral refuses >8 images/request) cannot
        # test "reallocation beats growth": the growth arm was never allowed to grow. Mark it
        # and do not bold its delta, so the row is visible but not counted as support.
        capped = bool(lims) and lims.count("provider") > len(lims) / 2
        mark = r"$^{\ddagger}$" if capped else ""
        lines.append(f"{tex}{mark} & {fmt(am)} & {fmt(um)} & {max(ws) if ws else '--'} & "
                     f"{fmt(d, bold=(d is not None and d > 0 and not capped))} " + r"\\")
        if capped:
            CAPPED_ROWS.append(tex)
    lines += [r"\bottomrule"]
    if CAPPED_ROWS:
        lines += [r"\multicolumn{5}{@{}p{0.86\linewidth}@{}}{\footnotesize $^{\ddagger}$"
                  r"Provider caps this backbone at $8$ images per request, so at $B{=}16$k the "
                  r"\textsc{Uniform-}$w$ arm is limited by the endpoint and not by the budget: "
                  r"the growth arm was never allowed to grow, and the row is shown but does not "
                  r"count as support for P3. Affected: " + ", ".join(CAPPED_ROWS) + r".}\\"]
    lines += [r"\end{tabular}", r"\end{table}"]
    splice("TAB_P3", "\n".join(lines))


def tab_probe():
    """Assumption 1, MEASURED. Registered as a prediction and left unmeasured in the first
    pass; scripts/probe_assumption.py now measures it, and the reason it had to be measured is
    in notes/deviations.md D-42 -- a near-chance grid has two incompatible explanations and the
    grid alone cannot tell them apart."""
    src = ROOT / "results/probe.json"
    if not src.exists():
        print("[make_tables] no results/probe.json; leaving tab:probe as registered")
        return
    recs = json.load(open(src))
    rows, e0s, e1s = [], [], []
    for model, tex, _p in BACKBONES:
        rec = recs.get(model)
        if not rec:
            rows.append(f"{tex} & -- & -- \\\\")
            continue
        a = [r["score"] for r in rec["attr"] if r.get("score") is not None]
        st = [r["score"] for r in rec["step"] if r.get("score") is not None]
        f0 = f"{sum(a)/len(a):.2f} ({len(a)})" if a else "--"
        f1 = f"{sum(st)/len(st):.2f} ({len(st)})" if st else "--"
        if a:
            e0s.append(sum(a) / len(a))
        if st:
            e1s.append(sum(st) / len(st))
        # a one-step score at or below chance is flagged, not smoothed over
        if st and sum(st) / len(st) <= 0.5:
            f1 = r"\underline{" + f1 + "}"
        rows.append(f"{tex} & {f0} & {f1} \\\\")
    lo0, hi0 = (min(e0s), max(e0s)) if e0s else (0, 0)
    n_chance = sum(1 for v in e1s if v <= 0.5)
    lines = [
        r"\begin{table}[!t]",
        r"\centering\small",
        r"\caption{\textbf{Representational sufficiency (Assumption~\ref{ass:repr}), measured.} "
        r"Left: single-keyframe attribute accuracy $1-\epsilon_0$, the RET question asked "
        r"with the target frame handed to the model, which is the best case the assumption "
        r"describes (chance $1/K=12.5\%$). Right: one composition step $1-\epsilon_1$, two "
        r"in-context frames of the same class, which was seen earlier (chance $50\%$); scored "
        r"items in parentheses. "
        + (f"Attribute reading is comfortably sufficient at this scale, "
           f"${lo0:.2f}$--${hi0:.2f}$ against a $0.125$ floor, so a near-chance grid cell is "
           f"\\emph{{not}} explained by an inability to read a frame that is in context. "
           if e0s else "")
        + (f"The one-step column is the weak one: {n_chance} of {len(e1s)} backbones sit at or "
           r"below chance (\underline{underlined}), so for those the CMP family is limited by "
           r"composition and not only by access, and Proposition~\ref{prop:complete}'s "
           r"$1-d_q\epsilon_1$ bound is vacuous there. Two caveats on the right-hand column: it "
           r"is binary, so it cannot separate inability from confusion over the words "
           r"\textsf{first}/\textsf{second}, and each frame renders its own index in its header, "
           r"so the task is legible in principle, since one backbone scores $1.00$ on it. "
           if e1s else "")
        + r"Measured by \texttt{scripts/probe\_assumption.py}; per-item records released.}",
        r"\label{tab:probe}",
        r"\begin{tabular}{lcc}",
        r"\toprule",
        r"Backbone & $1-\epsilon_0$ (attribute) & $1-\epsilon_1$ (one step) \\",
        r"\midrule",
    ] + rows + [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    splice("TAB_PROBE", "\n".join(lines))


def tab_cmpclean():
    """What the D-43 defect was worth: the CMP column before and after the corpus fix.

    This table used to give CMP twice from one run (all 24 items vs the 16 non-degenerate
    ones) because the affected cells had not been re-run. They have been now, so the honest
    comparison is between MEASUREMENTS, not between two readings of one measurement: the
    pre-fix column is the superseded run in results/cells_pre_cmpfix/, the post-fix column is
    the current corpus. Both are 24 items at chance 25.0% -- balancing the before/after golds
    removes an exploitable prior (a constant scores 50% on that slice now, not 100%); it does
    not move the chance level, since CMP mixes sixteen K=8 items with eight K=2 ones."""
    src = ROOT / "analysis/verdicts.json"
    if not src.exists():
        print("[make_tables] no verdicts.json; skipping tab:cmpfix")
        return
    v = json.load(open(src))
    pp = v.get("CMP_prepost") or {}
    abl = v.get("CMP_prepost_abl") or {}
    if not pp:
        print("[make_tables] verdicts.json has no CMP_prepost; skipping tab:cmpfix")
        return
    cols = [("asp", r"\ASP{}"), ("retr_only", r"\textsc{Retr-only}"),
            ("blind", r"\textsc{Blind}")]

    def cell(d):
        if not d:
            return ["--", "--"]
        return [f"{d['pre']:.1f}", f"{d['post']:.1f}"]

    lines = [
        r"\begin{table}[!t]",
        r"\centering\small\setlength{\tabcolsep}{4.5pt}",
        r"\caption{\textbf{What the corpus defect was worth: the CMP column before and after "
        r"the fix.} Eight of the twenty-four \textsc{cmp} items carried the gold "
        r"\textsf{before} in the corpus this paper first measured, so a constant answer scored "
        r"$8/8$ on them (D-43). \emph{pre}: the superseded run, retained in "
        r"\texttt{results/cells\_pre\_cmpfix/}. \emph{post}: the same cells re-run against the "
        r"corrected corpus, in which the naming order is chosen to give an exactly $4$--$4$ "
        r"gold balance. Both columns are $24$ items at chance $25.0\%$ -- the fix removes an "
        r"exploitable prior, not a chance-level difference, since \textsc{cmp} mixes sixteen "
        r"$K{=}8$ items with eight $K{=}2$ ones. The \textsc{Blind} pair is the "
        r"diagnostic to read first: an agent that sees no frames at all should sit at chance, "
        r"and only the post column is entitled to. Every \textsc{cmp} figure elsewhere in this "
        r"paper is a \emph{post} figure.}",
        r"\label{tab:cmpfix}",
        r"\begin{tabular}{@{}l" + "cc" * len(cols) + r"@{}}",
        r"\toprule",
        "& " + " & ".join(rf"\multicolumn{{2}}{{c}}{{{tex}}}" for _k, tex in cols) + r" \\",
        " ".join(rf"\cmidrule(lr){{{2 + 2 * n}-{3 + 2 * n}}}" for n in range(len(cols))),
        "Backbone & " + " & ".join("pre & post" for _ in cols) + r" \\",
        r"\midrule",
    ]
    for model, tex, _prm in BACKBONES:
        row = pp.get(model) or {}
        cells = []
        for key, _t in cols:
            cells += cell(row.get(key))
        lines.append(f"{tex} & " + " & ".join(cells) + r" \\")
    if abl:
        lines.append(r"\midrule")
        lines.append(r"\multicolumn{" + str(1 + 2 * len(cols)) +
                     r"}{@{}l}{\emph{flagship ablations, the cells F3 is computed on}} \\")
        for key, tex in (("asp", r"\quad \ASP{}"), ("asp_no_cs", r"\quad $-\cs$"),
                         ("asp_no_cv", r"\quad $-\cv$"), ("asp_r1", r"\quad $R{=}1$")):
            d = abl.get(key)
            if not d:
                continue
            lines.append(f"{tex} & " + " & ".join(cell(d)) +
                         r" & \multicolumn{" + str(2 * (len(cols) - 1)) +
                         r"}{c}{---} \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    splice("TAB_CMPCLEAN", "\n".join(lines))


def tab_registered():
    """The three registered benchmarks with no licence-free data path. Kept as
    predictions so the pre-registration stays auditable rather than quietly dropped."""
    benches = REG["benchmarks"][:3]
    lines = [
        r"\begin{table}[!t]",
        r"\centering\footnotesize\setlength{\tabcolsep}{5pt}",
        r"\caption{\textbf{Registered but not run.} The three natural-video benchmarks of "
        r"the pre-registration, with their frozen predictions\pred{} and registered 90\% "
        r"prediction intervals. They are not measured here: OpenEQA, VSI-Bench and "
        r"EgoSchema need episode-frame dumps we have no licence-free path to, and the "
        r"registered EW-Bench itself needs habitat-sim plus an HM3D/ScanNet licence "
        r"(\S\ref{sec:limits}). No value in this table is claimed as a result.}",
        r"\label{tab:registered}",
        r"\begin{tabular}{ll" + "c" * len(benches) + "}",
        r"\toprule",
        r"Backbone & Method & " + " & ".join(benches) + r" \\",
        r"\midrule",
    ]
    reg_model_tex = {"qwen3.8-27b": r"Qwen3.8-27B", "gemma-4-31b": r"Gemma~4~31B",
                     "qwen3-omni-30b-a3b": r"Qwen3-Omni-30B-A3B",
                     "qwen3-vl-8b": r"Qwen3-VL-8B", "qwen2.5-vl-7b": r"Qwen2.5-VL-7B"}
    meth_tex = dict(METHODS)
    meth_tex["egagent_reimpl"] = r"\textsc{EGAgent} (reimpl.)"
    for mi, (model, methods) in enumerate(REG["main"].items()):
        lines.append(rf"\multirow{{{len(methods)}}}{{*}}{{{reg_model_tex.get(model, model)}}}")
        for method, vals in methods.items():
            cells = [f"{vals['pred'][j]:.1f}" + r"\pred" +
                     (rf"{{\scriptsize$\pm${vals['pm'][j]}}}" if vals.get("pm") else "{}")
                     for j in range(len(benches))]
            lines.append(f" & {meth_tex.get(method, method)} & " + " & ".join(cells) + r" \\")
        if mi < len(REG["main"]) - 1:
            lines.append(r"\midrule")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    splice("TAB_REGISTERED", "\n".join(lines))


BUDGETS = [1024, 2048, 4096, 8192, 16384]

# Corpus parameters, from annotation/generate_synthetic.py. Kept here rather than typed
# into prose so that Sec 5.6's arithmetic and the corpus can never disagree.
N_FRAMES, D_ATTR, K_ALPHA = 300, 32, 8
L_S, BITS_PER_TOKEN = 512, 12.0


def _n_backbones() -> int:
    return sum(1 for m, _t, _p in BACKBONES if load(m, "asp", "RET"))


def values():
    r"""Emit every number the prose quotes as a \newcommand, so the text is generated from
    the same records as the tables. A paper that hardcodes "State-only reaches 12\%" in one
    place and regenerates the table in another will eventually disagree with itself; there is
    no way to notice when it does, and a reader has no way to tell which number is real."""
    import json as _json
    m_bits = L_S * BITS_PER_TOKEN
    kappa = (m_bits / (N_FRAMES * D_ATTR) + 1) / math.log2(K_ALPHA)
    V = {"VN": N_FRAMES, "Vd": D_ATTR, "VK": K_ALPHA,
         "VNd": f"{N_FRAMES * D_ATTR:,}".replace(",", "{,}"),
         "VmBits": f"{m_bits:,.0f}".replace(",", "{,}"),
         "VkappaS": f"{kappa:.3f}", "VkappaSpct": f"{100 * kappa:.1f}",
         "VoneOverK": f"{100 / K_ALPHA:.1f}"}

    def rng(fn, fmt="{:.1f}"):
        vals = [x for x in (fn(m) for m, _t, _p in BACKBONES) if x is not None]
        if not vals:
            return "--", "--"
        return fmt.format(min(vals)), fmt.format(max(vals))

    for key, meth, sub in [("StateRET", "state_only", "RET"),
                           ("UnifRET", "uniform16", "RET"),
                           ("AspRET", "asp", "RET"),
                           ("RetrTRK", "retr_only", "TRK"),
                           ("StateTRK", "state_only", "TRK"),
                           ("AspTRK", "asp", "TRK"),
                           ("AspCMP", "asp", "CMP"),
                           ("BlindRET", "blind", "RET")]:
        lo, hi = rng(lambda m, _me=meth, _s=sub: mean_of(m, _me, _s))
        V[f"V{key}Min"], V[f"V{key}Max"] = lo, hi

    def grand(model, method, budget=4096):
        vs = [mean_of(model, method, s, budget) for s in SUBSETS]
        vs = [v for v in vs if v is not None]
        return statistics.fmean(vs) if len(vs) == len(SUBSETS) else None

    lo, hi = rng(lambda m: grand(m, "asp"))
    V["VAspMeanMin"], V["VAspMeanMax"] = lo, hi
    lo, hi = rng(lambda m: grand(m, "uniform16"))
    V["VUnifMeanMin"], V["VUnifMeanMax"] = lo, hi
    lo, hi = rng(lambda m: (grand(m, "asp") - max(grand(m, "state_only") or -1e9,
                                                  grand(m, "retr_only") or -1e9))
                 if grand(m, "asp") is not None else None, "{:+.1f}")
    V["VCorGapMin"], V["VCorGapMax"] = lo, hi
    lo, hi = rng(lambda m: (grand(m, "asp") - grand(m, "uniform16", 16384))
                 if (grand(m, "asp") is not None
                     and grand(m, "uniform16", 16384) is not None) else None, "{:+.1f}")
    V["VP3DeltaMin"], V["VP3DeltaMax"] = lo, hi

    # Theorem 2's ceiling depends on the realised w, which differs per backbone.
    ceils = []
    for model, _t, _p in BACKBONES:
        w = realised_w(model)
        if w != "--":
            wi = int(w)
            ceils.append(100 * (wi / N_FRAMES + (1 - wi / N_FRAMES) / K_ALPHA))
    V["VThm2Min"] = f"{min(ceils):.1f}" if ceils else "--"
    V["VThm2Max"] = f"{max(ceils):.1f}" if ceils else "--"
    ws = [realised_w(m) for m, _t, _p in BACKBONES if realised_w(m) != "--"]
    V["VwMin"] = min(int(x) for x in ws) if ws else "--"
    V["VwMax"] = max(int(x) for x in ws) if ws else "--"

    for sub in SUBSETS:
        c = load(FLAGSHIP, "asp", sub)
        V[f"Vn{sub}"] = len(c["items"]) if c else "--"
    ns = [V[f"Vn{s}"] for s in SUBSETS]
    V["VnTotal"] = sum(ns) if all(isinstance(x, int) for x in ns) else "--"
    # The abstract used to say "six backbones" in prose. The ladder gained a seventh (D-39),
    # and a hardcoded count in the abstract is exactly the kind of number that goes stale
    # without anyone noticing, so it is generated like every other reported quantity.
    nb = _n_backbones()
    V["VnBackbones"] = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                        6: "six", 7: "seven", 8: "eight"}.get(nb, str(nb))

    # Judge-deferral rate: if this is high, the "accuracy" is partly a judge figure.
    tot = defer = 0
    for f in sorted(CELLS.glob("*__sew_*__B4096.json")):
        c = _json.loads(f.read_text())
        tot += len(c["items"])
        defer += c.get("judge_deferred", 0)
    V["VdeferPct"] = f"{100 * defer / tot:.1f}" if tot else "--"

    # EGAgent head-to-head: the informative comparison is per-subtest, not aggregate.
    for sub in SUBSETS:
        lo, hi = rng(lambda m, _s=sub: (mean_of(m, "asp", _s) - mean_of(m, "egagent", _s))
                     if (mean_of(m, "asp", _s) is not None
                         and mean_of(m, "egagent", _s) is not None) else None, "{:+.1f}")
        V[f"Vega{sub}Min"], V[f"Vega{sub}Max"] = lo, hi

    # The LOCATION claim: on RET the compressive-only channel should be the weaker of the
    # two single channels, and on TRK the verbatim-only one. Counting how many backbones
    # show that is the check; asserting it in prose without counting is not.
    loc = 0
    for model, _t, _p in BACKBONES:
        so_r, ro_r = mean_of(model, "state_only", "RET"), mean_of(model, "retr_only", "RET")
        so_t, ro_t = mean_of(model, "state_only", "TRK"), mean_of(model, "retr_only", "TRK")
        if None in (so_r, ro_r, so_t, ro_t):
            continue
        loc += int(so_r < ro_r and ro_t < so_t)
    V["VlocCount"] = loc
    V["VnMeasured"] = sum(1 for m, _t, _p in BACKBONES if mean_of(m, "asp", "RET") is not None)

    # Realised (B_s, B_r, B_c) split per router class. App. D registers a prediction about
    # this and it is only checkable if the ledger is actually reported.
    for sub in SUBSETS:
        acc = {"Bs": [], "Br": [], "Bc": [], "rho": []}
        for model, _t, _p in BACKBONES:
            c = load(model, "asp", sub)
            for r in (c["items"] if c else []):
                sp = r.get("split") or {}
                for ch in acc:
                    if ch in sp:
                        acc[ch].append(sp[ch])
        for ch in acc:
            V[f"Vsplit{sub}{ch}"] = (f"{100 * statistics.fmean(acc[ch]):.0f}"
                                     if acc[ch] else "--")

    rr = ROOT / "analysis/retrieval_recall.json"
    if rr.exists():
        d = _json.loads(rr.read_text())
        rec = [x["recall_at_k"] for x in d.values() if "recall_at_k" in x]
        dr = [x["delta_r"] for x in d.values() if "delta_r" in x]
        V["VrecallMin"] = f"{min(rec):.2f}" if rec else "--"
        V["VrecallMax"] = f"{max(rec):.2f}" if rec else "--"
        V["VdeltaRMin"] = f"{min(dr):.2f}" if dr else "--"
        V["VdeltaRMax"] = f"{max(dr):.2f}" if dr else "--"
    else:
        for k in ("VrecallMin", "VrecallMax", "VdeltaRMin", "VdeltaRMax"):
            V[k] = "--"

    # LaTeX control words are letters only: \VP3DeltaMin is a parse error, not a name.
    digits = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
              "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}
    V = {"".join(digits.get(ch, ch) for ch in k): val for k, val in V.items()}
    body = "\n".join(rf"\newcommand{{\{k}}}{{{val}}}" for k, val in V.items())
    # Defaults for the macros analysis/analyze.py owns, so an intermediate build (tables
    # regenerated, verdicts not yet recomputed) compiles instead of dying on an undefined
    # control sequence -- and so a missing verdict prints as "not evaluated" rather than
    # as a stale one. analyze.py emits \renewcommand over these.
    body += "\n" + "\n".join(
        rf"\providecommand{{\{k}}}{{{d}}}" for k, d in [
            ("VFone", "not evaluated"), ("VFtwo", "not evaluated"),
            ("VFthree", "not evaluated"), ("VFfour", "not evaluated"),
            ("VrhoUnif", "--"), ("VrhoAsp", "--"), ("VrhoDrop", "--"),
            ("VthmOneViol", "not evaluated"), ("VpairedFlagDelta", "--"),
            ("VpairedFlagP", "--"), ("VpairedFlagN", "--"),
            ("VdomCount", "--"), ("VsigCount", "--"), ("VnBackbones", "--"),
            ("VnTests", "--"), ("VsigUncorr", "--"), ("VsigHolm", "--"),
            ("VretrHolmSurv", "--"), ("VretrRawSurv", "--"), ("VretrNeg", "--"),
            ("VFthreeClean", "not evaluated"), ("VFthreeInvariant", "--"),
            ("VAspCmpAll", "--"), ("VAspCmpClean", "--"),
            ("VNoCsCmpAll", "--"), ("VNoCsCmpClean", "--"),
            ("VRoneCmpAll", "--"), ("VRoneCmpClean", "--"),
            ("VNoCvCmpAll", "--"), ("VNoCvCmpClean", "--"),
            ("VNoRhoCmpAll", "--"), ("VNoRhoCmpClean", "--")])
    splice("VALUES", body)
    return V





def fig_curves():
    """Figure 6, from measured cells. Panel (a) is the budget-capability curve on the
    flagship; panel (b) is score against parameter count, which is Prediction 3's axis.
    Points with no cell are simply absent rather than interpolated -- a drawn line through
    a budget we never ran would be indistinguishable from one we did."""
    def series(method, budget_axis=True, model=FLAGSHIP):
        pts = []
        if budget_axis:
            for b in BUDGETS:
                vs = [mean_of(model, method, s, b) for s in SUBSETS]
                vs = [v for v in vs if v is not None]
                if len(vs) == len(SUBSETS):
                    pts.append((b, statistics.fmean(vs)))
        else:
            for m, _tex, prm in BACKBONES:
                vs = [mean_of(m, method, s) for s in SUBSETS]
                vs = [v for v in vs if v is not None]
                if len(vs) == len(SUBSETS):
                    pts.append((prm, statistics.fmean(vs)))
        return " ".join(f"({x},{y:.1f})" for x, y in pts), pts

    style = {"uniform16": r"cwall, thick, mark=square*",
             "asp": r"crouter, very thick, mark=*"}
    lab = {"uniform16": r"\textsc{Uniform-}$w$", "asp": r"\ASP{}"}

    a_lines, any_a = [], False
    for meth in ("uniform16", "asp"):
        co, pts = series(meth)
        if pts:
            any_a = True
            a_lines.append(rf"\addplot[{style[meth]}] coordinates {{{co}}};")
            a_lines.append(rf"\addlegendentry{{{lab[meth]}}}")
    b_lines, rho = [], {}
    for meth in ("uniform16", "asp"):
        co, pts = series(meth, budget_axis=False)
        if pts:
            b_lines.append(rf"\addplot[{style[meth]}] coordinates {{{co}}};")
            xs = [x for x, _ in pts]; ys = [y for _, y in pts]
            rho[meth] = _spearman(xs, ys)
            b_lines.append(rf"\addlegendentry{{{lab[meth]}: "
                           rf"$\rho_{{\mathrm{{scale}}}}{{=}}{rho[meth]:.2f}$}}")

    axis_opts = (r"width=0.92\linewidth, height=5.4cm, grid=major, grid style={gray!20}, "
                 r"legend style={font=\scriptsize, at={(0.5,-0.30)}, anchor=north, "
                 r"legend columns=2, draw=none, fill=none, column sep=1.2ex}, "
                 r"legend cell align=left, label style={font=\small}, "
                 r"tick label style={font=\scriptsize}")
    out = [r"\begin{figure}[!t]", r"\centering",
           r"\begin{subfigure}{0.48\textwidth}", r"\centering",
           r"\begin{tikzpicture}",
           r"\begin{axis}[" + axis_opts + ", "
           r"xlabel={per-decision budget $B$ (tokens, log scale)}, "
           r"ylabel={SEW-Bench mean (\%)}, xmode=log, log basis x=2, "
           r"xtick={1024,2048,4096,8192,16384}, xticklabels={1k,2k,4k,8k,16k}]"]
    out += a_lines if any_a else [r"\addplot[gray] coordinates {(1024,0)};"]
    out += [r"\end{axis}", r"\end{tikzpicture}",
            r"\caption{Budget--capability, " + FLAGSHIP.replace("qwen3.8-27b", "Qwen3.8-27B")
            + r".}", r"\label{fig:budget}", r"\end{subfigure}\hfill",
            r"\begin{subfigure}{0.48\textwidth}", r"\centering", r"\begin{tikzpicture}",
            r"\begin{axis}[" + axis_opts + ", "
            r"xlabel={backbone parameters (B, log scale)}, "
            r"ylabel={SEW-Bench mean (\%)}, xmode=log, log basis x=2, "
            r"xtick={3,8,12,27,31}, xticklabels={3,8,12,27,31}, xmin=2.6, xmax=36]"]
    out += b_lines if b_lines else [r"\addplot[gray] coordinates {(3,0)};"]
    out += [r"\end{axis}", r"\end{tikzpicture}",
            r"\caption{Capability convergence across scale (Pred.~\ref{prd:conv}).}",
            r"\label{fig:conv}", r"\end{subfigure}"]
    drop = (rf" The rank correlation between parameter count and score falls from "
            rf"$\rho_{{\mathrm{{scale}}}}{{=}}{rho['uniform16']:.2f}$ under "
            rf"\textsc{{Uniform-}}$w$ to ${rho['asp']:.2f}$ under \ASP{{}}."
            if len(rho) == 2 else "")
    out += [r"\caption{\textbf{Measured budget and scale curves.} (a) Whether "
            r"restructuring a small budget beats enlarging an unstructured one, read as a "
            r"curve rather than a single contrast: the \ASP{} point at $B{=}4$k is to be "
            r"compared with the \textsc{Uniform-}$w$ point at $B{=}16$k. (b) Score against "
            r"parameter count for the two ends of the comparison." + drop +
            r" Missing points are budgets or backbones with no cell, left absent rather "
            r"than interpolated.}",
            r"\label{fig:curves}", r"\end{figure}"]
    splice("FIG_CURVES", "\n".join(out))


# (row key, row label, the subtest the pre-registration says it must hit hardest)
COLLAPSE_ROWS = [("asp_no_cv", r"$-\,\cv$", "RET"),
                 ("asp_no_cs", r"$-\,\cs$", "TRK"),
                 ("asp_r1",    r"$R{=}1$",    "CMP")]
COL_WALL = {"RET": r"Thm.~\ref{thm:shannon}\,$+$\,\ref{thm:horizon}",
            "TRK": r"Lem.~\ref{lem:vtrack}",
            "CMP": r"Thm.~\ref{thm:circuit}\,$+$\,\ref{thm:rounds}"}
COL_CHAN = {"RET": r"$\cv$", "TRK": r"$\cs$", "CMP": r"$R$ rounds"}


def fig_collapse():
    """Figure 7 from the measured ablation cells: delta vs full ASP, per subtest.

    The green box marks where the PRE-REGISTRATION says the largest drop in that column
    should be, not where it actually is. That is the point of criterion F3 -- if the
    measured largest drop moves off the boxed cell the figure shows it moving off, rather
    than the box quietly following the data."""
    full = {sub: mean_of(FLAGSHIP, "asp", sub) for sub in SUBSETS}
    if any(v is None for v in full.values()):
        # Still emit the float and its \label: an intermediate build otherwise reports
        # fig:collapse as an undefined reference, which buries real warnings in noise.
        splice("FIG_COLLAPSE",
               "\n".join([r"\begin{figure}[!t]\centering",
                          r"\fbox{\parbox{0.8\textwidth}{\centering\small "
                          r"ablation cells not present -- run "
                          r"\texttt{scripts/run\_grid.py --phase ablation}}}",
                          r"\caption{Measured collapse pattern (pending).}",
                          r"\label{fig:collapse}", r"\end{figure}"]))
        return
    deltas, worst = {}, {}
    for var, _lab, _exp in COLLAPSE_ROWS:
        for sub in SUBSETS:
            v = mean_of(FLAGSHIP, var, sub)
            deltas[(var, sub)] = None if v is None else v - full[sub]
    for sub in SUBSETS:
        got = {var: deltas[(var, sub)] for var, _l, _e in COLLAPSE_ROWS
               if deltas[(var, sub)] is not None}
        worst[sub] = min(got, key=lambda k: got[k]) if got else None

    W, H = 2.75, 1.16
    out = [r"\begin{figure}[!t]", r"\centering",
           r"\begin{tikzpicture}[scale=0.94, every node/.style={transform shape}]",
           rf"\def\W{{{W}}}\def\Hh{{{H}}}"]
    for j, sub in enumerate(SUBSETS):
        out += [rf"\node[font=\small\bfseries] at ({{{j}*\W+0.5*\W}},{{0.42}}) "
                rf"{{SEW-{sub}}};",
                rf"\node[font=\scriptsize, gray!60!black] at "
                rf"({{{j}*\W+0.5*\W}},{{-3*\Hh-0.26}}) {{{COL_WALL[sub]}}};",
                rf"\node[font=\scriptsize, gray!60!black] at "
                rf"({{{j}*\W+0.5*\W}},{{-3*\Hh-0.58}}) {{decisive: {COL_CHAN[sub]}}};"]
    for i, (var, lab, _exp) in enumerate(COLLAPSE_ROWS):
        out.append(rf"\node[font=\small, anchor=east] at "
                   rf"(-0.18,{{-{i}*\Hh-0.5*\Hh}}) {{{lab}}};")
    span = max((abs(d) for d in deltas.values() if d is not None), default=1.0) or 1.0
    for i, (var, _lab, expected) in enumerate(COLLAPSE_ROWS):
        for j, sub in enumerate(SUBSETS):
            d = deltas[(var, sub)]
            txt = "--" if d is None else rf"${d:+.1f}$"
            tint = 0 if d is None else int(min(70, 70 * abs(d) / span))
            box = 1 if expected == sub else 0
            hit = 1 if worst.get(sub) == var else 0
            out += [rf"\fill[cverb!{tint}, draw=gray!45] ({j}*\W,{{-{i}*\Hh-\Hh}}) "
                    rf"rectangle ({{{j}*\W+\W}},{{-{i}*\Hh-\Hh+\Hh}});"]
            if box:
                col = "crouter" if hit else "cverb"
                out.append(rf"\draw[{col}, very thick, rounded corners=1pt] "
                           rf"({{{j}*\W+0.05}},{{-{i}*\Hh-\Hh+0.05}}) rectangle "
                           rf"({{{j}*\W+\W-0.05}},{{-{i}*\Hh-0.05}});")
            out.append(rf"\node[font=\small] at ({{{j}*\W+0.5*\W}},"
                       rf"{{-{i}*\Hh-0.5*\Hh}}) {{{txt}}};")
    out.append(r"\node[font=\scriptsize, gray!55!black, anchor=east] at (-0.18,0.42) "
               r"{$\Delta$ score (pts)};")
    ok = all(worst[s] == v for v, _l, e in COLLAPSE_ROWS for s in [e] if worst.get(s))
    ok = all(worst.get(e) == v for v, _l, e in COLLAPSE_ROWS)
    verdict = (r"\textcolor{crouter}{\rule{2.6mm}{1.1pt}}\ \ the registered signature "
               r"HOLDS: in every column the largest drop is the ablation that removes "
               r"\emph{that} column's wall price."
               if ok else
               r"\textcolor{cverb}{\rule{2.6mm}{1.1pt}}\ \ the registered signature is "
               r"\textbf{CROSSED} in at least one column: the boxed cell is where the "
               r"pre-registration put the largest drop, and it is not where the largest "
               r"drop is. Criterion F3 fires; \S\ref{sec:falsify} reports it as such.")
    out += [r"\node[font=\scriptsize, anchor=north west, align=left, text width=7.9cm] "
            r"at (0,{-3*\Hh-0.92}) {" + verdict + r"};",
            r"\end{tikzpicture}",
            r"\caption{\textbf{Measured collapse pattern.} Each cell is the change in score "
            r"when one channel or resource is removed from \ASP{}, against full \ASP{} on "
            rf"the flagship (SEW-RET/TRK/CMP $={full['RET']:.1f}/{full['TRK']:.1f}/"
            rf"{full['CMP']:.1f}$). The theory predicts a \emph{{shape}}, not merely that "
            r"ablations hurt: removing $\cv$ should cost most on the subtest witnessing the "
            r"Shannon and horizon walls while costing little on tracking, and symmetrically "
            r"for $\cs$ and for rounds. Boxes mark where the pre-registration placed each "
            r"column's largest drop; they are not moved to follow the data, which is what "
            r"makes criterion F3 (\S\ref{sec:falsify}) able to fire.}",
            r"\label{fig:collapse}", r"\end{figure}"]
    splice("FIG_COLLAPSE", "\n".join(out))


def _spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    import math
    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


if __name__ == "__main__":
    n = len(list(CELLS.glob("*.json"))) if CELLS.exists() else 0
    values()
    tab_main()
    tab_ablation()
    tab_p3()
    tab_probe()
    tab_cmpclean()
    tab_registered()
    fig_curves()
    fig_collapse()
    print(f"[make_tables] spliced generated values, tab:main, tab:ablation, tab:p3, tab:probe, tab:cmpclean, tab:registered, fig:curves, fig:collapse "
          f"into paper/asp/asp.tex from {n} cell record(s)")
