#!/usr/bin/env python3
"""Offline self-test of the budget accounting. No API key, no GPU, no network.

The equal-budget premise of Table 2 is a claim about code, so it gets a test. A fake
transport reports token usage proportional to what was actually sent, which is enough
to catch the failure this suite was written for: a single oversized call slipping past
a budget that was only checked on entry.

  python scripts/selftest_budget.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OPENROUTER_API_KEY", "selftest-not-a-real-key")

import openrouter_client as oc  # noqa: E402

FAILED = []
IMG_COST = 302        # measured for qwen3-vl-8b (scripts/calibrate_tokens.py)


def check(name: str, cond: bool, detail: str = ""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not cond:
        FAILED.append(name)


class FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        msgs = self._p["messages"][0]["content"]
        text = sum(len(c["text"]) for c in msgs if c["type"] == "text")
        n_img = sum(1 for c in msgs if c["type"] == "image_url")
        prompt = text // 4 + n_img * IMG_COST
        completion = self._p["max_tokens"]          # worst case: model fills it
        return {"choices": [{"message": {"content": "ANSWER: ok"}}],
                "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
                "model": "fake/model"}


def fake_post(url, json=None, headers=None, timeout=None):
    return FakeResp(json)


def main() -> int:
    oc.requests.post = fake_post
    oc.MODELS["fake"] = "fake/model"
    tiny = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest.jpg")
    open(tiny, "wb").write(b"\xff\xd8\xff\xd9")     # content irrelevant to the fake

    print("1. an oversized call is refused, not merely logged")
    s = oc.BudgetedSession("fake", budget=4096)
    try:
        s.chat("q" * 200, images=[tiny] * 24, max_completion=128, tag="uniform")
        check("24 frames at B=4096 raises BudgetExhausted", False, f"spent={s.spent}")
    except oc.BudgetExhausted as e:
        check("24 frames at B=4096 raises BudgetExhausted", True, str(e)[:56])
    check("nothing was spent on the refused call", s.spent == 0, f"spent={s.spent}")

    print("1b. w=16 is unaffordable at the MEASURED cost; w=12 is the real ceiling")
    s = oc.BudgetedSession("fake", budget=4096)
    s.img_tokens = IMG_COST
    try:
        s.chat("q" * 200, images=[tiny] * 16, max_completion=128, tag="uniform")
        check("w=16 refused at 302 tok/frame", False, f"spent={s.spent}")
    except oc.BudgetExhausted:
        check("w=16 refused at 302 tok/frame", True, "16*302=4832 > 4096")
    s = oc.BudgetedSession("fake", budget=4096)
    s.img_tokens = IMG_COST
    try:
        s.chat("q" * 200, images=[tiny] * 12, max_completion=128, tag="uniform")
        check("w=12 accepted at 302 tok/frame", s.spent <= 4096, f"spent={s.spent}")
    except oc.BudgetExhausted as e:
        check("w=12 accepted at 302 tok/frame", False, str(e)[:56])

    print("2. a call that fits is allowed and debited")
    s = oc.BudgetedSession("fake", budget=4096)
    s.chat("q" * 200, images=[tiny] * 4, max_completion=128, tag="read_retr_r1")
    check("4 images fit under B=4096", 0 < s.spent <= 4096, f"spent={s.spent}")

    print("3. total spend never exceeds B across many calls")
    s = oc.BudgetedSession("fake", budget=2048)
    n = 0
    try:
        for i in range(50):
            s.chat("q" * 100, images=[tiny], max_completion=64, tag=f"round{i}")
            n += 1
    except oc.BudgetExhausted:
        pass
    check("spend stays within budget", s.spent <= 2048, f"spent={s.spent} after {n} calls")
    check("it did stop early", n < 50, f"{n} calls made")

    print("4. per-channel ledger routes tags correctly")
    s = oc.BudgetedSession("fake", budget=100000)
    s.chat("x", max_completion=8, tag="router_cls")
    s.chat("x", max_completion=8, tag="state_update")
    s.chat("x", images=[tiny], max_completion=8, tag="read_retr_r1")
    s.chat("x", max_completion=8, tag="round1")
    ch = s.by_channel
    check("rho/Bs/Br/Bc all charged", all(ch[k] > 0 for k in ("rho", "Bs", "Br", "Bc")), str(ch))
    check("split sums to ~1", abs(sum(s.split().values()) - 1.0) < 0.01, str(s.split()))

    print("5. estimate is conservative (never under-reserves for images)")
    s = oc.BudgetedSession("fake", budget=100000)
    est = s.estimate("q" * 400, 3, 100)
    s.chat("q" * 400, images=[tiny] * 3, max_completion=100, tag="round1")
    check("estimate >= actual", est >= s.spent, f"est={est} actual={s.spent}")

    os.remove(tiny)
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: {FAILED}")
        return 1
    print("all budget invariants hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
