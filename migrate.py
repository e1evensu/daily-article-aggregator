"""Apply the SQL schema migration configured for this service."""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.db import engine

MIGRATIONS_DIR = Path("migrations")
MIGRATION_NAME_RE = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply SQL migration file")
    parser.add_argument("path", nargs="?", default=None, help="SQL migration path")
    return parser.parse_args()


async def apply_sql(path: Path) -> None:
    """Execute every statement from one migration file inside a single transaction."""
    statements = split_sql(path.read_text(encoding="utf-8"))
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))


async def ensure_schema_migrations_table(db_engine: AsyncEngine = engine) -> None:
    """Create the migration tracking table when the target DB has not been bootstrapped yet."""
    ddl = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA_MIGRATIONS_TABLE} (
    version VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
    async with db_engine.begin() as conn:
        await conn.execute(text(ddl))


async def applied_versions(db_engine: AsyncEngine = engine) -> set[str]:
    """Read the set of migration filenames recorded in the target database."""
    await ensure_schema_migrations_table(db_engine)
    async with db_engine.begin() as conn:
        result = await conn.execute(text(f"SELECT version FROM {SCHEMA_MIGRATIONS_TABLE}"))
        return {row[0] for row in result}


async def pending_migration_files(db_engine: AsyncEngine = engine, root: Path = MIGRATIONS_DIR) -> list[Path]:
    """Compare repository migrations with DB state and return the unapplied files in order."""
    files = list_migration_files(root)
    applied = await applied_versions(db_engine)
    return [path for path in files if path.name not in applied]


async def apply_pending(db_engine: AsyncEngine = engine, root: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every pending migration in order and record the applied version."""
    pending = await pending_migration_files(db_engine, root)
    applied_now: list[str] = []
    for path in pending:
        statements = split_sql(path.read_text(encoding="utf-8"))
        async with db_engine.begin() as conn:
            for statement in statements:
                await conn.execute(text(statement))
            await conn.execute(
                text(
                    f"INSERT INTO {SCHEMA_MIGRATIONS_TABLE} (version) VALUES (:version) "
                    "ON DUPLICATE KEY UPDATE version = version"
                ),
                {"version": path.name},
            )
        applied_now.append(path.name)
    return applied_now


def split_sql(sql: str) -> list[str]:
    """Split a migration file into executable SQL statements, skipping comments."""
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(line)
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def list_migration_files(root: Path = MIGRATIONS_DIR) -> list[Path]:
    """Enforce the repository's numbered SQL convention before any migration run."""
    if not root.exists():
        raise ValueError(f"migration directory not found: {root}")
    files = sorted(path for path in root.iterdir() if path.is_file() and path.suffix == ".sql")
    invalid = [path.name for path in files if not MIGRATION_NAME_RE.match(path.name)]
    if invalid:
        raise ValueError(f"invalid migration filename(s): {', '.join(invalid)}")
    if not files:
        raise ValueError(f"no migration files found in: {root}")
    return files


def latest_migration_path(root: Path = MIGRATIONS_DIR) -> Path:
    """Use the highest-numbered migration as the default apply target."""
    return list_migration_files(root)[-1]


def main() -> None:
    """Run the configured SQL migration file."""
    args = parse_args()
    if args.path:
        path = Path(args.path)
        if not path.exists():
            raise SystemExit(f"migration not found: {path}")
        asyncio.run(apply_sql(path))
        print(f"applied {path}")
        return

    applied = asyncio.run(apply_pending())
    if applied:
        print(f"applied {', '.join(applied)}")
    else:
        print("no pending migrations")


if __name__ == "__main__":
    main()
