# Budget-Constrained Embodied Perception — artifact

Pre-registration, protocol, corpus generator, and the complete per-question measurement
records for the ASP (Access-Structured Perception) study: four resource walls for budgeted
embodied perception, and an equal-budget comparison of seven access structures across seven
open multimodal backbones (3B–31B) on the synthetic **SEW-Bench** corpus.

Paper: [`paper/asp/asp.pdf`](paper/asp/asp.pdf) · Pre-registration: [`REGISTRATION.md`](REGISTRATION.md)

## Start here

    make verify

Offline, no API key, about a minute. It regenerates the corpus from its seed, then runs five
independent checks and exits non-zero if any of them disagrees with the paper:

| | Check | What a failure would mean |
|---|---|---|
| 1 | `analysis/check_bounds.py` | a closed-form ceiling printed in the paper does not follow from `data/sew/meta.json` |
| 2 | `annotation/selftest_regen.py` | the corpus does not regenerate bit-identically, so the released cells were measured on different frames |
| 3 | `scripts/selftest_budget.py` | the budget accountant can under-charge a call, so "equal budget" is not equal |
| 4 | `scripts/selftest_retry.py` | a provider fault could be silently scored as a model failure |
| 5 | `analysis/analyze.py` + `analysis/check_figures.py --agreement` | a number in a table or figure has drifted from `results/` |

Check 5 is the one that matters most: every table and figure in the paper is spliced in from
`results/` by generator scripts, so if the paper and the data ever disagree, regenerating
changes the file and the check fails.

## What the paper promises, and where it is

The paper's Reproducibility paragraph commits to releasing specific things. Each one:

| Promise | Path |
|---|---|
| the pre-registration | `results/registered_predictions.json` (SHA-256 `0af367149532d48a…`) |
| the pre-measurement tables the measured ones are diffed against | `notes/tab_main_reference.tex`, `notes/tab_ablation_reference.tex` |
| the protocol and all frozen prompts | `docs/PROTOCOL.md`, `scripts/methods/` |
| the SEW-Bench generator (fixed seed, bit-identical) | `annotation/generate_synthetic.py`, verified by `annotation/selftest_regen.py` |
| the EW-Bench generator up to its rendering call | `annotation/generate_ewbench.py`, `datasheet/ewbench_datasheet.md` |
| the budget accountant with its offline invariant tests | `scripts/openrouter_client.py`, `scripts/selftest_budget.py` |
| the per-question records behind every cell of every table | `results/cells/` (207 cells) |
| every deviation from the registration, logged with its reason | `notes/deviations.md` (D-01 … D-48) |
| the superseded records, released rather than discarded | `results/cells_pre_bm25fix/`, `results/cells_pre_bsfix/`, `results/cells_pre_cmpfix/`, `data/sew_pre_cmpfix/` |
| the EGAgent reimplementation parity checklist | `docs/EGAGENT_REIMPL.md` |

The three quarantine directories exist because three defects were found *after* measurement: a
retrieval-index tokeniser bug that invalidated 70 cells, a budget-accounting bug that
invalidated 4, and a corpus defect that made a third of one subtest answerable without seeing
any frames. In each case the affected cells were re-run and the superseded ones kept, so the
size of each measurement error is auditable. `notes/deviations.md` has the accounts.

## What is not here

- **The 1,200 corpus frames** (52 MB). They are a pure function of the seed;
  `make data` regenerates them in about 30 seconds and check 2 above asserts they come back
  byte-identical. A tarball is attached to the release for anyone who would rather not.
- **The offline keyframe caches** (`results/cache/`). Reproducible, but only by spending API
  tokens, so they are a release asset rather than a repository directory. Reproducing the
  *numbers* does not need them; re-running the *grid* does.
- **OpenEQA, VSI-Bench, EgoSchema, EW-Bench data.** Not ours to distribute. Their question
  sets are public; their frames sit behind HM3D, ScanNet, ScanNet++ and Ego4D agreements. The
  paper reports these as *not evaluated* rather than as passes.

## Re-running the measurements

Needs an OpenRouter key and costs roughly $15 for the full grid.

    export OPENROUTER_API_KEY=...          # never paste a key into a commit or a chat
    pip install -r scripts/requirements.txt
    python scripts/run_grid.py --phase offline  --jobs 12          # one-off, cached per (backbone, episode)
    python scripts/run_grid.py --phase main     --jobs 12 --resume
    python scripts/run_grid.py --phase ablation --jobs 12 --resume
    python scripts/run_grid.py --phase p3       --jobs 12 --resume
    python scripts/run_grid.py --phase sweep    --jobs 12 --resume
    make tables

`--only-subset {RET,TRK,CMP}` restricts any phase to one witness subtest; it filters the same
job list the full grid builds rather than taking a different code path.

Results will not match ours to the digit. The serving arm is an API whose provider routing and
quantisation are not observable to us, which the paper records as a limitation. What should
reproduce is the *ordering* of access structures at equal budget.

## Layout

    annotation/   corpus generators and the regeneration contract test
    scripts/      the ASP method, the six baselines, the budget accountant, the runners
    analysis/     verdicts, table/figure generation, bound arithmetic, float audit
    results/      the registration, 207 per-question cell records, three quarantines
    data/         question sets and metadata (frames regenerate)
    docs/         protocol, serving notes, EGAgent parity checklist
    notes/        deviation log, pre-measurement reference tables
    paper/asp/    the paper source and PDF

## Licences

Code (`scripts/`, `analysis/`, `annotation/`) is Apache-2.0 — see [`LICENSE`](LICENSE).
Corpus, records, registration and deviation log are CC BY 4.0 — see
[`LICENSE-DATA`](LICENSE-DATA), which also explains why "licence-free corpus" in the paper is
a claim about provenance and why an explicit outbound grant is still needed.

## One caveat about the pre-registration

This repository cannot prove *when* the predictions were written. It is a curated snapshot with
no development history, and the private development repository would not help: the project
entered version control in a single commit containing the registration and the results
together. [`REGISTRATION.md`](REGISTRATION.md) states this plainly and sets out what the
artifact does establish instead — content integrity via the hash, unrun clauses left intact,
48 logged deviations including six that damage our own claims, and two of four frozen
falsification criteria firing.
