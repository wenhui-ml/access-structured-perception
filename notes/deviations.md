deviations log (empty)
2026-08-21 (pre-run revision, logged before any measurement):
 - Added Theorem 4 (unconditional round wall via pointer chasing); Thm 3 now explicitly secondary/conditional.
 - Serving: PRIMARY = local vLLM on B300 (BF16, pinned, no prefix cache, bs=1); OpenRouter demoted to replication arm. No on-device latency claims anywhere; edge-scale = model class + budget (Sec 4.5 cost model).
 - Added EGAgent (ACL 2026) reimplementation as 6th equal-budget baseline + registered predictions row.
 - Registered statistics switched to paired per-question deltas + Wilcoxon with min effect sizes.
2026-08-21 (structure revision, pre-run): consolidated to 6 sections
 (Intro / Related / Theory / Method / Experiments+Analysis / Limitations+Conclusion);
 added Def. 4 (wall price), remarks after Thm 1-2, Algorithm 1, design rationales,
 metrics + implementation-details paragraphs, EGAgent head-to-head + threats-to-validity
 paragraphs; +22 references (total 72); float fixes ([!t], footnotesize main table,
 raggedbottom, clearpage before appendix). No registered numbers changed.
2026-08-22 (theory correction, pre-run — CLAIM CHANGE, no registered number changed):
 - CORRECTED Prop. 1. The old form asserted strict super-additivity
   Cap(Cs+Cv+rho) > Cap(Cs) + Cap(Cv) - Cap(empty) on the uniform mixture
   T = 1/3(T_ret + T_trk + T_cmp). That inequality is FALSE as stated: on the mixture each
   single channel is near-ceiling on two of three families, so the RHS exceeds 1 unless
   kappa_s < 1/K. At our own operating point kappa_s ~= 0.380 vs 1/K = 0.125, giving
   RHS ~= 1.17 > 1 >= any hybrid. Split into:
     Prop. 1 = access-completeness only (per-family bounds, unchanged);
     Prop. 2 = strict super-additivity on a NEW conjunctive witness T_conj (RET and TRK
               components both required), valid under the explicit slack condition
               Delta < 1 - kappa_s - 1/K + 1/K^2  (= 0.510 at EW-Bench parameters);
     Cor. 1  = strict dominance over the BETTER single channel on the mixture,
               gap >= 1/3 (1 - 1/K - Delta_T).
   Abstract and Intro contribution bullet reworded to match. The arithmetic reason the
   mixture cannot carry the additive form is stated in the paper (Sec 3 + App A.8), not hidden.
 - FIXED Thm 1 denominator: bound is over the total ATTRIBUTE count Nd, not the keyframe
   count N. Sec 6's ceiling computation read "1 - (6100/450+1)/3 ~= 0.62", which evaluates to
   -3.85; the stated 0.62 requires Nd ~= 43,200, i.e. d ~= 96 attributes/keyframe. d is now a
   MEASURED, logged corpus property with the schema that yields it given in App B.2, and the
   ceiling is recomputed per walkthrough rather than from the corpus mean.
 - REPLACED the deferred reduction in Prop. 1's proof ("formalized via a reduction in the
   long version") with Lemma 3 (no tracking without a compressive channel): a verbatim-only
   agent reading k_tot < N keyframes is pinned at exactly 1/K on sum-mod-K tracking. Proved
   directly by an exposure argument, because the old route via Thm 2 does not go through for
   query-conditioned retrieval. Requires a stated read-only-retrieval convention (App A.1).
 - PROMOTED two proof sketches to full proofs: Thm 3 now has the S5 embedding as Lemma 1
   (projection reduction, explicit generators, explicit query); Thm 4 now has Lemma 2
   (list-decoding Fano) and a complete two-case bound, and its Sec 3 statement was rewritten
   to match what is actually proved (R=1 only; the R<d_q hierarchy is cited, not claimed).
 - Appendix expanded 1,145 -> 5,608 words: App A.1 standing conventions, A.8 why the mixture
   fails, A.9 scope-of-quantifiers; App B full EW-Bench protocol incl. the d schema and a
   hand-worked CMP item (labelled constructed, not measured); App C anchor arithmetic and
   three named ways the prediction methodology can fail; App D S1-S5 specified to runnable
   detail with per-experiment registered expectations.
 - Paper 18 -> 25 pages. Clean build, 0 undefined refs/cites, 0 multiply-defined labels,
   2 sub-4pt overfull boxes (both pre-existing).
2026-08-22 (front matter, no claim or number changed):
 - De-anonymized: six authors / three affiliations via authblk. Peiji Long assigned
   affil 3 (Independent Researcher), name spelling aligned to longpeiji@gmail.com.
   Chi Man Vong marked corresponding.
 - Added \ifanon switch (asp.tex L50-52) so one source builds both the named preprint
   and the double-blind submission. Anonymous build verified: 0 names/emails/affils on p1.
 - Title wrapped to \Large so the three intended manual line breaks actually fit; before
   this the first line overflowed and left "Structure:" alone on line 2.
 - No funding or acknowledgments section: none exists and none is planned. The "add funding"
   item was removed from SUBMIT.md rather than left as a dangling TODO.
2026-08-22 (figures, no claim or registered number changed):
 - +3 figures (3 -> 7 total). All seven now referenced from prose; before this pass
   fig:curves had no \ref anywhere either, which is now fixed.
   * Fig. 3 fig_argument (Sec 3): the argument as a dependency graph. Solid = unconditional
     (Thm 1, 2, 4, Lem 3), dashed = rests on TC0 != NC1 (Thm 3). Makes visible that the
     conditional result is not load-bearing.
   * Fig. 4 fig_router (Sec 4.4): (a) per-class budget partition = choosing a row of Tab 1;
     (b) the same budget actually spent on the worked CMP item, zoomed axis, showing the
     allocation is a cap (997 of 4096 spent, 76% returned).
   * Fig. 5 fig_witness (Sec 5.1): the three EW subtests as keyframe strips, with the
     ~16-of-450 read budget DRAWN TO SCALE. Shows the three failure modes are orthogonal
     by construction, which is what makes the collapse pattern diagnostic.
   * Fig. 7 fig_collapse (Sec 5.4): the ablation delta matrix, diagonal boxed. Turns Tab 3
     into the *shape* F3 tests; a crossed pattern refutes even if ASP wins every benchmark.
 - Two figures were redesigned mid-pass after review: fig_router v1 merely restated Tab 1
   (added panel b), and a planned access-loop state machine was DROPPED as a third redundant
   view of the loop already carried by Fig 1's arc and Algorithm 1 - replaced by fig_witness,
   which had no prior representation in the paper.
 - Added the missing prose for Sec 5.3 (what to check first in Tab 2: the *location* of the
   margin, EGAgent within 4 pts on EW-RET but 16 behind on EW-TRK as the diagnostic cell).
 - FIXED an inconsistency introduced by me in the previous pass: the App B.5 worked example
   listed (410,1638,2007), close to the RET profile, while the text said cmp. Correct CMP
   allocation is 0.25/0.35/0.40 x 4055 = (1014,1419,1622); the derivation is now shown inline.
 - Paper 25 -> 27 pages. Clean build, 0 undefined, 0 dup labels, 2 sub-4pt overfull (both pre-existing).
2026-08-22 (Related Work expansion, no claim or registered number changed):
 - Sec 2 rewritten: 868 -> 2,252 words, reorganised around one question per line of work
   ("which channel does it commit to, which wall does that leave unpaid?"). Constraint held
   throughout: NO new bibliography entries. Every citation is one of the 80 already in
   references.bib, so nothing was added that could not be checked. The single previously
   uncited entry (videomme) is now used in the benchmarks paragraph; bib is 80/80 cited.
 - NEW Table 1 (tables/tab_related.tex): related work by channel possessed
   (Cs / Cv / adaptive R / explicit B) with the wall each class cannot pay. Rows are
   CLASSES with representative citations, not individual systems, deliberately: a per-system
   capability matrix would assert more about each paper than we can verify, whereas the
   class-level claim is what the theory actually establishes. Borderline cells are marked
   partial rather than argued, and the caption says the classification is by published
   design commitment, not measured performance.
 - Two paragraphs added that a theory paper needs and this one lacked:
   * "The lower-bound toolkit, and where it has not been pointed" -- states plainly which
     machinery is borrowed (Fano/counting, pointer-chasing rounds, Barrington x TC0) and
     that the novelty is the target and the single-budget accounting, not the technique.
     Also names Lem 3 as the one bound with no off-the-shelf form.
   * "Pre-registration as method" -- situates the methodology and states its cost honestly
     (registered values will be wrong in places and the record is public).
 - Sharpened the long-context paragraph to the actual asymmetry (width defers the horizon
   wall at linear cost but cannot touch the composition wall, where depth binds), and the
   test-time-compute paragraph to what differs from the text setting (allocation over
   *access* arms with provable unequal returns, not over difficulty).
 - Paper 27 -> 29 pages; 7 figures, 5 tables. Clean build, 0 undefined, 0 dup labels,
   2 sub-4pt overfull (both pre-existing).
2026-08-22 (serving-description consistency sweep, no claim or number changed):
 - Resolved the last known internal contradiction. Sec 4 opened with "served over an API
   (here: OpenRouter)" while Sec 4.5, the abstract, Sec 5.1, SERVING.md and
   registered_predictions.json all say PRIMARY = local vLLM, OpenRouter = replication arm.
   Fixed in five places, all of them descriptions of the same setup:
   * sections/04_method.tex:4 -- now "OpenAI-compatible completion endpoint: locally served
     vLLM for all primary numbers, OpenRouter for the replication arm; nothing in ASP
     depends on which of the two answers."
   * tikz/fig_overview.tex -- backbone box read "(<=31B, OpenRouter)", now "(<=31B, local vLLM)".
     This one mattered most: it is the first figure a reader sees.
   * docs/README.md -- opening line said the work runs "via OpenRouter"; now states the
     primary/secondary split and points at SERVING.md. Repro block now shows ASP_API_URL
     for the local arm instead of implying the API key is required for primary numbers.
   * scripts/openrouter_client.py -- module docstring generalised to "OpenAI-compatible";
     documents ASP_API_URL and notes the accounting is identical for both arms, which is
     what makes the local-vs-API delta measurable rather than a confound.
   * scripts/methods/asp.py -- docstring no longer says the backbone is "served via OpenRouter".
 - Nudged the $B_s$ tokens label in Fig 1 clear of the compressive-channel box corner.
 - Verified: latexmk clean, 0 undefined refs/cites, both touched Python files still parse.
2026-08-22 (single-file source, no content change):
 - paper/asp/asp.tex is now the COMPLETE paper: all 9 section files, 7 tikz figures and
   5 tables inlined; 0 remaining \input. 1,158 lines / 137 KB. Matches the house style of
   the sibling manuscripts (ecp.tex, vwv.tex), which are monolithic.
 - Verified byte-identical: pdftotext of the flattened build diffed clean against the
   component build before the swap (29 pages both).
 - CRITICAL rewiring, or the backfill path would have been silently severed:
   analysis/make_tables.py previously WROTE paper/asp/tables/{tab_main,tab_ablation}.tex.
   With tables inlined those writes would have gone to files nobody reads, so the paper
   would still show registered predictions after a real measurement run. It now splices
   both tables into asp.tex between
     % ===== BEGIN/END GENERATED TAB_MAIN|TAB_ABLATION =====
   and RAISES rather than no-ops if a marker is missing. Round-trip tested: re-running
   make_tables.py regenerates both tables in place and the PDF stays identical.
 - Old components moved to paper/asp/legacy_components/ with a README saying they are a
   recovery copy only and will go stale. Not deleted: this tree has one commit and the
   files were untracked, so there was no other copy.
 - README.md, docs/README.md, SUBMIT.md updated (SUBMIT.md's "overlay measured points"
   item pointed at tikz/fig_curves.tex and at Fig. 3; the curves figure is now Fig. 6).
2026-08-22 (code audit + fixes; no paper number changed):
 Audited all 773 lines of scripts/, analysis/, annotation/. Seven defects, five of which
 would have silently produced plausible-looking but invalid numbers.

 FIXED
 1. Verbatim channel was not visual at all. asp.py passed frame PATHS to
    sentence-transformers CLIP encode(), which encodes strings as TEXT. So the keyframe
    gate compared filenames ("frame_0001.jpg" vs "frame_0002.jpg") and the episodic index
    matched natural-language queries against path-string embeddings. C_v -- the core of
    the paper -- was doing nothing. Added embed_images() (PIL -> encode) and embed_text(),
    with a cache shared by the gate and the index.
 2. Equal-budget comparison did not bind. BudgetedSession.chat() checked only
    remaining()<=0 on ENTRY, then let a single call overshoot arbitrarily and merely logged
    it. Asymmetric across methods: many-small-call methods (ASP) were truncated correctly
    while one-big-call methods were not, so Table 2 would have been a comparison at
    UNEQUAL budgets. Added a pre-call estimate (text/4 + n_img*img_tokens + max_completion)
    that refuses the call. scripts/selftest_budget.py asserts the invariants offline.
 3. EW free-form cells inflated up to 100x. score() returned 0/1 for MCQ but [0,100] for
    LLM-Match, and commit() then multiplied everything except OpenEQA by 100. All of
    EW-CMP and the non-MCQ part of EW-RET/TRK were affected. score() is now always [0,100]
    and commit() never rescales.
 4. Router allocation was decorative. run_asp computed (Bs,Br,Bc) but only the TOTAL was
    tracked, so water-filling had no effect on behaviour and App. D's registered claim
    about the realised split was unmeasurable. Added a per-channel ledger keyed off call
    tags, per-channel caps enforced in the loop, and sess.split() in the trace.
 5. EGAgent baseline was unreachable: defined in baselines.py, absent from answer_one()
    dispatch and from --method choices, and its entity_graph had no builder. The paper's
    headline head-to-head could not be run. Wired up; added build_entity_graph().
 6. Per-keyframe update allowance was budget=10**9, i.e. unenforced, against Sec 4.5's
    "one bounded update call (<= L_s + L_x)". Now metered at (L_s+400) per keyframe.
 7. Paper says BM25, code was a Jaccard overlap ratio with no IDF term -- unable to do the
    one job Sec 4.3 assigns it (disambiguating near-duplicate frames by rare words).
    Replaced with Okapi BM25, max-normalised to scale-match the cosine term.

 FINDING THAT NEEDS A PAPER DECISION (not silently patched)
 - Uniform-16 does not fit B=4096. Sec 5.1 states 230-280 tokens/frame; 16 frames costs
   3,680-4,480 tokens for the IMAGES ALONE, before prompt, question or answer. It fits only
   at the bottom of the paper's own stated range: at 250 tok/frame it overruns by ~92, at
   280 by ~572. Sec 5.1's parenthetical "(approx 16 images at low-res tokenization)" treats
   16 images as the WHOLE budget. So the registered default baseline is infeasible at the
   default budget for the upper part of the backbone range, and every Uniform-16 cell in
   Table 2 assumes something the accounting forbids.
   Interim code behaviour: uniform() now sends the largest w that fits and logs
   w_requested vs w_realised, so the shortfall is measured rather than hidden or crashed.
   The paper still says "Uniform-16" in Table 2, P1, P2, F1, F2 and Figs 5/7, so the naming
   and the registered values need an explicit decision -- flagged to the authors, NOT
   changed unilaterally, because it touches registered predictions.

 ADDED
 - scripts/check_models.py: resolves slugs against the live OpenRouter catalogue and
   reports whether each accepts images (a text-only model answering a visual question
   would look like a result). Run before spending anything.
 - scripts/selftest_budget.py: offline budget invariants via a fake transport. Passes.
 - PILOT_MODELS roster behind ASP_PILOT=1, kept separate from the registered grid.
 - docs/PILOT.md: what a pilot number can and cannot support, with the Assumption-1
   argument for why P1/P2 are not testable below the representational threshold and P3 is
   the sensible pilot headline; plus the rule that pilot numbers go to results/pilot.json,
   never results/measured.json.
2026-08-22 (Uniform-16 feasibility, resolved minimally):
 - Kept the name, the registered values, and every method key. Fixed only the sentence
   that was actually wrong: Sec 5.1 claimed 230-280 tokens/frame while asserting 16 frames
   fit B=4096, which is false above ~240 tokens/frame (16 x 280 = 4,480 > 4,096 before
   prompt or answer). Sec 5.1 now PINS the image resolution per model at <=240 tokens/frame,
   states the arithmetic, and says that where a backbone cannot reach it, w drops to the
   largest uniform sample that fits and the realised w is reported per cell -- equal budget
   means equal tokens, not equal frames.
 - BudgetedSession.img_tokens 300 -> 240 to match the pinned figure; selftest updated
   (Uniform-16 now asserted to FIT at 240, and a 24-frame call asserted to be refused).
 - Deliberately NOT done: renaming uniform16 -> uniform_fill across 6 files and 14 spots in
   asp.tex. It would have touched registered predictions and every Uniform cell for a
   naming improvement, and the one-paragraph fix removes the contradiction without it.
2026-08-22 (OpenRouter model selection, MEASURED -- supersedes the earlier 240 assumption):
 - Surveyed the live catalogue: 250 image-capable models. Restricted to the class Sec 5.1
   is actually about -- OPEN-WEIGHT, image-capable, <=31B total or active -- which excludes
   the cheap proprietary small models (gpt-5-nano, gemini-flash-lite): a proprietary pilot
   would not be on-topic for a paper whose claim is about open models.
 - Probed 14 candidates with one real single-frame question (scripts/probe_models.py).
   Only 4 both resolved AND answered correctly. Presence in the catalogue is not usability:
     PASS  ministral-3b-2512, qwen3-vl-8b, gemma-3-12b, qwen3-vl-30b-a3b (+ gemma-3-27b,
           reserved as judge)
     FAIL  gemma-3-4b-it / mistral-small-3.2-24b / gemma-4-26b-a4b:free -> provider 429
           ministral-8b "Brown", ministral-14b "Gray", nemotron-nano-12b-vl "brown"
           (and 3,359 prompt tokens for ONE frame), qwen3.5-9b -> empty string
 - CALIBRATED per-image token cost by differencing 0/1/3-frame requests
   (scripts/calibrate_tokens.py). Linear in frame count for all five working models:
     gemma-3-12b/27b 259 | qwen3-vl-8b, qwen3-vl-30b-a3b 302 | ministral-3b 432
   EVERY value is above the 240 the paper had pinned. So Uniform-16 at B=4096 is
   unaffordable for EVERY backbone in the class, not just the dear end: the frames alone
   cost 4,144-6,912 tokens. Max affordable w is 15 / 12 / 9 respectively.
 - Sec 5.1 corrected AGAIN, this time from measurement rather than assumption: it now
   states the differencing method, the three measured constants, the resulting w ceilings,
   and that w is set per backbone with the realised value reported per cell. The earlier
   "pinned <=240 tokens/frame" claim was my assumption and was wrong.
 - Label changed \textsc{Uniform-16} -> \textsc{Uniform-}$w$ throughout asp.tex (one sed,
   17 occurrences). Code/JSON keys deliberately left as uniform16 -- an identifier, not a
   claim -- to avoid touching registered predictions for a naming change.
 - openrouter_client: IMG_TOKENS table of measured constants, applied per session in
   __post_init__; default raised 240 -> 320 (conservative). selftest updated to assert what
   measurement says: w=16 refused at 302 tok/frame, w=12 accepted.
 - Judge/backbone leakage avoided: gemma-3-27b passes the probe but is reserved as the
   LLM-Match judge and excluded from PILOT_MODELS, since App. B requires the judge be
   disjoint from every evaluated backbone.
 - Retry policy widened: provider-side 408/409/422/429/5xx are retried with backoff and the
   response body is surfaced on failure. Observed live: gemma-3-4b-it returned 422 then 429
   for an image request qwen3-vl-8b served fine, and the old client crashed on the 422.
2026-08-22 (first pilot where the walls actually bind; PILOT ONLY, not in the paper):
 - Built annotation/generate_synthetic.py: licence-free long-horizon streams standing in
   for EW-Bench (habitat-sim + HM3D unavailable). N=150 keyframes x 2 episodes, K=8 colour
   alphabet, d=9 attributes/keyframe, 12 questions (6 RET / 4 TRK / 2 CMP).
   Design choice: object CLASS is drawn as text, the queried ATTRIBUTE (colour) is not --
   labelling the colour would turn every RET item into OCR and hand the verbatim channel an
   advantage unrelated to vision.
   Validation gate added after the first draft emitted TWO contradictory RET items about
   "the lamp in the living room": a confident gold label on an unanswerable question shows
   up as a model failure, so the generator now refuses to ship ambiguous items.
 - keyframe_gate: tau_g<=0 is now identity. The gate thins sensor-rate video; applying it to
   an already-keyframed corpus thinned twice (300 -> 29 frames), giving N/w=1.9 and a
   horizon ceiling of 0.58, which makes Thm 2 say almost nothing.
 - Per-episode disk cache for the online phase (results/cache/). It depends only on
   (backbone, episode, tau_g), but run_eval is invoked per (method, subset) cell, so without
   it the same N update calls were paid 3x. Measured 0.53 -> 0.12 USD; 11 of 12 cells ran
   with ZERO API calls.
 - FIXED: the online-phase budget was a POOL of (L_s+400) x N, but Sec 4.5's L_s+L_x is a
   PER-CALL bound and a real call costs ~1,184 tokens (state 512 + image 302 + instruction
   120 + output 250). The pool ran dry at keyframe ~117/150 and BudgetExhausted escaped
   uncaught, killing the first run. Sized from the measured img_tokens now, and a truncated
   online phase warns loudly instead of committing a cell built on a partial stream.
 - FIXED: openai/gpt-5-mini REQUIRES reasoning and rejects reasoning.enabled=false with a
   400. The blanket disable killed the judge on the first call. Latched per session + retry.

 RESULTS (qwen3-vl-8b, N=150, w<=12 affordable at 302 tok/frame, 12 questions):
              RET    TRK    CMP   mixture
   Uniform-w  16.7   25.0   50.0    30.6
   State-only  0.0   50.0   50.0    33.3
   Retr-only  83.3   25.0   50.0    52.8
   ASP        83.3   50.0   50.0    61.1

   Thm 2 (horizon): ceiling w/N+(1-w/N)/K = 19.5%; measured Uniform-w 16.7% -> UNDER, the
     wall binds. This is the first run where it says anything: the previous 6-frame smoke
     stream had w=N, so the ceiling was 100%.
   Lem 3 (no tracking without C_s): precondition k_tot(12) < N(150) holds; Retr-only 25.0
     vs State-only 50.0 -> predicted direction HOLDS.
   Cor 1 (dominance over the better single channel): ASP 61.1 vs 52.8, +8.3 pts, and ASP is
     >= the better channel on EVERY subtest -> HOLDS.
   Thm 1 (Shannon) is VACUOUS here: kappa_s = (m/(Nd)+1)/log2 K = 1.85 > 1 because the state
     carries 6,144 bits against only Nd=1,350 stream attributes. State-only RET = 0.0 is
     therefore NOT evidence for Thm 1 -- it fails for practical reasons (the typed state does
     not retain per-object colour). Making Thm 1 bind needs Nd > m/2: at N=250, d=51 gives
     kappa_s=0.49. That is the next corpus change and it is NOT done.

 LIMITS, stated so no one over-reads this: 12 questions (scores quantised at 16.7/25/50),
 CMP identical at 50.0 for all four methods so it has no discriminating power, one backbone,
 2-D schematic renders not egocentric video, n=12 admits no statistical test. All values live
 in results/pilot.json and are excluded from the paper by file routing, not by convention.

================================================================================
FULL MEASURED GRID: corpus rebuild, six-backbone ladder, API-only
================================================================================

Goal for this pass: turn the paper from a pre-registration into an experimental paper.
Everything that cannot be measured without a licence or a GPU is moved to future work and
SAID to be future work; everything else is measured.

--------------------------------------------------------------------------------
D-20  CORPUS REPLACED: data/synth (N=150, d=9) -> data/sew (N=300, d=32)   [CLAIM CHANGE]
--------------------------------------------------------------------------------
WHY. Thm 1's ceiling is kappa_s = (m/(Nd)+1)/log2 K, over the ATTRIBUTE count Nd. At the
old parameters Nd = 1,350 against m ~ 6,144 bits of state, so kappa_s = 1.85 > 1 and the
theorem was arithmetically vacuous -- the previous pass said so explicitly and left it
unfixed. Raising N alone is the expensive lever (offline cost is linear in N x backbones);
raising d is free. SEW-Bench now renders 16 objects per frame, each with TWO K=8-ary
attributes read off pixels (colour, printed digit), so d = 32 and Nd = 9,600 at N = 300:

    kappa_s = (6144/9600 + 1)/3 = 0.547   -> Thm 1 BINDS (State-only RET <= 54.7%)

d counts only K-ary attributes; room, door state and frame index are excluded, which makes
the ceiling conservative rather than flattering. Filler classes and their attributes are
re-randomised every frame, so the entropy the state must discard is real -- with a fixed
per-room layout the stream would carry only |rooms| x 16 x 2 attribute values in total and
the Nd in the bound would be a fiction.
ALSO: 80 questions (32 RET / 24 TRK / 24 CMP) over 4 episodes, up from 12, so the
registered paired Wilcoxon tests are actually runnable. Superseded artifacts:
results/superseded/.

--------------------------------------------------------------------------------
D-21  BENCHMARK RENAMED IN THE PAPER: EW-Bench -> SEW-Bench for everything measured
--------------------------------------------------------------------------------
EW-Bench (900 Q over 60 HM3D/ScanNet walkthroughs) was registered and is NOT BUILT:
annotation/generate_ewbench.py still raises NotImplementedError, and rendering it needs
habitat-sim plus an HM3D/ScanNet licence. Reporting synthetic numbers under the registered
name would be the single most misleading thing available here, so the measured corpus gets
its own name, the paper says in the abstract and in Sec 5.1 that it is a 2-D schematic
render, and the EW-Bench design is retained in App B.2 as "registered, not built".

--------------------------------------------------------------------------------
D-22  THREE REGISTERED BENCHMARK COLUMNS NOT RUN
--------------------------------------------------------------------------------
OpenEQA, VSI-Bench, EgoSchema: no licence-free path to episode-frame dumps. Their frozen
predictions are reproduced in Table 7 (tab:registered), still dagger-marked, and are NOT
claimed as results. Consequence, stated in the paper rather than buried: P2's OpenEQA
sub-clause and P3's OpenEQA clause are recorded as NOT EVALUATED, not as passed.

--------------------------------------------------------------------------------
D-23  BACKBONE LADDER: 6 models, 2 substitutions
--------------------------------------------------------------------------------
Ministral-3B (3B), Qwen3-VL-8B (8B, registered), Gemma-3-12B (12B), Qwen3.8-27B (27B,
registered flagship), Qwen3-VL-30B-A3B (30B/A3B), Gemma-4-31B (31B, registered).
qwen/qwen2.5-vl-7b-instruct and qwen/qwen3-omni-30b-a3b-instruct DO NOT EXIST in the live
OpenRouter catalogue (scripts/check_models.py, 421 models). Ministral-3B takes the small
slot; Qwen3-VL-30B-A3B takes the MoE slot but is NOT an omni model, so no audio-modality
claim is made from it. openrouter_client.py now keeps REGISTERED (record only) separate
from MODELS (the measured ladder) so the two can never be confused in code.

--------------------------------------------------------------------------------
D-24  ONE SERVING ARM (OpenRouter), NO GPU
--------------------------------------------------------------------------------
The registration named local vLLM as primary with OpenRouter as replication. Only the API
arm was run, at the user's explicit and repeated instruction. Controls kept: pinned slugs,
temperature 0, provider-side reasoning disabled, returned model fingerprint recorded per
call. Controls LOST: provider routing, quantisation, silent revision changes. Also:
sentence-transformers is now pinned to device="cpu", because it grabs CUDA whenever it is
visible and GPU work on this host goes through slurm.

--------------------------------------------------------------------------------
D-25  BUG: data URIs said "image/jpg", which is not a MIME type      [WOULD HAVE LOST 3 BACKBONES]
--------------------------------------------------------------------------------
_img_content derived the data-URI type from the file extension, emitting
"data:image/jpg;base64,...". Qwen's provider tolerates it; DeepInfra (the Gemma family)
returns HTTP 422 with the message "Input should be <ChatMessageRole.TOOL: 'tool'>" -- a
complaint about message ROLES, which is why this read as a broken backbone rather than a
one-word bug. Every Gemma cell would have been unrunnable. Fixed with an extension->MIME
map; the error path now also prints the payload shape, since a provider schema complaint
that names the wrong field is otherwise only findable by hand-bisecting.

--------------------------------------------------------------------------------
D-26  BUG: IndexError killed an offline job mid-episode
--------------------------------------------------------------------------------
SceneState.update did `m.group(1).strip().splitlines()[0]` on the CAPTION match. A model
that emits the marker and then nothing gives an empty string, splitlines() returns [], and
[0] raises -- taking the whole episode down at whichever keyframe it first happened.

--------------------------------------------------------------------------------
D-27  CAPTION SCHEMA v1 -> v2, after measuring that v1 broke Assumption 1(ii)  [METHOD CHANGE]
--------------------------------------------------------------------------------
This is the most consequential change in this pass and it was made on measured evidence,
before the answer grid was run.

MEASUREMENT FIRST (analysis/retrieval_recall.py, zero API cost -- the index and captions
are cached and the ranking is local): with v1 free-form one-line captions, the episodic
index returned the RET target inside the top k=8 in 0.06-0.12 of items. delta_r = 0.88 to
1.00. Assumption 1(ii) of the paper -- retrieval finds the target with probability
>= 1 - delta_r -- was flatly false. Cause breakdown, which the script separates because the
two defects have different fixes: in 24 of 28 misses for Ministral-3B and 16 of 16 for
Gemma-3-12B the target's OWN caption did not contain the target's class name at all. A
one-line caption cannot inventory 16 objects, so BM25 had nothing to match.

Left uncorrected, ASP and Retr-only would have been pinned near chance on RET, the
"scissors gap" would have failed, and the failure would have been about a caption's recall
rather than about access structure -- a null result that says nothing either way.

FIX. CAPTION_VERSION = 2 asks for the object-class INVENTORY (room, door state, then every
visible class name), with the caption allowance raised from 64 to 192 tokens on the
fallback path. It does NOT leak an answer: the queried attributes (colour, printed digit)
are never named in the caption and stay in the pixels, so the caption's only job is to make
the right frame findable -- which is exactly what Sec 4.3 assigns the verbatim channel.
The same captions feed Socratic, EGAgent, Retr-only and ASP, so no method gains relative
to another.
HONESTY. This changes a method component after seeing data. It is not a change made to
improve a score -- delta_r was measured before any answer cell was run, and the criterion
was the pre-registered assumption, not the outcome. CAPTION_VERSION is part of the offline
cache key so v1 and v2 indices can never mix, and the v1 caches are kept in
results/superseded/cache_capv1/ so the measurement is reproducible.

--------------------------------------------------------------------------------
D-28  BUG: markdown-wrapped actions silently disabled the access loop
--------------------------------------------------------------------------------
run_asp matched actions with `out.strip().splitlines()[-1].startswith("STATE:")`. Models
emit "**STATE: objects**", so the match failed, the action fell to the NOTE branch, and the
loop degenerated for that backbone. Observed live on Ministral-3B, where a RET answer came
back as the literal string "**STATE: objects**". Now normalised (emphasis stripped, scan
upward for the first line that is an action). Related: the forced-guess path returned the
last line of the scratch context, which could be a bracketed bookkeeping note; it now
spends one small call on an actual answer when budget remains.

--------------------------------------------------------------------------------
D-29  SCORING: exact match with a judge fallback, not LLM-Match
--------------------------------------------------------------------------------
Table 2 registers the three witness columns as ACCURACY. SEW golds are single closed-
alphabet tokens, so a 1-5 judge scale would inject 25-point quantisation noise into a
comparison about a few points of separation. scripts/sew_score.py decides by rule when the
answer contains exactly one token of the relevant alphabet and DEFERS to the frozen judge
otherwise, so a verbose-but-correct answer is not scored 0 for being verbose. The deferral
rate is stored per cell, because a high one would mean the accuracy figure is partly a
judge figure. An empty answer is 0 without deferral.

--------------------------------------------------------------------------------
D-30  Uniform-w requests as many frames as B affords, not 16
--------------------------------------------------------------------------------
Previously w=16 was requested and silently shrunk. At the measured 259-432 tokens/frame,
16 frames do not fit B=4096 for ANY backbone, and for the P3 arm at B=16,384 a cap of 16
would have crippled the baseline the prediction is supposed to beat fairly. w is now
"largest uniform sample the budget affords" and the realised value is reported per cell.

--------------------------------------------------------------------------------
D-31  Infrastructure (no claim content)
--------------------------------------------------------------------------------
- Offline phase is resumable: the cache is written every 20 keyframes and a PREFIX of the
  target keyframe list is resumed from. At N=300 and ~5 s/call an episode is ~30 min, so a
  crash at keyframe 280 must not discard 280 paid calls.
- Frame embeddings cached to one npz per directory (was: recomputed per cell).
- scripts/run_grid.py drives offline/main/ablation/p3 phases as isolated subprocesses with
  --resume, so a rate-limit storm costs the affected cells only.
- Per-question records per cell (results/cells/*.json) including realised w and the
  realised (B_s,B_r,B_c) split. Without these, App D's registered split prediction and
  every paired significance test were unreportable.
- analysis/make_tables.py now reads results/cells/ (not a summary file), so a table can
  never disagree with the records the significance tests run on. Four generated tables:
  tab:main, tab:ablation, tab:p3, tab:registered.
- Ablations run through the SAME run_asp loop with one component disabled (use_cs, use_cv,
  use_router, random_retr, R), so a collapse is attributable to the component rather than
  to a different code path.

--------------------------------------------------------------------------------
D-32  STATE SCHEMA v2 -> v3: the compressive channel was not accumulating anything  [METHOD FIX]
--------------------------------------------------------------------------------
Found by reading the v2 caches, not by a failing test. Every backbone's final state held
the CURRENT frame's object list and no cumulative quantity whatsoever -- no counts, no
toggle tally, and `rooms` overwritten to the current room rather than kept as an ordered
trace. Sec 4.2 says C_s holds "the running reductions retrieval cannot cheaply rebuild",
and _evict() already contained `if "count" not in v` to protect counter-bearing entries --
but nothing ever created one, because the update prompt only said "add/merge objects". The
implementation contradicted its own design.

Consequence had it shipped: State-only cannot answer a TRK question in principle from a
state with no counters, so it would have scored near chance, ASP would have inherited the
same blindness through the same channel, and Lemma 3's contrast (verbatim pinned at 1/K on
TRK, compressive fine) would have been untestable. The TRK column would have measured
nothing.

FIX. STATE_SCHEMA is now {counts, env, rooms_visited, objects, event_log} and the prompt
asks for GENERIC reductions -- a cumulative sighting count per observed class, a binary
environment state with its change count, an ordered room trace -- never the specific
quantities the questions ask about. Two supporting details: the reductions are serialised
FIRST, so the L_s truncation that feeds the state back in eats per-object detail rather
than the counters; and _evict now only ever touches `objects`. Verified on 6 keyframes:
counts accumulate per class and door_changes increments.
NOTE ON BENCHMARK TUNING. The schema names cumulative counts and a binary environment
state. Those are the two reduction types Definition 1 already quantifies over, and they
are what any embodied state would carry; the prompt does not mention mugs, doors, or any
class in the corpus. It is still a change made with knowledge of the task family, and it is
recorded here as such.

--------------------------------------------------------------------------------
D-33  CORPUS: the printed attribute is a LETTER, not a digit
--------------------------------------------------------------------------------
The second K=8 attribute per object was a digit 0-7. Weaker backbones read it as a count:
after six frames Gemma-3-12B's state reported counts of 8 and 9 for classes that had been
seen at most six times. That turns the TRK column into a measurement of digit/count
confusion rather than of the compressive channel. Changed to capital letters A-H, same
alphabet size, same "readable only from pixels" property, no interference with counting.
scripts/sew_score.py matches letters CASE-SENSITIVELY with word boundaries, because
lowercasing first makes the English article "a" indistinguishable from the tag "A" and
would defer every letter item to the judge.

--------------------------------------------------------------------------------
D-34  Socratic and State-only truncate by BUDGET, not by a hardcoded constant
--------------------------------------------------------------------------------
socratic() kept the last 8,000 characters of captions and state_only() rendered 6,000
characters of state, both hardcoded. Whether that was more or less than B allowed depended
on the constant, and the entire premise of Table 2 is that every method spends the same
budget. Both now derive the room from sess.remaining(); socratic logs how many of the
available captions actually fit, because the resulting horizon limit on a text-only channel
is a measured quantity here rather than an implementation detail.

--------------------------------------------------------------------------------
D-35  MATH CORRECTION: Theorem 4 Case 2 was FALSE as stated
--------------------------------------------------------------------------------
The round wall previously claimed, for an agent with an m-bit cross-frame state and a single
non-adaptive retrieval round,

    Pr[correct]  <=  (m/N + 1)/log2(N/k)  +  1/K,

deriving the additive 1/K from "if the answer frame was not retrieved, the answer is a
uniform guess". That step is invalid: the answer a_{p_J} is a function of the stream, so an
m-bit state may simply CONTAIN it. Explicit counterexample -- a state tabulating the pairs
(j, a_{p_j}) for j in a fixed set S of size floor(m/log2 K) answers those queries with no
retrieval at all, achieving

    |S|/N + (1 - |S|/N)/K,

which at N=300, k=8, K=8 is 0.708 at m=600 bits where the claim allowed 0.699, and 1.000 at
m=900 bits where the claim allowed 0.890. The violation sits inside the range where the old
bound was non-vacuous, so it is not a corner case.

Theorem 4 is now three parts. (i) No cross-frame state: k/N + (1-k/N)/K, unchanged and
unconditional -- this is the part Retr-only and Socratic instantiate, since they have no C_s
and m=0. (ii) Localisation with an m-bit state: Pr[p_J in W] <= (m/N+1)/log2(N/k). This is
exactly what the List-Fano argument proves and it is a statement about ACCESS. (iii) The old
display, now with the added hypothesis that the agent is READ-GROUNDED (its answer is a
function of content it actually read, not of s_N alone), under which the 1/K step is valid.

Also recorded in the paper: for states that are neither read-grounded nor tabulators we have
no capability bound, and closing that -- a round/state tradeoff for pointer chasing under an
o(N)-bit advice string -- is genuinely open. The paper says so rather than implying coverage
it does not have.

--------------------------------------------------------------------------------
D-36  MATH CORRECTION: Corollary 1's simplification did not follow
--------------------------------------------------------------------------------
The dominance corollary simplified max{(2 kappa_s + 1)/3, (2 + 1/K)/3} to the second term
"since kappa_s <= 1". That is wrong: (2 kappa_s + 1)/3 <= (2 + 1/K)/3 holds iff
kappa_s <= (1 + 1/K)/2, and kappa_s <= 1 permits the first term to reach 1, well above
(2 + 1/K)/3 = 0.708 at K=8. The corollary now states the max explicitly with both branches.
The CONCLUSION is unchanged at our operating point -- kappa_s = 0.547 against the 0.5625
threshold -- but by a margin of 0.016, so which channel is the baseline to beat is a property
of the corpus and is now checked against the measured kappa_s rather than assumed.

--------------------------------------------------------------------------------
D-37  SCOPE: two of the seven bounds are VACUOUS at SEW-Bench parameters
--------------------------------------------------------------------------------
Evaluating every closed form at the parameters actually run (new Table 8) shows:
Thm 1 (kappa_s = 0.547), Thm 2 (16.0% at w=12), Lemma 3 (12.5%) and Thm 4(i) (14.8% at k=8)
all bind. Thm 4(ii)-(iii) do NOT: at m = 6,144 bits against N = 300 frames the localisation
bound evaluates to 411%, i.e. the state is large enough per pointer that a single round could
in principle localise, and the R=1 ablation's failure is therefore empirical rather than
information-theoretic. Thm 3 is asymptotic in d_q and our deepest chain is d_q = 3, so it
yields no number here at all. Additionally Prop 2 (super-additivity) has NO witness in the
corpus: SEW-Bench ships RET/TRK/CMP and no dedicated conjunctive subset, so that claim is
recorded as not evaluated. All of this is stated in the paper rather than left for a reader
to discover.

--------------------------------------------------------------------------------
D-38  PROVIDER LIMIT: Mistral endpoints accept at most 8 images per request
--------------------------------------------------------------------------------
Uniform-16 cells on ministral-3b and ministral-14b failed with HTTP 400 "Total number of
images exceeds the maximum allowed of 8" -- deterministic, verified by probing 8/12/16/24
images (8 OK, the rest capped) and reproduced on both Mistral models. Probed all six
backbones at n=16: only the two Mistral models cap; both Gemma and all three Qwen backbones
serve 16. The constraint now lives in openrouter_client.IMG_CAP, chat() REFUSES an
over-cap request rather than truncating silently (a truncated image list is a different
method reported under the wrong name), and baselines.uniform() clamps and records
w_limited_by in {request, provider, budget}.

This matters beyond plumbing. P3 asks whether reallocating access beats BUYING context; on a
capped backbone the 16k growth arm cannot buy context at all, so the cell measures the cap
and not the question. tab_p3 marks such rows with a dagger and does not bold their delta, and
analyze.py excludes them from the F4 verdict. Asp is unaffected: a round that wants more
frames asks in the NEXT round, which is the distinction Thm 4 is about -- the cap limits
width, not depth.

--------------------------------------------------------------------------------
D-39  LADDER: ministral-14b added because gemma-3-12b has a single provider
--------------------------------------------------------------------------------
google/gemma-3-12b-it is served by exactly ONE OpenRouter provider (DeepInfra), and that
provider shed load long enough to lose all 24 of its main-phase cells in one pass. A scale
ladder whose mid-rung depends on a single upstream endpoint has a hole in it whenever that
endpoint is busy, so the 8->27B gap is now filled twice on two different providers:
gemma-3-12b (12B, DeepInfra) and mistralai/ministral-14b-2512 (14B, Mistral), the latter
measured at 432 tokens/frame. Note its one-frame count probe answered 20 for a 16-object grid,
so Assumption 1 is visibly weaker for it; that is a data point for the convergence test, not
a reason to drop it.

--------------------------------------------------------------------------------
D-40  RETRY: the client now survives provider-side faults it used to die on
--------------------------------------------------------------------------------
Three failure modes were each losing whole cells. (a) HTTP 429 "temporarily rate-limited
upstream": the old ladder gave up after 5 tries and ~15s, which cost 21 cells in one pass;
now 8 tries with a 60s cap and jitter, honouring Retry-After, spanning ~4 minutes of
shedding. (b) HTTP 400 whose body is "Provider returned error" -- an upstream fault wearing a
client-error code; retried, and distinguishable from a real payload bug because a payload bug
is deterministic. (c) HTTP 200 whose body carries {"error": ...} and no "choices", which used
to surface as KeyError: 'choices' and kill the process; now retried, and if it survives every
retry it raises with the body rather than returning "" upward, where an empty answer would
have scored as a wrong one and entered the tables as a measurement.

A fourth mode appeared once the first three were handled: (d) the request failing BELOW http
-- requests raises ConnectionError("Connection reset by peer") / Timeout instead of returning
a response, so the status-code ladder never saw it and the cell died on the first occurrence.
Now retried on the same ladder, and on exhaustion it raises a RuntimeError naming the
transport exception rather than propagating a bare requests error out of a worker.

scripts/selftest_retry.py locks all four modes down offline, with no API key and no network.
It asserts both directions, which are not the same property: a transient fault must be
retried until it clears, AND a fault that never clears must raise rather than return "".
It also asserts that a genuine payload bug (a 400 whose body is NOT "Provider returned
error") still fails on the first attempt instead of burning eight, and that an over-cap image
list is refused rather than truncated (D-38). The cap check runs before the frames are read
and encoded, since it is a caller bug and there is no reason to base64 a megabyte to find it.

--------------------------------------------------------------------------------
D-41  INDEX BUG: BM25 tokenised on whitespace, so retrieval matched almost nothing
--------------------------------------------------------------------------------
EpisodicIndex._bm25 tokenised both documents and query with str.split(). The v2 captions are
comma-separated class inventories and the backbones emit them with inconsistent spacing:

    'study, closed, belt, ruler, soap, bowl, ...'     -> tokens 'belt,' 'ruler,' 'soap,'
    'study, closed, belt,ruler,soap,bowl,...'         -> ONE 17-class token

Neither form contains the token 'belt', so a query naming a class scored zero against the one
caption that contained it. Measured before the fix: recall@8 = 0.00-0.22, delta_r = 0.91-1.00,
median rank of the target 121 of 300 -- while the target class name WAS present in its own
caption in 29 of 29 checked misses. The text was right; the tokeniser threw it away. Fixed by
tokenising on non-alphanumerics (EpisodicIndex._tok, re.findall(r"[a-z0-9]+", ...)).

After the fix, same corpus, same captions, same embeddings:

    backbone            R@1    R@8   delta_r   med rank        (was R@8 / delta_r)
    ministral-3b       0.59   0.75      0.25          1        (0.03 / 0.97)
    qwen3-vl-8b        1.00   1.00      0.00          1        (0.09 / 0.91)
    gemma-3-12b        0.97   0.97      0.03          1        (0.09 / 0.91)
    ministral-14b      0.27   1.00      0.00          2        (0.22 / 0.78)
    qwen3.8-27b        1.00   1.00      0.00          1        (0.00 / 1.00)
    qwen3-vl-30b-a3b   0.94   0.94      0.06          1        (0.09 / 0.91)
    gemma-4-31b        0.91   0.91      0.09          1        (0.09 / 0.91)

CONSEQUENCE FOR THE GRID. Every cell whose method touches the retrieval ranking was measuring
the tokeniser, not the access structure: asp and all six asp_* ablations, retr_only, and
egagent -- 70 of 145 cells. They are moved to results/cells_pre_bm25fix/ (kept, not deleted:
they are the evidence for this entry) and re-run. The 75 cells of blind, uniform16, socratic
and state_only never rank anything and are unaffected; keeping them is not an optimisation but
a check, since they should come back unchanged.

This is the second time an index defect nearly produced an access-structure conclusion (see
D-27, where the caption did not name the target at all). The difference is that D-27 was found
by measuring delta_r before the answer grid and this one survived that check, because
retrieval_recall.py's own caption-presence test used substring matching and therefore reported
'the class name is in the caption' -- true, and irrelevant to whether BM25 could see it. The
lesson recorded for the next version: a recall probe must exercise the SAME tokeniser the
retriever uses, or it is measuring a different index.

--------------------------------------------------------------------------------
D-42  Assumption 1 is now MEASURED, not assumed (tab:probe)
--------------------------------------------------------------------------------
The near-chance first-pass grid had two incompatible explanations -- access structure binding
(the thesis) versus backbones unable to read the frames at all (Assumption 1 failing) -- and
the grid cannot separate them, because a retrieval hit followed by a misread scores exactly
like a retrieval miss. scripts/probe_assumption.py removes access from the problem: it asks the
RET question with the target frame handed to the model (eps_0, chance 12.5%) and asks one
composition step over two in-context frames (eps_1, chance 50%). Roughly 400 single-image
calls for the whole table, no GPU.

First result, qwen3-vl-8b: 1-eps_0 = 93.8% (32/32 scored, no deferrals), 1-eps_1 = 81.2%.
Assumption 1 HOLDS for that backbone, which is what made D-41 findable: a model that reads a
handed-over frame 94% of the time and still scores 9.4% on RET is not failing at perception,
so the failure had to be in access -- and it was, in the index rather than in the architecture.

--------------------------------------------------------------------------------
D-43  CORPUS DEFECT: all eight CMP before/after golds are "before"
--------------------------------------------------------------------------------
Found by auditing the gold distribution of every answer alphabet AFTER the grid was complete.
`take()` returns SORTED frame indices, so sing[i]["t"] < sing[i+1]["t"] always held, and the
question template always named the earlier singleton first. Every one of the eight
before/after items therefore carries the gold "before", and the single word "before" scores
8/8 on them.

It is not hypothetical. Measured, on the eight items alone:

    backbone            blind on the 8 degenerate items
    qwen3-vl-30b-a3b    100.0
    gemma-3-12b         100.0
    ministral-3b        100.0
    qwen3-vl-8b          87.5

and blind's CMP mean falls from 34-41% to 4.7-10.9% once they are removed. A third of the
CMP subtest was answerable with no access to the stream at all.

CONSEQUENCES, all of which are reported in the paper rather than repaired by re-running:
  * The CMP chance level is 25.0% as shipped (16 colour items at K=8 plus 8 binary items),
    not the 12.5% of RET and TRK, and the paper never stated it. It does now.
  * Every CMP figure is reported twice: as measured over 24 items, and restricted to the 16
    items whose gold is not degenerate (chance 12.5%). The restriction is a re-analysis of the
    released per-question records, not a second run.
  * F3's verdict was initially qualified as resting on a contaminated subtest. SUPERSEDED by
    D-44: F3 is an argmax over one ablation's three drops, not a comparison of levels, and it
    recomputes unchanged on the 16 clean items. See D-44 for the recomputation.

FIXED FOR THE FUTURE, IN THREE PLACES (revised -- see D-45 for why a shuffle was not enough):
  1. The question template no longer names the earlier singleton first. The naming order is
     chosen to realise a CONSTRUCTED 4-4 gold balance, drawn from an item-local stream.
  2. The answerability gate gained a gold-DISTRIBUTION check, which the old gate could not
     see: it flags any answer alphabet where the most common gold beats a Bonferroni-corrected
     binomial tail at that K. The statistic is deliberately the max over k categories, not a
     per-category tail -- at K=8 and n=16, six of one colour is ordinary noise (corrected tail
     0.21) and flagging it would make the gate cry wolf, while 8/8 at K=2 is 0.008.

The released generator now REFUSES to ship the corpus this paper measured. That refusal is
correct and is left in place: the measured corpus stays in data/sew unchanged so the released
results remain reproducible against the artefact that produced them, and anyone regenerating
gets the fixed version and a different CMP column.


--------------------------------------------------------------------------------
D-44  F3 RECOMPUTED ON THE NON-DEGENERATE CMP ITEMS -- VERDICT INVARIANT
      (re-analysis of released records; zero API cost, no cell re-run)

D-43 left F3's verdict qualified as "computed on a contaminated subtest", and three
independent peer reviews all read that as the paper's most serious methodological hole. It
was too pessimistic about our own data, and the check that shows so costs nothing.

F3 is not a comparison of LEVELS. It asks, for each ablation, WHICH SUBTEST FALLS FURTHEST
-- an argmax over three drops. A restriction of one subtest's item set therefore moves the
verdict only if it moves that argmax. Recomputed over the 16 non-degenerate CMP items
(analysis/analyze.py: mean_clean(), f3_matrix(), F3_clean, F3_verdict_invariant):

  ablation    expected   as measured (all 24)          clean (16)
  -C_v        RET        RET  {84.4,   0.0, -16.7} ok   RET  {84.4,   0.0,  +6.2} ok
  -C_s        TRK        RET  { 3.1,  -8.3, -62.5} X    RET  { 3.1,  -8.3, -75.0} X
  R=1         CMP        RET  {43.8,   0.0, -20.8} X    RET  {43.8,   0.0, -12.5} X

Same largest-drop column in every row, same per-row verdict, same overall verdict: F3 FIRES
either way. Two of the three crossings are not even about CMP: -C_s crosses because it RAISES
TRK by 8.3, and R=1 crosses because RET collapses by 43.8. Note the direction of this check
was fixed before running it -- had the argmax moved, the paper would be reporting a verdict it
no longer had grounds for.

Second finding, same re-analysis: the flagship -C_s CMP improvement is LARGER on clean items.
  ASP 8.3 -> -C_s 70.8   (all 24, chance 25.0%)
  ASP 6.2 -> -C_s 81.2   (clean 16, chance 12.5%)
So the paper's central negative result -- the compressive channel is harmful on this corpus --
is understated by the degenerate slice, not manufactured by it. Both readings are now quoted
everywhere the number appears, including the abstract.

WHAT THE RE-RUN IS STILL FOR: the CMP LEVELS in Table 3, not F3. Scope corrected: 69 CMP cells
(main grid + ablations + B=16k arm + budget sweep), not the "49 + 6" the paper previously
stated. Offline caches are keyed by (backbone, episode, tau_g) and hold no question, so they
are reused verbatim and the marginal cost is the scored decisions alone.


--------------------------------------------------------------------------------
D-45  THE D-43 FIX, CORRECTED TWICE: A SHUFFLE IS NOT A BALANCE, AND THE RNG STREAM
      IS SHARED

Two defects in D-43's own fix, both found by testing it instead of trusting it.

(a) A SHUFFLE IS NOT ENOUGH. Eight independent coin flips landed on 6 "before" / 2 "after" at
    the shipped seed. That passes the new gate (corrected tail 0.58) and a constant answer
    still scores 75% on a subtest whose chance level is meant to be 50%. At n=8 no unbiased
    draw reliably balances. The balance is now CONSTRUCTED: a fixed permutation of four
    "before" and four "after" is derived once from the corpus seed and consumed by slot, and
    the naming order is chosen to realise the assigned gold. Which item gets which is random;
    the tally is exactly 4-4 by construction.

(b) THE RNG STREAM IS SHARED, AND THIS IS THE EXPENSIVE ONE. build_episode() walks a single
    random.Random across every frame of every episode, so ANY extra draw shifts all
    downstream sampling -- every frame, every singleton, every tracked class, in that episode
    AND all later ones. D-43's rng.shuffle(pair) did exactly that. Consequence had it shipped:
    the corpus changes wholesale, the 28 offline keyframe caches are void, and a 69-cell CMP
    re-run becomes a 207-cell regrid plus ~8,400 offline update calls. The draw now comes from
    random.Random(f"cmp-order|{seed}|...") -- item-local, seeded on the corpus seed.

VERIFIED, not asserted: annotation/selftest_regen.py regenerates at the shipped seed and
checks all of it. No key, no network.
    all 1,200 frames byte-identical    meta.json byte-identical
    exactly 4 of 80 questions change   all 4 in CMP
    before/after tally exactly 4-4     shipped corpus confirmed degenerate (8/8 "before")
The paper states these numbers (App. C.1, "a regeneration contract"), so they are a test.


--------------------------------------------------------------------------------
D-46  PROSE SAID SIX BACKBONES; THE LADDER HAS SEVEN

Found while auditing against peer review, and missed by all three reviewers. Ministral 14B was
added post hoc (D-40) and reached every table via the generated blocks, but the hand-written
prose was never updated: Sec. 4.1's backbone list omitted it entirely, and "six open
backbones" / "six-backbone ladder" / "6 backbones x 4 episodes" / "6x7x80 scored decisions" /
"Eighty questions over four episodes and six backbones" all disagreed with \VnBackbones{}=7 a
few lines away. A reader checking the grid size against the table would have found the paper
contradicting itself.

Fixed: every count now reads \VnBackbones{}, which is generated from the cells on disk, so the
number cannot drift again. Sec. 4.1 introduces Ministral 14B and LABELS IT AS POST HOC, with
the reason (Gemma-3-12B was the only rung between 8B and 27B and has a single provider on this
arm, so an outage there would have removed the middle of Prediction 3's x-axis) and the two
facts that make it a robustness measure rather than a selection: it was added before any 14B
cell was scored, and it is reported in every table rather than only where it helps.

Also fixed: MODEL_TEX in analysis/analyze.py had no entry for ministral-14b, so any generated
verdict sentence naming that backbone would have emitted the raw slug "ministral-14b" into the
typeset paper.


--------------------------------------------------------------------------------
D-47  CMP CELLS RE-RUN AGAINST THE CORRECTED CORPUS (69 cells)

D-43 disclosed the degenerate before/after slice; D-44 showed F3 survives it; D-45 made the
generator fix corpus-local. This is the re-run itself. Three peer reviews all named the
missing re-run as the outstanding defect, and it was affordable, so it was done.

SCOPE.  69 CMP cells: 49 main (7 backbones x 7 methods), 6 flagship ablations, 7 p3
(Uniform-w @ B=16k), 8 budget sweep -- minus one filename collision between the p3 and sweep
arms at B=16k. NOT re-run: the 138 RET/TRK cells, because no RET or TRK item changed
(asserted by annotation/selftest_regen.py, not assumed). The 28 offline keyframe caches are
keyed by (backbone, episode, tau_g) and hold no question, so they were reused verbatim and
only the scored decisions were repaid.

PROCEDURE.  Archived data/sew/questions.json + meta.json to data/sew_pre_cmpfix/ (frames are
byte-identical so they are not duplicated; the README says why). Quarantined the 69 cells to
results/cells_pre_cmpfix/. Regenerated data/sew. Re-ran via run_grid.py --only-subset CMP,
which filters the SAME job list the full grid builds -- not a separate code path with its own
defaults. Ablations first, since F3 and the abstract depend on those cells.

WHAT THE DEFECT WAS WORTH.
  * BLIND, the instrument that detected it, is the check that the repair took. Before: four of
    seven backbones sat clearly ABOVE the 25.0% chance line (36.5, 34.4, 37.5, 40.6). After:
    none does. The two that ROSE (8.3->16.7, 0.0->16.7) were below chance before -- refusals,
    not competence -- and moved toward it, not past it.
  * CHANCE IS UNCHANGED at 25.0%. CMP mixes 16 K=8 items with 8 K=2 items, so balancing the
    binary golds removes an exploitable PRIOR (a constant scores 50% on that slice now, not
    100%); it does not move the floor. Stated in the paper so nobody reads the fix as having
    lowered the bar.
  * F3 VERDICT UNCHANGED -- still fires, same two crossings, largest-drop column RET in all
    three rows. This is now confirmed twice by independent means: by restricting the released
    records to 16 items (D-44), and by this 24-item re-measurement. The second is the stronger
    form, being an independent measurement rather than a subset of the contaminated one.
  * THE CENTRAL NEGATIVE RESULT SURVIVES AT A HIGHER LEVEL. Flagship -C_s CMP: 8.3 -> 70.8
    before, 20.8 -> 83.3 after. The same 62.5-point gap with both endpoints raised, so the
    "our compressive channel is harmful here" finding is a property of the channel and not of
    the defect.
  * IT MOVED AGAINST US WHERE IT COULD. Retr-only on the flagship CMP went 37.5 -> 71.9, and
    ASP vs Retr-only is now significant on 0 of 7 backbones UNCORRECTED (was 1 of 7), with 3
    of 7 deltas negative (was 2), the flagship's worst at -16.2. So the paper's own thesis
    comparison reads worse after the correction than before it. Recorded explicitly, because a
    correction that flatters the corrector is one a reader should discount.
  * Holm over the 42-test family: 35 significant uncorrected, 31 survive (was 34 / 32).

CODE CHANGE THIS FORCED.  analysis/analyze.py's is_degenerate() was hardcoded to the answer
VALUES {"before","after"} -- correct only by accident, because in the pre-fix corpus every such
item carried "before". On a balanced corpus that predicate flags all eight items of a 4-4 slice
and would silently delete a third of the subtest from every "clean" statistic. Degeneracy is
now MEASURED from whichever corpus is on disk, using the same corrected-binomial-tail statistic
as the generator's gate: 8 flagged on the archived corpus, 0 on the corrected one. All the
*_clean statistics therefore collapse to their plain counterparts now, which is intended.

PAPER.  Sec 5.6 rewritten from "here is a defect we are disclosing" to "here is a defect, its
repair, and what it was worth". tab:cmpclean (all/clean from one run) replaced by tab:cmpfix
(pre/post, two runs). Future-work item (i) removed as done and the list renumbered (i)-(ix),
with a sentence saying the removed item was completed rather than silently dropping it.
Abstract, the F3 criterion bullet, and the Retr-only paragraph all updated.


--------------------------------------------------------------------------------
D-48  EGAGENT REIMPLEMENTATION CRASHED ON AN EMPTY PLANNER RESPONSE

Found by the D-47 re-run: 2 of the 49 main cells died, both egagent
(qwen3-vl-30b-a3b, gemma-4-31b), both with

    File "scripts/methods/baselines.py", line 156, in egagent_reimpl
      last = plan.strip().splitlines()[-1]
    IndexError: list index out of range

Those two backbones return an EMPTY planner response on some CMP items, and splitlines() on
"" is [], so [-1] raises. Not a transient fault -- the retry ladder is irrelevant, this is a
real bug in our reimplementation. It did not fire on the pre-fix corpus: the changed question
wording is what elicited the empty response.

FIX.  An empty plan is treated as a REFUSAL, taking the same path an unparseable plan already
took: the model is scored on what it emitted (nothing), which exact-match counts as wrong.
Two alternatives were considered and rejected, and the reasons are in the code comment because
both are tempting:
  * issue a VSEARCH the planner never asked for -> FLATTERS the baseline
  * drop the item -> silently shrinks n for one method only
When `plan` is non-empty the function is byte-for-byte its previous behaviour, so every cell
that completed under the old code -- including all 138 un-rerun RET/TRK cells -- is unaffected.
Recorded in docs/EGAGENT_REIMPL.md as a fourth respect in which our reimplementation differs
from the published system.

PROCESS NOTE.  The retry script for these two cells deadlocked on `pgrep -f cmp_rerun.sh`,
which matched the literal text of its OWN parent wrapper's command line and so waited on
itself forever. Same class of error as the earlier pkill self-match. Any pgrep/pkill whose
pattern appears in the invoking command line will match the invoker.
