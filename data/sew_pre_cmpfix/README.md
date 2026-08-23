# The corpus as measured, before the D-43/D-45 CMP fix

`questions.json` here is the item set every cell in `results/cells_pre_cmpfix/` was scored
against. Eight of its twenty-four CMP items carry the gold `before` (see D-43): the generator's
`take()` returns sorted frame indices and the before/after template always named the earlier
singleton first, so a constant answer scored 8/8 and a blind agent reached 87.5-100% on them.

Only `questions.json` is archived, and that is deliberate rather than lazy: the corrected
generator draws the naming order from an item-local stream, so regenerating at the shipped seed
leaves all 1,200 frames and `meta.json` byte-identical and changes exactly four of the eighty
questions. `meta.json` is copied only so this directory is self-describing.
`annotation/selftest_regen.py` asserts that property; if it ever fails, the frames in
`data/sew/frames` are no longer the frames these results were measured on.

Nothing in the paper reports numbers from this corpus any more. It is kept so the superseded
cells stay auditable against the item set that produced them.
