"""Persist deep-analysis reports into the `deep_analyses` table.

The Finder stage (`src/deep/finder.py`) is deliberately stdlib-only and writes
each report to `REPORT_DIR/{subject}.md` with a leading `<!-- {meta json} -->`
comment. This module bridges those files into the database using the intel
system's async engine, so reports become queryable alongside items and can be
surfaced in digests / the API.

Idempotent: re-ingesting a subject overwrites its row (the latest run wins).

CLI:
    python3 -m src.deep.store ingest-all          # ingest every report file
    python3 -m src.deep.store ingest GHSA-xxxx     # one subject
    python3 -m src.deep.store ingest-pending       # only files not yet in DB
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from src.db import async_session
from src.models.deep_analysis import DeepAnalysis

REPORT_DIR = os.environ.get("DEEP_REPORT_DIR", "/root/intel-deep/reports")
_META_RE = re.compile(r"^<!--\s*(\{.*?\})\s*-->\s*", re.DOTALL)


def parse_report_file(path: Path) -> dict:
    """Split a report file into its meta dict and markdown body."""
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    m = _META_RE.match(text)
    if m:
        try:
            meta = json.loads(m.group(1))
        except json.JSONDecodeError:
            meta = {}
    return {"meta": meta, "report_md": text}


def _row_from(path: Path, item_id: str | None = None) -> dict:
    parsed = parse_report_file(path)
    meta = parsed["meta"]
    subject = meta.get("ghsa") or meta.get("subject") or path.stem
    return {
        "id": subject,
        "subject": subject,
        "item_id": item_id or meta.get("item_id"),
        "kind": meta.get("kind", "vuln_rca"),
        "repo": meta.get("repo"),
        "vuln_commit": meta.get("vuln_commit"),
        "fix_commit": meta.get("fix_commit"),
        "model": meta.get("model"),
        "status": meta.get("status"),
        "attempts": meta.get("attempts"),
        "report_md": parsed["report_md"],
    }


async def upsert_row(row: dict) -> None:
    """Insert or overwrite a deep_analyses row (MySQL ON DUPLICATE KEY UPDATE)."""
    async with async_session() as session:
        stmt = mysql_insert(DeepAnalysis).values(**row)
        update_cols = {k: stmt.inserted[k] for k in row if k != "id"}
        stmt = stmt.on_duplicate_key_update(**update_cols)
        await session.execute(stmt)
        await session.commit()


async def ingest_file(path: Path, item_id: str | None = None) -> str:
    row = _row_from(path, item_id=item_id)
    await upsert_row(row)
    return row["id"]


async def ingest_meta(meta: dict, report_md: str, item_id: str | None = None) -> str:
    """Ingest straight from an in-memory Finder result (pipeline path — no file
    round-trip needed)."""
    subject = meta.get("ghsa") or meta.get("subject")
    row = {
        "id": subject, "subject": subject, "item_id": item_id or meta.get("item_id"),
        "kind": meta.get("kind", "vuln_rca"), "repo": meta.get("repo"),
        "vuln_commit": meta.get("vuln_commit"), "fix_commit": meta.get("fix_commit"),
        "model": meta.get("model"), "status": meta.get("status"),
        "attempts": meta.get("attempts"), "report_md": report_md,
    }
    await upsert_row(row)
    return subject


async def _existing_ids() -> set[str]:
    async with async_session() as session:
        rows = await session.execute(select(DeepAnalysis.id))
        return {r[0] for r in rows.all()}


async def ingest_all(only_pending: bool = False) -> list[str]:
    """Ingest all report files, optionally skipping subjects already stored in DB."""
    files = sorted(Path(REPORT_DIR).glob("*.md"))
    files = [f for f in files if not f.name.endswith(".fixdiff.patch")]
    skip = await _existing_ids() if only_pending else set()
    done = []
    for f in files:
        if only_pending and f.stem in skip:
            continue
        try:
            done.append(await ingest_file(f))
        except Exception as e:  # noqa: BLE001 — report and continue
            print(f"FAILED {f.name}: {e}", file=sys.stderr)
    return done


def main() -> None:
    """Run the deep-report ingestion CLI."""
    ap = argparse.ArgumentParser(description="Ingest deep-analysis reports into DB")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest-all")
    sub.add_parser("ingest-pending")
    p1 = sub.add_parser("ingest")
    p1.add_argument("subject")
    p1.add_argument("--item-id", default=None)
    a = ap.parse_args()

    if a.cmd == "ingest":
        path = Path(REPORT_DIR) / f"{a.subject}.md"
        if not path.exists():
            sys.exit(f"no report file: {path}")
        out = asyncio.run(ingest_file(path, item_id=a.item_id))
        print(f"ingested {out}")
    else:
        out = asyncio.run(ingest_all(only_pending=a.cmd == "ingest-pending"))
        print(f"ingested {len(out)}: {', '.join(out) or '(none)'}")


if __name__ == "__main__":
    main()
