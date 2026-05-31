#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "src" / "front"
ASSIGN_RE = re.compile(r"window\.([A-Za-z0-9_]+)\s*=")


def iter_front_files() -> list[Path]:
    return sorted(path for path in FRONT.iterdir() if path.suffix in {".js", ".jsx"})


def main() -> int:
    found: set[str] = set()
    for path in iter_front_files():
        found.update(ASSIGN_RE.findall(path.read_text(encoding="utf-8")))

    if found:
        print("frontend policy violations:")
        for name in sorted(found):
            print(f"  - unexpected window export: {name}")
        return 1

    print("frontend policy OK")
    print("window exports: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
