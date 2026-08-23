# Datasheets

Two corpora. Only the second was built.

---

## SEW-Bench (Synthetic Embodied Walkthrough) — BUILT AND MEASURED

**Motivation.** Witness tasks for the four walls, at parameters where the corresponding
bounds are non-vacuous, with no licence dependency. It exists because EW-Bench (below)
could not be built, and because the paper's Theorem 1 is *arithmetically vacuous* unless
the queryable attribute count `Nd` is large: at an earlier `d = 9` and `N = 150`,
`kappa_s = 1.85 > 1` and the theorem said nothing at all.

**Composition.** 4 episodes x N=300 frames; 80 questions (32 RET / 24 TRK / 24 CMP).
Per frame: 16 objects in a 4x4 grid, each with a colour and a printed capital letter, both
drawn uniformly from a K=8 alphabet and readable only from pixels — so `d = 32` queryable
attribute values per frame and `Nd = 9,600` per episode, giving `kappa_s = 0.547`. Room,
door state and frame index are NOT counted in `d` (they are not K-ary), which makes the
resulting ceiling conservative. Six rooms, visited in runs of 12–26 frames so the stream
contains revisit loops.

**Collection.** Fully programmatic, fixed seed (`annotation/generate_synthetic.py`), so the
corpus regenerates bit-identically. Filler object classes and all their attributes are
re-randomised every frame — with a fixed per-room layout the stream would carry only
`|rooms| x 16 x 2` distinct attribute values in total and the `Nd` in the bound would be a
fiction. Four class pools (filler / RET singletons / TRK counted / CMP chain) are disjoint,
checked at generation time.

**Item types.** RET: a class appearing in exactly one frame of the episode; the question
asks its colour or its letter. TRK: cumulative sighting counts for four classes, the final
door state after 5–9 toggles, and the toggle count. CMP: a class appearing exactly three
times in three distinct rooms with three distinct colours, asked for its colour *the second
time it was seen* (d_q=2, composing an ordering with an episodic lookup); plus before/after
ordering between two singletons.

**Answerability gate.** Generation aborts if any two items share a question string with
different golds, if the class pools intersect, or if an episode is too short to place its
scheduled events. A confident gold on an unanswerable question surfaces as a model failure,
which is worse than having no item.

**Licences.** None required. Frames are generated from primitives with DejaVu fonts;
questions and frames released CC-BY-4.0.

**Leakage.** The corpus is generated at run time from a seed and appears in no pretraining
corpus. The judge is disjoint from every backbone.

**What it is not.** A 2-D schematic render. It tests access structure under a token budget.
It tests nothing about natural-scene perception, egocentric motion, occlusion, or lighting,
and no result on it should be read as an OpenEQA-style result. See the paper's Limitation (1).

---

## EW-Bench — REGISTERED, **NOT BUILT**

**Status.** `annotation/generate_ewbench.py` raises `NotImplementedError` at the rendering
call. Building it needs habitat-sim and an HM3D/ScanNet licence. Retained here and in the
paper's Appendix B.2 because it is part of the pre-registration and is the corpus this work
should next be run on.

**Registered composition.** 60 walkthroughs (HM3D 40 / ScanNet 20), 8–15 min, N in
[380,520] keyframes; 900 questions (300 RET / 300 TRK / 300 CMP), K=8 attribute alphabet,
d_q in {3,4,5}. Registered `d ~ 96`, hence `Nd ~ 43,200` and `kappa_s ~ 0.38` — a tighter
ceiling than SEW-Bench's 0.547, which is the main thing the real corpus would buy.

**Registered collection.** Programmatic from ground-truth annotations; CMP surface forms
LLM-paraphrased, 2-annotator verification with adjudication. Licences: HM3D and ScanNet
terms apply to frames; questions CC-BY-4.0. Leakage: judge disjoint; scene IDs checked
against published training-corpus manifests of all backbones.
