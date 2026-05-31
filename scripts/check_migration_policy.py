#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import migrate


def main() -> int:
    root = Path("migrations")
    try:
        files = migrate.list_migration_files(root)
    except ValueError as exc:
        print(f"migration policy violation: {exc}")
        return 1

    print("migration policy OK")
    print(f"latest migration: {files[-1].name}")
    print(f"tracked by table: {migrate.SCHEMA_MIGRATIONS_TABLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
