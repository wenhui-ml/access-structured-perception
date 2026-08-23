#!/usr/bin/env python3
"""Deterministic scorer for SEW-Bench, with an LLM-Match fallback.

WHY NOT JUST USE THE JUDGE. SEW-Bench golds are single closed-alphabet tokens (a colour,
a digit, a count, open/closed, before/after). Table 2 registers these three columns as
ACCURACY, not LLM-Match, so the metric has to be exact match; and a 1-5 judge scale would
inject 25-point quantisation noise into a comparison whose whole point is a few points of
separation between access structures.

WHY NOT ONLY THE RULE. A verbose but correct answer ("I believe it was the white one")
must not be scored 0 for being verbose, and a rule cannot safely resolve every phrasing --
"across 300 frames I saw 4 mugs" has two numbers in it. So the rule decides when it is
UNAMBIGUOUS and defers to the judge otherwise. The deferral rate is reported, because a
high one would mean the accuracy figure is partly a judge figure.
"""
from __future__ import annotations
import re

COLOURS = ["red", "blue", "green", "yellow", "purple", "orange", "brown", "white"]
LETTERS = list("ABCDEFGH")
PAIRS = [{"open", "closed"}, {"before", "after"}]

DEFERRED = {"n": 0}          # module-level counter, printed by the caller


def _toks(s: str) -> set[str]:
    return set(re.findall(r"[a-z]+", (s or "").lower()))


def rule_match(pred: str, gold: str) -> float | None:
    """100 / 0 when the rule is unambiguous, None when it should defer to the judge."""
    g = (gold or "").strip().lower()
    tk = _toks(pred)

    if g in COLOURS:
        found = [c for c in COLOURS if c in tk]
        if len(found) == 1:
            return 100.0 * (found[0] == g)
        return None                                  # none, or several: defer

    for pair in PAIRS:
        if g in pair:
            found = [w for w in pair if w in tk]
            if len(found) == 1:
                return 100.0 * (found[0] == g)
            return None

    if g.upper() in LETTERS and len(g) == 1:
        # Case-SENSITIVE with word boundaries. Lowercasing first would make the English
        # article "a" indistinguishable from the tag "A", so "it was a B" would look
        # ambiguous and defer every single item to the judge.
        found = sorted(set(re.findall(r"\b([A-H])\b", pred or "")))
        if len(found) == 1:
            return 100.0 * (found[0] == g.upper())
        return None

    if re.fullmatch(r"\d+", g):
        nums = {int(x) for x in re.findall(r"\d+", pred or "")}
        if len(nums) == 1:
            return 100.0 * (nums.pop() == int(g))
        return None

    return None


def sew_score(pred: str, gold: str, question: str = "") -> float:
    if not (pred or "").strip():
        return 0.0                                   # an empty answer is simply wrong
    r = rule_match(pred, gold)
    if r is not None:
        return r
    DEFERRED["n"] += 1
    from llm_match import llm_match
    return llm_match(pred, gold, question)
