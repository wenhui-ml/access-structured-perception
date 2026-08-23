#!/usr/bin/env python3
"""Recompute every closed-form ceiling in the paper from the corpus metadata and check the
literal numbers in paper/asp/asp.tex against them.

Why this exists. The measured tables are generated (analysis/make_tables.py), so they cannot
drift from the data. The BOUNDS were not: kappa_s, the horizon ceiling, the round ceiling and
the various threshold conditions were typed by hand into Sec. 3, Sec. 5.6, App. A and App. B,
and a hand-typed bound is exactly the kind of number that survives a parameter change nobody
re-derives. Two real errors were found this way (notes/deviations.md D-35, D-36) plus one
arithmetic slip in the convergence constant, so the check is now a script.

Run:  python analysis/check_bounds.py      (exit 0 = every number in the tex agrees)
"""
from __future__ import annotations
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEX = ROOT / "paper/asp/asp.tex"
META = ROOT / "data/sew/meta.json"

L_S_TOKENS = 512      # Def. 2 state cap, and the --ls-tokens default of the generator
BETA = 12.0           # bits per token
B = 4096              # per-decision budget
W = 12                # realised uniform width at B and the measured tau (Sec. 5.1)
K_RETR = 8            # top-k of the episodic index
D_Q_MAX = 3           # deepest CMP chain SEW-Bench ships
TAU_MIN, TAU_MAX = 259, 432   # measured tokens/frame across the ladder

fails: list[str] = []


def check(label: str, computed, literal: str, fmt=lambda v: f"{v}"):
    """Assert that `literal` appears in the tex AND equals the computed value."""
    tex = TEX.read_text()
    want = fmt(computed)
    if want != literal:
        fails.append(f"{label}: recomputed {want!r} but the paper was checked against "
                     f"{literal!r} -- one of the two is stale")
    elif literal not in tex:
        fails.append(f"{label}: value {literal!r} is correct but does not appear in asp.tex; "
                     f"either the prose changed or the check is checking the wrong thing")
    else:
        print(f"  ok  {label:52s} {literal}")


def main() -> int:
    m_ep = json.load(open(META))[0]
    N, d, Nd, K = m_ep["n_frames"], m_ep["d_attributes"], m_ep["Nd"], m_ep["K"]
    m = int(L_S_TOKENS * BETA)
    lg = math.log2
    print(f"corpus: N={N} d={d} Nd={Nd} K={K} m={m} bits (L_s={L_S_TOKENS}, beta={BETA})\n")

    # --- Thm 1, perceptual Shannon wall
    kappa = (m / Nd + 1) / lg(K)
    check("Thm 1 kappa_s at SEW", kappa, "0.547", lambda v: f"{v:.3f}")
    check("Thm 1 kappa_s as a percentage", kappa * 100, "54.7", lambda v: f"{v:.1f}")
    # the superseded draft, quoted in Sec. 5.6 and App. B as the vacuous case
    check("Thm 1 kappa_s at the d=9 draft", (m / 1350 + 1) / lg(K), "1.85",
          lambda v: f"{v:.2f}")
    check("Thm 1 kappa_s at registered EW", (m / 43200 + 1) / lg(K), "0.381",
          lambda v: f"{v:.3f}")
    # vacuity threshold: the bound says nothing once m >= Nd(log2 K - 1)
    assert m < Nd * (lg(K) - 1), "Thm 1 is vacuous at these parameters"

    # --- Thm 2, horizon wall
    hz = W / N + (1 - W / N) / K
    check(f"Thm 2 ceiling at w={W}", hz * 100, "16.0", lambda v: f"{v:.1f}")

    # --- Lemma 3, no tracking without C_s
    check("Lem 3 ceiling 1/K", 100 / K, "12.5", lambda v: f"{v:.1f}")
    assert TAU_MIN <= TAU_MAX and B // TAU_MAX < N, "Lem 3 needs k_tot < N"
    print(f"  ok  Lem 3 hypothesis k_tot<N                          "
          f"{B // TAU_MAX}-{B // TAU_MIN} vs N={N}")

    # --- Thm 4(i), round wall with no cross-frame state
    rd = K_RETR / N + (1 - K_RETR / N) / K
    check(f"Thm 4(i) ceiling at k={K_RETR}", rd * 100, "14.8", lambda v: f"{v:.1f}")

    # --- Thm 4(ii)-(iii): VACUOUS here, and the paper says so. Check that too.
    loc = (m / N + 1) / lg(N / K_RETR)
    check("Thm 4(ii) localisation (vacuous)", loc * 100, "411", lambda v: f"{v:.0f}")
    check("Thm 4(iii) (vacuous)", (loc + 1 / K) * 100, "423", lambda v: f"{v:.0f}")
    if loc <= 1:
        fails.append("Thm 4(ii) is NOT vacuous at these parameters, but the paper says it is")

    # --- the counterexample that forced the Thm 4 restatement (D-35)
    for m_bits, claimed_s, adv_s in ((600, "0.699", "0.708"), (900, "0.890", "1.000")):
        claimed = (m_bits / N + 1) / lg(N / K_RETR) + 1 / K
        S = min(N, int(m_bits // lg(K)))
        adv = S / N + (1 - S / N) / K
        check(f"D-35 old claim at m={m_bits}", claimed, claimed_s, lambda v: f"{v:.3f}")
        check(f"D-35 tabulator at m={m_bits}", adv, adv_s, lambda v: f"{v:.3f}")
        if adv <= claimed:
            fails.append(f"D-35: the counterexample does not actually violate the old claim "
                         f"at m={m_bits}; the correction's justification is wrong")

    # --- Prop 2, strict super-additivity on T_conj
    check("Prop 2 condition Delta <", 1 - kappa - 1 / K + 1 / K ** 2, "0.344",
          lambda v: f"{v:.3f}")

    # --- Cor 1, dominance on the mixture: which branch, and the mixture arithmetic
    check("Cor 1 branch threshold (1+1/K)/2", (1 + 1 / K) / 2, "0.5625",
          lambda v: f"{v:.4f}")
    if kappa > (1 + 1 / K) / 2:
        fails.append("Cor 1: kappa_s exceeds the threshold, so the paper's first branch "
                     "no longer applies")
    check("Prop 2 remark: mixture RHS", (2 * kappa + 3) / 3 - 2 / (3 * K), "1.28",
          lambda v: f"{v:.2f}")

    # --- Cor 2, convergence constant
    check("Cor 2 constant c = 1+N+d_q", 1 + N + D_Q_MAX, "304", lambda v: f"{v:d}")

    print()
    if fails:
        for f in fails:
            print(f"FAIL  {f}")
        return 1
    print("all bound arithmetic in asp.tex agrees with the corpus metadata")
    return 0


if __name__ == "__main__":
    sys.exit(main())
