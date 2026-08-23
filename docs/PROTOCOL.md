# Pre-registration protocol (FROZEN 2026-08-21)

Grid: 5 backbones × 6 methods × {OpenEQA EM-EQA, VSI-Bench, EgoSchema, EW-RET/TRK/CMP}
at B=4096; budget sweep B∈{1k,2k,4k,8k,16k} on Qwen3.8-27B; ablations per Table 3.
Temperature 0; 3 seeds where sampling unavoidable; judge disjoint from backbones.
Headline predictions P1–P3 and falsification criteria F1–F4: see paper §5.2/§5.5.
Registered numeric predictions: results/registered_predictions.json (append-only).
Any deviation from this protocol must be logged in notes/deviations.md before running.

---

## Execution record (appended after the runs; the protocol above is unchanged)

The protocol above is the FROZEN registration and is not edited. What was actually run,
and where it departs, is recorded here and in `notes/deviations.md`.

**Ran:** 6 backbones × 7 methods × SEW-{RET,TRK,CMP} at B=4096; 7 ASP ablation variants
on Qwen3.8-27B; Uniform-w at B=16384 for P3. One serving arm (OpenRouter), temperature 0,
provider-side reasoning disabled, model fingerprint recorded per call.

**Did not run, and why:**

| Registered | Status | Reason |
|---|---|---|
| EW-Bench (900 Q, 60 HM3D/ScanNet walkthroughs) | not built | needs habitat-sim + HM3D/ScanNet licence |
| OpenEQA EM-EQA | not run | no licence-free path to episode-frame dumps |
| VSI-Bench | not run | same |
| EgoSchema | not run | same |
| Qwen2.5-VL-7B | substituted → Ministral 3B | slug does not exist on OpenRouter |
| Qwen3-Omni-30B-A3B | substituted → Qwen3-VL-30B-A3B | slug does not exist on OpenRouter |
| local vLLM primary arm | not run | user constraint: API-only |
| budget sweep B∈{1k,2k,8k} | not run | only the 4k vs 16k contrast that P3 needs |
| 3 seeds | n/a | temperature 0 and reasoning disabled make the runs deterministic |
| tab:probe (Assumption 1) | **RAN** | was "registered, not run"; `scripts/probe_assumption.py` measures eps_0 and eps_1 per backbone. eps_u is still unmeasured (a per-update probe is a different instrument) |
| S4(a) alpha sweep | RAN | local, no API cost. alpha=1 (vision-only) recall@8 = 0.005, so the index's competence is entirely textual on this corpus |

**Substituted in:** SEW-Bench (`annotation/generate_synthetic.py`), 4 episodes × N=300
frames, 80 questions (32/24/24), d=32 queryable K=8-ary attributes per frame so that
Nd=9,600 and Theorem 1 binds at kappa_s=0.547. Fixed seed; regenerates bit-identically.

**Commands.**

```bash
python annotation/generate_synthetic.py --out data/sew --frames 300 --episodes 4
python scripts/check_models.py                       # verify every slug against the live catalogue
python scripts/calibrate_tokens.py <slugs...>        # measure tokens/frame on the real frames
python scripts/run_grid.py --phase offline  --jobs 24
python scripts/run_grid.py --phase main     --jobs 24 --resume
python scripts/run_grid.py --phase ablation --jobs 12 --resume
python scripts/run_grid.py --phase p3       --jobs 12 --resume
python analysis/make_tables.py && python analysis/analyze.py
cd paper/asp && latexmk -pdf asp.tex
```


## Correction log (post-first-pass)

Two defects were found after the first full pass and both invalidated results rather than
merely slowing them down. Full detail in `notes/deviations.md`.

**D-41, BM25 tokenised on whitespace.** The v2 captions are comma-separated class inventories,
so the retriever's tokens were `belt,` / `ruler,` or one 17-class blob, and a query naming a
class matched nothing. Measured recall@8 was 0.00-0.22 with the target at median rank 121 of
300. After tokenising on non-alphanumerics: recall@8 = 0.91-1.00, median rank 1. Every cell
whose method ranks anything (asp, all asp_* ablations, retr_only, egagent -- 70 of 145) was
re-run; the pre-fix records are kept in `results/cells_pre_bm25fix/`. End-to-end confirmation
on one cell: Asp on SEW-RET with Qwen3-VL-8B went from 9.4 to 93.8, against the
Proposition 1 prediction of 1-(eps_0+delta_r) = 1-(0.06+0.00) = 0.94.

**D-42, Assumption 1 measured.** The first-pass grid sat near chance almost everywhere, which
has two incompatible explanations (access structure binding, versus backbones unable to read
the frames) that the grid cannot separate. The probe settles it: 1-eps_0 = 0.71-1.00 against a
0.125 floor, so perception per access is not the problem -- which is what made D-41 findable.
The one-step margin 1-eps_1 is weaker: four of seven backbones at or below the 50% chance line.
