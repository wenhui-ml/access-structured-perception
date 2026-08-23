#!/usr/bin/env python3
r"""Audit every float in the paper: does it say what the data says, and does it sit inside
the text block and line up with everything else?

Four layers, cheapest first. Each is a separate exit-code contribution, so a caption typo
does not hide a figure hanging 12pt into the margin.

  L1 STRUCTURE   parse asp.tex: every float labelled, every label referenced, captions
                 present and in house style, float placement consistent, generated blocks
                 properly delimited.
  L2 GEOMETRY    measure the TYPESET RESULT with pdfplumber, not the source. Every drawn
                 object and glyph is checked against the text block, so a figure that
                 overruns is caught even when LaTeX reports no overfull box (tikz pictures
                 routinely overrun silently -- they are one box as far as TeX is concerned).
                 Also: per-float centring slack, and the smallest font size in each float.
  L3 AGREEMENT   regenerate every generated block from the measured data and diff. If a
                 number in a table or figure has drifted from results/, the regeneration
                 changes the file and this fails. This is the check that a float "matches
                 what the paper expects": expectation is defined as the data on disk.
  L4 REGRESSION  hash each rendered page. Stored under analysis/.figbaseline/. On a later
                 run, report which pages changed -- so an edit meant to fix figure 7 that
                 also reflowed figure 12 does not go unnoticed.

Usage:
  python analysis/check_figures.py                 # L1+L2, fast, no side effects
  python analysis/check_figures.py --agreement     # + L3 (runs make_tables/analyze)
  python analysis/check_figures.py --baseline      # + L4, (re)write the page hashes
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEX = ROOT / "paper/asp/asp.tex"
PDF = ROOT / "paper/asp/asp.pdf"
BASE = ROOT / "analysis/.figbaseline"

# 10pt article, geometry margin=1in, letter. The text block is the contract every float
# has to honour; hardcoding it from the class options is more honest than inferring it
# from the glyphs, which would define the margin as wherever the content happens to end.
PAGE_W, PAGE_H = 612.0, 792.0
MARGIN = 72.0
BOX_L, BOX_R = MARGIN, PAGE_W - MARGIN
TOL = 1.0            # pt. Below this, a rule end is antialiasing, not a defect.
FONT_FLOOR = 5.0     # pt effective. Below this a tikz label is unreadable.
CENTRE_TOL = 6.0     # pt of left/right slack asymmetry before centring is "off"

fails: list[str] = []
warns: list[str] = []


def bad(layer: str, msg: str) -> None:
    fails.append(f"[{layer}] {msg}")


def warn(layer: str, msg: str) -> None:
    warns.append(f"[{layer}] {msg}")


# ---------------------------------------------------------------- L1: structure
FLOAT_RE = re.compile(r"\\begin\{(figure|table)\*?\}(\[[^\]]*\])?", re.M)


def layer1(src: str) -> dict:
    """Returns {label: {kind, caption, placement, line}} for every float."""
    floats: dict = {}
    for m in FLOAT_RE.finditer(src):
        kind, placement = m.group(1), (m.group(2) or "")
        # Find this float's matching \end, allowing nested subfigure/tabular.
        depth, i = 1, m.end()
        open_re = re.compile(rf"\\(begin|end)\{{{kind}\*?\}}")
        while depth and i < len(src):
            n = open_re.search(src, i)
            if not n:
                break
            depth += 1 if n.group(1) == "begin" else -1
            i = n.end()
        body = src[m.end():i]
        line = src[:m.start()].count("\n") + 1
        labels = re.findall(r"\\label\{([^}]+)\}", body)
        caps = re.findall(r"\\caption(?:\[[^\]]*\])?\{", body)
        if not labels:
            bad("L1", f"{kind} at line {line} has no \\label -- it cannot be referenced")
            continue
        # A float with subfigures carries several labels; the float's own is the last one
        # not belonging to a subfigure.
        outer = [l for l in labels if not l.startswith("fig:sub")]
        lab = outer[-1] if outer else labels[-1]
        if not caps:
            bad("L1", f"{kind} {lab} (line {line}) has no \\caption")
        floats[lab] = dict(kind=kind, placement=placement, line=line,
                           n_caption=len(caps), body=body)
    # Every float must be referenced, or it is decoration the reader never reaches.
    for lab, d in floats.items():
        n = len(re.findall(r"\\(?:ref|autoref|Cref|cref)\{" + re.escape(lab) + r"\}", src))
        if n == 0:
            bad("L1", f"{d['kind']} {lab} (line {d['line']}) is never \\ref'd in the text")
        d["n_refs"] = n
    # House style: floats are [!t]. A stray [h] is what makes a float land mid-paragraph.
    for lab, d in floats.items():
        if d["placement"] not in ("[!t]", "[t]", "[!tb]", ""):
            warn("L1", f"{d['kind']} {lab} placement {d['placement']} "
                       f"(house style is [!t]); this is how floats drift off-page")
    # Generated blocks must be paired, or a regeneration writes into the wrong span.
    begins = re.findall(r"% ===== BEGIN GENERATED (\w+)", src)
    ends = re.findall(r"% ===== END GENERATED (\w+) =====", src)
    for b in begins:
        if b not in ends:
            bad("L1", f"generated block {b} has BEGIN but no END marker")
    dupes = [k for k, c in collections.Counter(begins).items() if c > 1]
    if dupes:
        bad("L1", f"duplicated generated markers: {dupes}")
    print(f"  L1  {len(floats)} floats, {len(begins)} generated blocks")
    return floats


# ---------------------------------------------------------------- L2: geometry
# CALIBRATION. The first version of this check reported 60 failures, all of them
# microtype character protrusion: commas, hyphens, periods, parens and em-dashes are
# deliberately allowed to hang past the margin so the edge looks optically straight. A
# checker that flags a typographic feature is worse than no checker, so the two kinds of
# object get different contracts:
#   * DRAWN geometry (tabular rules, tikz paths) must land inside the text block to 0.5pt.
#     Nothing places these but us, and LaTeX does NOT report a tikzpicture that overruns --
#     the picture is one box as far as TeX is concerned, so \hbadness never fires.
#   * GLYPHS get 2pt, and the protruding punctuation is exempt entirely.
# The font-size floor moved to the SOURCE (see layer2_fonts): measuring it in the PDF just
# rediscovers that nested math scripts are small, which is not a defect.
TOL_DRAW = 0.5
TOL_GLYPH = 2.0
PROTRUDE = set(",.;:!?-\u2013\u2014()[]{}'\"\u2018\u2019\u201c\u201d/*")


def layer2(floats: dict) -> None:
    try:
        import pdfplumber
    except ImportError:
        warn("L2", "pdfplumber not installed; geometry unchecked")
        return
    if not PDF.exists():
        bad("L2", f"{PDF} does not exist -- build the paper first")
        return

    n_draw = n_glyph = 0
    worst_draw = 0.0
    spans: list = []          # per-float content extent, for the alignment report
    with pdfplumber.open(str(PDF)) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            caps = [(float(w["top"]), w["text"]) for w in
                    (page.extract_words() or []) if w["text"] in ("Figure", "Table")]

            for r in (page.rects or []) + (page.lines or []) + (page.curves or []):
                n_draw += 1
                x0, x1 = float(r["x0"]), float(r["x1"])
                over = max(BOX_L - x0, x1 - BOX_R)
                if over > TOL_DRAW:
                    worst_draw = max(worst_draw, over)
                    bad("L2", f"p{pno} {_nearest(caps, float(r['top']))}: drawn object "
                              f"overruns the text block by {over:.1f}pt "
                              f"(x[{x0:.1f},{x1:.1f}] vs [{BOX_L:.0f},{BOX_R:.0f}]) -- "
                              f"LaTeX never reports this for a tikzpicture")
            for c in (page.chars or []):
                t = (c.get("text") or "")
                if not t.strip() or t in PROTRUDE:
                    continue
                n_glyph += 1
                x0, x1 = float(c["x0"]), float(c["x1"])
                over = max(BOX_L - x0, x1 - BOX_R)
                if over > TOL_GLYPH:
                    bad("L2", f"p{pno} {_nearest(caps, float(c['top']))}: glyph {t!r} "
                              f"{over:.1f}pt outside the text block")

            # Alignment / width utilisation, measured from DRAWN objects rather than
            # glyphs. A table's width IS its \toprule width and a tikzpicture's is its
            # paths' extent; captions contain no rules, so this attribution cannot be
            # polluted by a short last caption line -- which is exactly what made the first
            # version of this check report a centred table as flush-left.
            draws = [(float(o["x0"]), float(o["x1"]), float(o["top"]))
                     for o in (page.rects or []) + (page.lines or []) + (page.curves or [])]
            if draws:
                groups: list = []
                for x0, x1, top in sorted(draws, key=lambda d: d[2]):
                    if groups and top - groups[-1][2] < 200:
                        g = groups[-1]
                        groups[-1] = (min(g[0], x0), max(g[1], x1), top)
                    else:
                        groups.append((x0, x1, top))
                for x0, x1, top in groups:
                    if x1 - x0 < 100:          # a rule that short is a cell border, not a float
                        continue
                    spans.append((pno, _nearest(caps, top), x0, x1))

    if spans:
        blk = BOX_R - BOX_L
        # Under-use is the defect that hides: a float 20% narrower than the text block whose
        # cells are simultaneously hyphenating is wasting width AND cramping content. That
        # was the Table 9 defect -- 402pt of 468pt used, with "pub-lished" in a 2.35cm column.
        # Width UNDER-USE on its own is not a defect: a four-column table of small numbers
        # should be narrow, and stretching it would look worse. It only matters when it
        # coincides with cramped cells, and that is decided from the source in
        # layer2_widths(); here we keep the two signals that are defects on their own --
        # a float that is severely narrow, and one that is full width but off-centre.
        for p_, k, x0, x1 in sorted(set(spans), key=lambda t: t[3] - t[2]):
            used = x1 - x0
            # Centring is only checkable for TABLES. A booktabs rule is exactly the table
            # width, so its extent is the float's. A tikzpicture's drawn paths are not: text
            # nodes legitimately stick out past the paths, so a centred figure measures as
            # off-centre and the check would cry wolf on every figure in the paper.
            if k != "Table":
                continue
            if used < 0.62 * blk:
                warn("L2", f"p{p_} table: uses only {used:.0f}pt of the {blk:.0f}pt text "
                           f"block ({used / blk:.0%}) -- check it is meant to be this narrow")
            elif abs((x0 - BOX_L) - (BOX_R - x1)) > CENTRE_TOL:
                warn("L2", f"p{p_} table: {used:.0f}pt wide but not centred -- slack "
                           f"L{x0 - BOX_L:.1f} R{BOX_R - x1:.1f}pt")
    print(f"  L2  {n_draw} drawn objects (tol {TOL_DRAW}pt) and {n_glyph} glyphs "
          f"(tol {TOL_GLYPH}pt, punctuation exempt) vs text block "
          f"[{BOX_L:.0f},{BOX_R:.0f}]pt")


def _nearest(caps: list, top: float) -> str:
    """Name the float whose caption is nearest above this object, so a geometry complaint
    points at something a human can find in the PDF."""
    above = [(t, k) for t, k in caps if t <= top + 2]
    if not above:
        return "float above (caption on an earlier page)"
    return max(above)[1]


def _parse_colspec(spec: str):
    r"""Split a tabular column spec into (p-widths in cm, number of natural-width columns).

    Written as a scanner rather than a regex because both naive attempts were wrong: a
    non-greedy [^}]* stops at the brace inside >{\raggedright\arraybackslash}, and
    [clr] with letter-boundary lookarounds matches NOTHING in `cccc` -- every c is flanked
    by letters. A four-column checkmark block then counts as zero columns and the table's
    width audit is quietly meaningless.
    """
    ps: list = []
    natural = 0
    i = 0
    n = len(spec)
    while i < n:
        ch = spec[i]
        if ch in "@!>" and i + 1 < n and spec[i + 1] == "{":
            depth, i = 0, i + 1          # skip a balanced {...} decoration
            while i < n:
                if spec[i] == "{":
                    depth += 1
                elif spec[i] == "}":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            continue
        if ch in "pmb" and i + 1 < n and spec[i + 1] == "{":
            j = spec.find("}", i)
            body = spec[i + 2:j] if j > 0 else ""
            m = re.match(r"([0-9.]+)cm", body)
            if m:
                ps.append(float(m.group(1)))
            else:
                natural += 1             # p{\linewidth} etc -- not a fixed cm width
            i = (j + 1) if j > 0 else n
            continue
        if ch in "clrX":
            natural += 1
        i += 1
    return ps, natural


def layer2_widths(src: str) -> None:
    r"""Tables whose p-columns do not add up to the text block.

    This is the check that catches the real defect, because it catches the CAUSE. A tabular
    made of p{} columns is one whose cells are expected to wrap; if the specified widths sum
    to well under \textwidth, every one of those cells wraps EARLIER THAN IT HAD TO, and the
    table simultaneously sits indented from the text block. That combination -- wasted width
    plus forced hyphenation -- was Table 9: p-columns summing to 11.9cm inside a 16.5cm
    block, rendering "pub-lished" and a six-line row.

    A table of c/r/l columns is exempt: narrow is correct there and widening it is worse.
    """
    TEXTW = (BOX_R - BOX_L) / 28.4527          # pt -> cm
    n = flagged = 0
    # NOT [^}]* -- a column spec containing >{\raggedright\arraybackslash} has braces in
    # it, and a non-greedy no-brace match silently skips every such table. Silence from a
    # checker is not a pass, so the spec is taken to the end of its line instead.
    for m in re.finditer(r"\\begin\{tabular\}\{(.*)$", src, re.M):
        spec = m.group(1)
        line = src[:m.start()].count("\n") + 1
        ps, n_other = _parse_colspec(spec)
        if not ps:
            continue
        n += 1
        ncol = len(ps) + n_other
        # \tabcolsep is 6pt by default but several of these tables set it to 4pt; read the
        # nearest preceding \setlength so the arithmetic matches the table being audited.
        ts = re.findall(r"\\setlength\{\\tabcolsep\}\{([0-9.]+)pt\}", src[:m.start()])
        tabcolsep = float(ts[-1]) if ts else 6.0
        sep = ((ncol - 1) if "@{}" in spec else (ncol + 1)) * 2 * tabcolsep / 28.4527
        # Natural-width columns take their content, which is unknown here; 1.2cm is a
        # deliberately generous allowance so this check under-reports rather than over-.
        total = sum(ps) + sep + 1.2 * n_other
        if total < 0.90 * TEXTW:
            flagged += 1
            warn("L2w", f"tabular at line {line}: {len(ps)} p-columns sum to "
                        f"{sum(ps):.2f}cm (+{sep:.2f}cm colsep at {tabcolsep:.0f}pt, "
                        f"{n_other} natural column(s)) = {total:.2f}cm inside a "
                        f"{TEXTW:.2f}cm text block. Every p-cell wraps earlier than it had "
                        f"to; widen the columns or move content to a note.")
    print(f"  L2w {n} tabulars with p-columns checked against the "
          f"{TEXTW:.2f}cm text block")


def layer2_fonts(src: str) -> None:
    r"""Effective font size inside tikzpictures, from the source.

    This is the check the PDF cannot do cleanly. `scale=` combined with
    `every node/.style={transform shape}` scales the FONTS too, so shrinking a figure to fix
    a margin overrun silently shrinks its labels -- which is exactly how a legend ends up at
    4pt. Effective size = declared size x scale, and it is flagged below FONT_FLOOR."""
    SIZE = {"tiny": 5.0, "scriptsize": 7.0, "footnotesize": 8.0, "small": 9.0,
            "normalsize": 10.0, "large": 12.0}
    n = 0
    for m in re.finditer(r"\\begin\{tikzpicture\}(\[[^\]]*\])?", src):
        opts = m.group(1) or ""
        line = src[:m.start()].count("\n") + 1
        sc = re.search(r"scale\s*=\s*([0-9.]+)", opts)
        scale = float(sc.group(1)) if sc else 1.0
        shapes = "transform shape" in opts
        end = src.find(r"\end{tikzpicture}", m.end())
        body = src[m.end():end if end > 0 else m.end()]
        n += 1
        sizes = {SIZE[k] for k in SIZE if re.search(rf"\\{k}\b", body + opts)}
        if not sizes:
            continue
        eff = min(sizes) * (scale if shapes else 1.0)
        if eff < FONT_FLOOR:
            bad("L2f", f"tikzpicture at line {line}: smallest font {min(sizes):.0f}pt "
                       f"x scale {scale} = {eff:.1f}pt effective (floor {FONT_FLOOR}pt). "
                       f"`transform shape` scales fonts as well as coordinates.")
    print(f"  L2f {n} tikzpictures checked for effective font size "
          f"(floor {FONT_FLOOR}pt)")


# ---------------------------------------------------------------- L3: agreement
def layer3() -> None:
    """Every generated float must regenerate identically from the data on disk."""
    before = TEX.read_bytes()
    for script in ("analysis/make_tables.py", "analysis/analyze.py"):
        r = subprocess.run([sys.executable, str(ROOT / script)],
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            bad("L3", f"{script} exited {r.returncode}: {r.stderr.strip()[-300:]}")
            return
    after = TEX.read_bytes()
    if before == after:
        print("  L3  every generated block already agrees with results/ (byte-identical)")
        return
    # Report WHICH blocks moved, not just that something did.
    b = before.decode("utf-8", "replace").splitlines()
    a = after.decode("utf-8", "replace").splitlines()
    import difflib
    moved = set()
    cur = "?"
    for line in difflib.unified_diff(b, a, n=0, lineterm=""):
        m = re.match(r"% ===== BEGIN GENERATED (\w+)", line[1:] if line[:1] in "+-" else line)
        if m:
            cur = m.group(1)
        if line[:1] in "+-" and not line.startswith(("+++", "---")):
            moved.add(cur)
    bad("L3", f"generated content had DRIFTED from results/: regenerating changed "
              f"{sorted(moved) or ['(span unknown)']}. The paper was reporting stale "
              f"numbers; it is now fixed on disk, so rebuild and re-check.")


# ---------------------------------------------------------------- L4: regression
def layer4(write: bool) -> None:
    if not PDF.exists():
        return
    BASE.mkdir(exist_ok=True)
    store = BASE / "pagehashes.json"
    out = subprocess.run(["pdftoppm", "-r", "50", "-png", str(PDF),
                          str(BASE / "pg")], capture_output=True)
    if out.returncode != 0:
        warn("L4", "pdftoppm failed; page regression unchecked")
        return
    cur = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
           for p in sorted(BASE.glob("pg-*.png"))}
    for p in BASE.glob("pg-*.png"):
        p.unlink()
    if write or not store.exists():
        store.write_text(json.dumps(cur, indent=1))
        print(f"  L4  baseline written: {len(cur)} pages")
        return
    old = json.loads(store.read_text())
    changed = sorted(k for k in cur if old.get(k) != cur[k])
    added = sorted(set(cur) - set(old))
    removed = sorted(set(old) - set(cur))
    if not (changed or added or removed):
        print(f"  L4  all {len(cur)} pages pixel-identical to baseline")
    else:
        warn("L4", f"pages changed since baseline: {changed or '-'}"
                   f"{'  added ' + str(added) if added else ''}"
                   f"{'  removed ' + str(removed) if removed else ''}"
                   f"   (re-run with --baseline once the change is intended)")


def layer5_proofmarks(src: str) -> None:
    r"""End-of-proof marks: must be flush right, and must come from the macros.

    Two failure modes, both of which the paper had. (a) `\qquad\blacksquare` inside a
    \[...\] display makes the mark part of the CENTRED content: it never reaches the margin
    and it shifts the equation off centre. (b) a bare inline $\blacksquare$ after a full line
    can wrap onto the next line alone, reading as a stray glyph. Both are invisible in the
    source and obvious in the PDF, so the source is checked for the raw symbol and the PDF
    for the position.
    """
    raw = [src[:m.start()].count("\n") + 1
           for m in re.finditer(r"\\blacksquare", src)
           if "qedmark" not in src[max(0, m.start() - 120):m.start()]
           and not src[:m.start()].rstrip().endswith("%")]
    # The definition line is legitimate; anything else should use \proofend/\proofenddisp.
    body = [l for l in raw if not re.match(r"\s*%", src.splitlines()[l - 1])]
    for l in body[1:]:
        bad("L5", f"line {l}: raw \\blacksquare -- use \\proofend (text) or "
                  f"\\proofenddisp (display) so the mark lands at the margin")
    if not PDF.exists():
        return
    try:
        import pdfplumber
    except ImportError:
        return
    n = off = 0
    with pdfplumber.open(str(PDF)) as pdf:
        for page in pdf.pages:
            for c in page.chars or []:
                if (c.get("text") or "") != "■":
                    continue
                n += 1
                gap = BOX_R - float(c["x1"])
                if gap > 3.0:
                    off += 1
                    bad("L5", f"p{page.page_number}: QED mark {gap:.1f}pt short of the "
                              f"right margin -- it is inside centred content, not flush right")
    print(f"  L5  {n} end-of-proof marks, {n - off} flush right at the margin")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agreement", action="store_true",
                    help="L3: regenerate generated blocks and fail if anything drifted")
    ap.add_argument("--baseline", action="store_true",
                    help="L4: (re)write the per-page hash baseline")
    a = ap.parse_args()

    print(f"auditing {TEX.relative_to(ROOT)} / {PDF.name}")
    src = TEX.read_text(encoding="utf-8")
    floats = layer1(src)
    layer2(floats)
    layer2_fonts(src)
    layer2_widths(src)
    layer5_proofmarks(src)
    if a.agreement:
        layer3()
    layer4(a.baseline)

    print()
    for w in warns:
        print(f"  warn  {w}")
    for f in fails:
        print(f"  FAIL  {f}")
    print(f"\n{len(fails)} failures, {len(warns)} warnings")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
