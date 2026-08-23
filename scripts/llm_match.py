#!/usr/bin/env python3
"""OpenEQA-style LLM-Match judge (score 1-5 -> [0,100]).
Judge model MUST be disjoint from all evaluated backbones (leakage control,
paper App. B). Default: a frontier judge slug set via JUDGE_MODEL env var."""
import os, re
from openrouter_client import BudgetedSession, MODELS

JUDGE = os.environ.get("JUDGE_MODEL", "openai/gpt-5-mini")
MODELS["_judge"] = JUDGE

PROMPT = """You are grading an answer to an embodied question.
Question: {q}
Ground-truth answer: {g}
Model answer: {p}
Give an integer score 1-5 (5 = fully correct, 1 = wrong). Output the integer only."""

def llm_match(pred: str, gold: str, question: str = "") -> float:
    sess = BudgetedSession("_judge", budget=2048)
    out = sess.chat(PROMPT.format(q=question, g=gold, p=pred), max_completion=24, tag="judge")
    m = re.search(r"[1-5]", out)
    s = int(m.group(0)) if m else 1
    return (s - 1) / 4 * 100.0
