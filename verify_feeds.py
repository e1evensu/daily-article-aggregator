"""Verify Phase 1 source candidates with the real collector adapters.

This is a production gate, not a general feed discovery script. It reads the
canonical seed catalog, fetches each source through the same collector code the
pipeline uses, and exits non-zero unless enough sources return parseable items.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable

from src.collector.catalog import as_source_model, catalog_by_id, load_source_catalog
from src.collector.dispatcher import SourceFetchResult, fetch_source

FetchSource = Callable[..., Awaitable[SourceFetchResult]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify canonical source feeds/API endpoints")
    parser.add_argument("--source-file", default="config/sources.json", help="source seed JSON path")
    parser.add_argument("--min-ok", type=int, default=3, help="minimum sources that must fetch at least one item")
    parser.add_argument("--include-internal", action="store_true", help="also test internal tunnel-backed sources")
    parser.add_argument("--timeout-s", type=float, default=20.0, help="maximum seconds to wait per source")
    parser.add_argument("--check-source", help=argparse.SUPPRESS)
    return parser.parse_args()


async def verify(
    source_file: str,
    *,
    min_ok: int,
    include_internal: bool,
    timeout_s: float = 20.0,
    fetcher: FetchSource | None = None,
) -> int:
    """Verify catalog sources with the real collectors and enforce the minimum-ok gate."""
    entries = load_source_catalog(source_file)
    if not entries:
        print(f"FAIL no source entries loaded from {source_file}", flush=True)
        return 2

    ok_count = 0
    checked = 0
    for entry in entries:
        if entry.type == "internal_api" and not include_internal:
            print(
                f"SKIP {entry.id:30} internal_api (use --include-internal to test tunnel-backed sources)",
                flush=True,
            )
            continue

        source = as_source_model(entry)
        source.status = "approved"  # verify the parser without changing DB approval state
        started = time.monotonic()
        checked += 1
        if fetcher is None:
            outcome = await _run_source_subprocess(source_file, entry.id, timeout_s=timeout_s)
            result = outcome["result"]
            duration = outcome["duration_s"]
            sample = outcome["sample"]
        else:
            try:
                result = await asyncio.wait_for(fetcher(source), timeout=timeout_s)
            except TimeoutError:
                duration = time.monotonic() - started
                print(f"FAIL {entry.id:30} source_timeout {duration:5.1f}s", flush=True)
                continue

            duration = time.monotonic() - started
            sample = result.items[0].title[:72].replace("\n", " ") if result.items else ""


        if result.status == "succeeded" and result.items:
            ok_count += 1
            print(f"OK   {entry.id:30} items={len(result.items):3} {duration:5.1f}s | {sample}", flush=True)
        elif result.status == "succeeded":
            print(f"WARN {entry.id:30} items=  0 {duration:5.1f}s | fetched but no parseable entries", flush=True)
        else:
            print(f"FAIL {entry.id:30} {result.error or 'unknown_error'} {duration:5.1f}s", flush=True)

    if ok_count < min_ok:
        print(f"FAIL gate: {ok_count}/{checked} checked sources returned items; need >= {min_ok}", flush=True)
        return 1

    print(f"OK gate: {ok_count}/{checked} checked sources returned parseable items", flush=True)
    return 0


async def _run_source_subprocess(source_file: str, source_id: str, *, timeout_s: float) -> dict[str, object]:
    """Run one source verification in a subprocess so slow feeds can be hard-timed out."""
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).resolve()),
        "--source-file",
        source_file,
        "--check-source",
        source_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return {
            "duration_s": time.monotonic() - started,
            "sample": "",
            "result": SourceFetchResult(source_id=source_id, status="failed", error="source_timeout"),
        }

    duration = time.monotonic() - started
    if proc.returncode != 0:
        error = stderr.decode("utf-8", errors="replace").strip() or "source_check_failed"
        return {
            "duration_s": duration,
            "sample": "",
            "result": SourceFetchResult(source_id=source_id, status="failed", error=error.splitlines()[-1][:120]),
        }

    try:
        payload = json.loads(stdout.decode("utf-8").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {
            "duration_s": duration,
            "sample": "",
            "result": SourceFetchResult(source_id=source_id, status="failed", error="source_check_bad_output"),
        }

    return {
        "duration_s": float(payload.get("duration_s") or duration),
        "sample": str(payload.get("sample") or ""),
        "result": SourceFetchResult(
            source_id=source_id,
            status=str(payload.get("status") or "failed"),
            items=[object()] * int(payload.get("items") or 0),
            error=payload.get("error"),
        ),
    }


async def _check_one_source(source_file: str, source_id: str) -> int:
    """Fetch and report one source in the compact JSON shape used by the subprocess path."""
    entry = catalog_by_id(source_file).get(source_id)
    if entry is None:
        print(json.dumps({"source_id": source_id, "status": "failed", "error": "unknown_source"}), flush=True)
        return 1

    source = as_source_model(entry)
    source.status = "approved"
    result = await fetch_source(source)
    sample = result.items[0].title[:72].replace("\n", " ") if result.items else ""
    print(json.dumps({
        "source_id": source_id,
        "status": result.status,
        "items": len(result.items),
        "error": result.error,
        "duration_s": result.duration_s,
        "sample": sample,
    }), flush=True)
    return 0


def main() -> None:
    """Run the feed verification CLI."""
    args = parse_args()
    if args.check_source:
        raise SystemExit(asyncio.run(_check_one_source(args.source_file, args.check_source)))
    raise SystemExit(asyncio.run(
        verify(
            args.source_file,
            min_ok=args.min_ok,
            include_internal=args.include_internal,
            timeout_s=args.timeout_s,
        )
    ))


if __name__ == "__main__":
    main()
