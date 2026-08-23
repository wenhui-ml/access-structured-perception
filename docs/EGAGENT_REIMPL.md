# EGAgent reimplementation: parity checklist

`scripts/methods/baselines.py::egagent_reimpl` is a reimplementation of EGAgent
(Rege et al., ACL 2026) under this paper's budget accounting. It is not the authors'
code and it is not a port. This file states what matches and what does not, because a
"reimplementation" claim is only worth what its differences disclose — and because on
SEW-Bench this baseline **beats ASP on the TRK subtest by 30–70 points**, so the paper's
comparison rests on it being a fair rendering rather than a straw man.

## What matches the published design

| Component | Published EGAgent | Here |
|---|---|---|
| Entity scene graph | text entity–relation graph over the episode | `build_entity_graph()`: nodes = entities with first/last mention and mention count; edges = co-occurrence with shared timestamps |
| Graph built from | text (captions), not pixels | the **same** captions `C_v` indexes, from the same offline cache |
| Graph is offline | yes, amortised over queries | yes, not charged to the per-decision budget `B` |
| Planner loop | decompose query, decide whether visual verification is needed | one planner call emitting `VSEARCH: <query>` or `ANSWER: <answer>` |
| Visual search tool | retrieve and read frames | `index.retrieve()` + one multi-frame read |
| Backbone | frozen, prompted | same frozen backbone as every other arm in the same cell |

## What does not match, and the direction of the bias

1. **Planner depth is one round, not iterative.** The published planner can re-plan after a
   tool result. Ours emits at most one `VSEARCH` and then answers. This **understates**
   EGAgent on compositional items, which is the subtest where depth matters — so the CMP
   column should be read as a lower bound on what the real system would do.
2. **No relation typing.** Our edges are co-occurrence with shared timestamps, not typed
   spatial relations. This **understates** EGAgent on anything needing relational structure.
3. **Graph caps.** Top-60 entities by mention count, ≤200 edges, and the serialised graph is
   truncated to 6,000 characters before it enters the prompt. Uncapped, the graph would not
   fit `B`. This is a budget constraint the original does not face in the same form.
4. **Entity extraction is a stopword-filtered token pass**, not a learned extractor, and it
   drops hapax terms (mentions < 2) as caption jitter. On SEW-Bench, where entities are
   printed class names, this is close to exact; on natural video it would not be.
5. **An empty planner response is scored as a refusal.** Two backbones
   (Qwen3-VL-30B-A3B, Gemma 4 31B) return an empty plan on some CMP items. The first version
   of `egagent_reimpl` crashed there (`splitlines()[-1]` on `""`), which killed two cells in
   the D-47 re-run; the guard now scores the model on what it emitted, i.e. nothing, which
   exact-match counts as wrong. The two alternatives both bias the comparison and were
   rejected: issuing a `VSEARCH` the planner never asked for **flatters** EGAgent, and
   dropping the item shrinks `n` for one method only. Scoring the refusal as wrong
   **understates** EGAgent on those items, in the same direction as (1) and (2). Affected: 6
   of 24 CMP items on one backbone and 5 on the other, in the pre-fix run; see
   `notes/deviations.md` D-48.
6. **Same budget `B` as every other arm.** The published system is not evaluated under a
   per-decision token cap. Equalising the budget is the whole point of Table 2 and is a
   deliberate departure.

## Why it wins on TRK, which is worth stating plainly

The graph's `n` field is *the number of captions that mention an entity*. On SEW-Bench a
TRK count question ("how many mugs in total?") is answered by reading that integer. So this
baseline computes counts by counting mentions in an offline text index, and it does not ask
the backbone to maintain a running counter at all.

That is a fair win, not an artefact: the captions are the same ones every method gets, the
graph is charged the same way (offline, like `C_s`'s per-keyframe updates), and nothing about
the question was leaked into the construction. It is evidence that on this corpus a *derived
aggregate over an offline text index* is a better cumulative-state mechanism than a
prompted online accumulator — which is a finding about `C_s`'s implementation, and one the
paper reports against itself in §5.6 rather than around.

The limitation of the win is equally concrete: it works because SEW-Bench's tracked classes
appear in captions once per sighting and never as filler, so mention count equals sighting
count by construction. A corpus where an object is mentioned in captions while not being a
countable event, or where the reduction is not a count (containment, parity under partial
observation), would break the equality. The registered EW-Bench design has both.
