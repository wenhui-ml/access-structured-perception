#!/usr/bin/env python3
"""Offline regression test for the provider-fault retry ladder in openrouter_client.chat().

Four transient failure modes cost real cells on this grid before they were handled, and each
one looked like a different bug:
  429 upstream rate-limit      -> 21 main cells lost in one pass
  400 "Provider returned error"-> an UPSTREAM fault wearing a client-error code
  200 with {"error": ...}      -> surfaced as KeyError: 'choices' and killed the process
  ConnectionReset / Timeout    -> raised BELOW http, so the status-code ladder never saw it

The two properties that matter are asymmetric, so both are asserted here: a transient fault
must be retried until it clears, and a fault that never clears must RAISE rather than return
an empty string upward -- an empty answer scores as a wrong one and enters the tables as a
measurement. A genuine payload bug must still fail on the first attempt, not after eight.

No network, no API key needed. Run: python scripts/selftest_retry.py
"""
from __future__ import annotations
import json
import os
import pathlib
import sys

os.environ.setdefault("OPENROUTER_API_KEY", "dummy-offline-selftest")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import openrouter_client as oc      # noqa: E402

oc.time.sleep = lambda *_: None     # the ladder's waits are what makes this slow, not the work

OK_BODY = {"choices": [{"message": {"content": "ok"}}],
           "usage": {"total_tokens": 5}, "model": "stub"}


class Resp:
    def __init__(self, code, body, headers=None):
        self.status_code, self._body = code, body
        self.headers = headers or {}

    @property
    def text(self):
        return json.dumps(self._body)

    def json(self):
        return self._body


def scripted(seq):
    it = iter(seq)

    def post(*_a, **_k):
        v = next(it)
        if isinstance(v, Exception):
            raise v
        return v
    return post


def main() -> int:
    E = oc.requests.exceptions
    bad = 0

    recovers = {
        "429 upstream, then OK":
            [Resp(429, {"error": {"code": 429}}), Resp(200, OK_BODY)],
        "429 with Retry-After, then OK":
            [Resp(429, {"error": {}}, {"Retry-After": "2"}), Resp(200, OK_BODY)],
        "400 'Provider returned error', then OK":
            [Resp(400, {"error": {"message": "Provider returned error"}}), Resp(200, OK_BODY)],
        "200 carrying an error body, then OK":
            [Resp(200, {"error": {"message": "provider blew up"}}), Resp(200, OK_BODY)],
        "connection reset, then OK":
            [E.ConnectionError("Connection reset by peer"), Resp(200, OK_BODY)],
        "two timeouts, then OK":
            [E.Timeout("read timeout"), E.Timeout("read timeout"), Resp(200, OK_BODY)],
    }
    for name, seq in recovers.items():
        oc.requests.post = scripted(seq)
        try:
            out = oc.BudgetedSession("qwen3.8-27b", budget=10**6).chat("hi", tag="t")
            assert out == "ok", f"recovered but returned {out!r}"
            print(f"  ok        {name}")
        except Exception as e:                                  # noqa: BLE001
            bad += 1
            print(f"  FAIL      {name}: {type(e).__name__}: {str(e)[:70]}")

    raises = {
        "transport never recovers": [E.ConnectionError("reset")] * oc.RETRIES,
        "200 without choices, never recovers":
            [Resp(200, {"error": {"message": "x"}})] * oc.RETRIES,
        "a real payload bug fails immediately":
            [Resp(400, {"error": {"message": "invalid image encoding"}})],
    }
    for name, seq in raises.items():
        oc.requests.post = scripted(seq)
        try:
            oc.BudgetedSession("qwen3.8-27b", budget=10**6).chat("hi", tag="t")
            bad += 1
            print(f"  FAIL      {name}: returned instead of raising")
        except RuntimeError:
            print(f"  ok        {name}")
        except StopIteration:
            bad += 1
            print(f"  FAIL      {name}: retried a fault it should have surfaced at once")

    # the provider image cap must be refused, never silently truncated
    oc.requests.post = scripted([Resp(200, OK_BODY)])
    s = oc.BudgetedSession("ministral-14b", budget=10**6)
    try:
        s.chat("hi", images=["a.jpg"] * (s.img_cap + 1), tag="uniform")
        bad += 1
        print("  FAIL      over-cap image list was accepted")
    except RuntimeError:
        print(f"  ok        over-cap image list refused (cap={s.img_cap})")

    print("\nFAILURES:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
