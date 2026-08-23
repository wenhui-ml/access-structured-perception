#!/usr/bin/env python3
"""Verify model slugs against the LIVE OpenRouter catalogue before spending anything.

Hardcoded slugs go stale: OpenRouter renames and retires models, and a wrong slug
fails mid-run after the earlier cells have already been paid for. This asks the
catalogue instead of guessing, and reports whether each candidate accepts images --
a text-only model silently answering a visual question would look like a result.

  export OPENROUTER_API_KEY=...
  python scripts/check_models.py            # registered grid
  ASP_PILOT=1 python scripts/check_models.py   # + the small pilot models
"""
from __future__ import annotations
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openrouter_client import MODELS, PILOT_MODELS, REGISTERED  # noqa: E402

CATALOGUE = "https://openrouter.ai/api/v1/models"


def fetch() -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = requests.get(CATALOGUE, headers=headers, timeout=60)
    r.raise_for_status()
    out = {}
    for m in r.json().get("data", []):
        mods = (m.get("architecture") or {}).get("input_modalities") or []
        pricing = m.get("pricing") or {}
        out[m["id"]] = {
            "vision": "image" in mods,
            "ctx": m.get("context_length"),
            "in_price": pricing.get("prompt"),
            "out_price": pricing.get("completion"),
        }
    return out


def main() -> int:
    cat = fetch()
    print(f"catalogue: {len(cat)} models\n")
    groups = [("MEASURED LADDER", MODELS), ("REGISTERED (record only)", REGISTERED)]
    if os.environ.get("ASP_PILOT"):
        groups.append(("PILOT", PILOT_MODELS))
    bad = 0
    for label, table in groups:
        print(f"--- {label} ---")
        for key, slug in sorted(table.items()):
            if key.startswith("_"):
                continue
            info = cat.get(slug)
            if info is None:
                print(f"  MISSING  {key:18s} {slug}")
                bad += 1
            elif not info["vision"]:
                print(f"  NO-IMAGE {key:18s} {slug}  <-- would answer blind")
                bad += 1
            else:
                print(f"  ok       {key:18s} {slug}  ctx={info['ctx']} "
                      f"in={info['in_price']} out={info['out_price']}")
        print()
    if bad:
        print(f"{bad} slug(s) unusable. Vision-capable models containing a matching name:")
        want = {k.split('-')[0] for t in (g[1] for g in groups) for k in t}
        for slug, info in sorted(cat.items()):
            if info["vision"] and any(w in slug for w in want):
                print(f"    {slug}")
        return 1
    print("all slugs resolve and accept images.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
