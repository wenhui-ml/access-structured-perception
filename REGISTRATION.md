# Pre-registration

This file states what was frozen before measurement, what evidence there is that it was, and
the one respect in which that evidence is weaker than it should be.

## The registered artifact

`results/registered_predictions.json`

    SHA-256  0af367149532d48a4a8c5678d6d3528eb80acc29599b67cff8e0cf92b5a69fae

That hash is also printed in the paper. It pins the file's *content*: any later edit is
detectable by anyone. Verify with:

    shasum -a 256 results/registered_predictions.json

The registration contains the three headline predictions, their 90% prediction intervals, the
registered statistics (paired per-question deltas, one-sided Wilcoxon at α=0.01, with minimum
effect sizes), and the serving protocol. `notes/tab_main_reference.tex` and
`notes/tab_ablation_reference.tex` are the **pre-measurement tables**: every value in them
carries the `\pred{}` marker, and the paper's measured tables are the diff against them.

## The four falsification criteria, frozen verbatim

| | Criterion | Outcome |
|---|---|---|
| **F1** | `Uniform-w` comes within 10 points of ASP on EW-RET for any ≥27B backbone | did not fire |
| **F2** | ρ_scale under ASP is not lower than under `Uniform-w` by at least 0.2 | **FIRED** |
| **F3** | The ablation collapse pattern is crossed | **FIRED** |
| **F4** | `Uniform`@16k ≥ ASP@4k on both OpenEQA and EW mean | did not fire (OpenEQA half not evaluated) |

Two of four fired. The paper reports them as fired rather than revising them, and §5 explains
what each one means. F2 is additionally recorded as *uninformative* on this corpus, for a
reason that is a property of the backbone ladder an API catalogue allowed us to assemble
rather than of the prediction; that reasoning is in the paper, not here, and it does not change
the recorded outcome.

## What this artifact does and does not prove

**Does not prove: chronology.** This repository is a curated release snapshot with no
development history. The private development repository does not help either: the project
entered version control in a single commit that contains the registration and the results
together, so its git history provides no independent timestamp for the registration. We say
this plainly rather than leaving a reader to discover it. **Nothing here is cryptographic
evidence that the predictions were written before the measurements.**

**Does prove: content integrity, and self-incrimination.** What is auditable is stronger than
a timestamp in one respect and weaker in another, and both should be stated.

1. The registration is content-pinned by the hash above and released verbatim, unedited, with
   its unrun clauses intact. Three registered benchmarks (OpenEQA, VSI-Bench, EgoSchema) and
   the registered EW-Bench corpus were never run; their predictions remain in the paper marked
   `\pred{}` and recorded as *not evaluated* rather than quietly deleted or counted as passes.
2. `notes/deviations.md` logs 48 numbered deviations in chronological order, including six
   that damage our own claims: two false theorem statements, one invalid corollary
   simplification, one retrieval-index bug that invalidated 70 measured cells, one
   budget-accounting bug, and one corpus defect that made a third of a subtest answerable
   without any access to the stream.
3. Two of the four criteria fired, and one of the paper's three architectural components is
   reported as costing more than it returns. A registration reconstructed after seeing the
   results would not be one that fails against itself in two of four places.

That is an argument from the *shape* of the record, not a proof. A reader who wants
cryptographic assurance should discount item 0 and weigh 1–3 on their merits.

**For the next run.** The outstanding work listed in the paper (regenerating the natural-video
arm, the conjunctive witness subset, ε_u, EW-Bench) has not been registered yet. That
registration will carry an external timestamp — an OpenTimestamps proof or an OSF
registration — so this limitation does not recur.
