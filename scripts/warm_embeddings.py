#!/usr/bin/env python3
"""Pre-compute the frame embeddings once, so the grid's 24 processes hit the disk cache.

Without this every offline job embeds all 300 frames of its episode itself. Twenty-four
processes doing that simultaneously, each with torch defaulting to one thread per core,
drove the load average to ~1,400 on a 256-core host and turned a seconds-long CLIP pass
into minutes. This is pure local computation with no API cost, and the result is shared.

  python scripts/warm_embeddings.py data/sew
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from methods.asp import embed_images, _persist            # noqa: E402


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "data/sew")
    dirs = sorted(d for d in (root / "frames").iterdir() if d.is_dir())
    if not dirs:
        print(f"no frame directories under {root}/frames")
        return 1
    for d in dirs:
        frames = sorted(str(p) for p in d.glob("*.jpg"))
        embed_images(frames)
        print(f"  {d.name}: {len(frames)} frames embedded")
    _persist(force=True)
    print("[warm] embedding cache ready (results/cache/emb)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
