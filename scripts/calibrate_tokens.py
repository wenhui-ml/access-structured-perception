#!/usr/bin/env python3
"""Measure the per-image token cost of each backbone, by differencing.

Sec 5.1 says the per-model constant is "measured, logged, and used by the budget
accountant". This measures it: the same prompt is sent with n and with 0 images and
the difference divided by n is the per-image cost. Guessing it is not safe -- the
observed values (283-449 tokens for ONE frame) are all ABOVE the 240 the paper pins,
which changes how many frames Uniform-w can afford at B=4096.

  python scripts/calibrate_tokens.py qwen/qwen3-vl-8b-instruct google/gemma-3-12b-it
"""
from __future__ import annotations
import base64
import os
import sys

import requests

URL = "https://openrouter.ai/api/v1/chat/completions"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Per-image cost depends on RESOLUTION, so calibrate on the frames actually used.
# SEW-Bench renders at 640x480; the earlier 512x384 smoke frames give different numbers.
FRAME_DIR = os.environ.get("ASP_CALIB_FRAMES", os.path.join(ROOT, "data/sew/frames/ep1"))
FRAMES = [os.path.join(FRAME_DIR, f"frame_{i:04d}.jpg") for i in range(4)]
TEXT = "Reply with the single word: ok."


def ptok(slug: str, n_img: int, key: str) -> int | None:
    content = [{"type": "text", "text": TEXT}]
    for f in FRAMES[:n_img]:
        b = base64.b64encode(open(f, "rb").read()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b}"}})
    r = requests.post(URL, timeout=180, headers={"Authorization": f"Bearer {key}"},
                      json={"model": slug, "temperature": 0.0, "max_tokens": 4,
                            "messages": [{"role": "user", "content": content}]})
    if r.status_code != 200:
        return None
    d = r.json()
    return (d.get("usage") or {}).get("prompt_tokens")


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY")
    slugs = sys.argv[1:]
    if not key or not slugs:
        print("usage: OPENROUTER_API_KEY=... calibrate_tokens.py <slug> [slug ...]")
        return 2
    print(f"{'slug':46s} {'p(0img)':>8} {'p(1img)':>8} {'p(3img)':>8} {'tok/img':>8}")
    for s in slugs:
        p0, p1, p3 = ptok(s, 0, key), ptok(s, 1, key), ptok(s, 3, key)
        if None in (p0, p1, p3):
            print(f"{s:46s} {'-':>8} {'-':>8} {'-':>8} {'FAILED':>8}")
            continue
        per = round((p3 - p0) / 3)
        lin = "linear" if abs((p1 - p0) - per) <= max(8, 0.1 * per) else "NONLINEAR"
        fits = (4096 - 60 - 128) // per
        print(f"{s:46s} {p0:8d} {p1:8d} {p3:8d} {per:8d}   {lin}, "
              f"Uniform-w fits w<={fits} at B=4096")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
