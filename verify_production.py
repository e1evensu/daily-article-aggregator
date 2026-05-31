from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select

from src.config import parse_csv, settings
import migrate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify persisted production run artifacts")
    parser.add_argument("--min-items", type=int, default=1, help="minimum items linked to the latest finished run")
    parser.add_argument("--min-analyzed", type=int, default=1, help="minimum analyzed items linked to the latest finished run")
    parser.add_argument("--min-digests", type=int, help="minimum digests linked to the latest finished run")
    parser.add_argument("--domains", default=settings.digest_domains, help="comma-separated digest domains to verify")
    parser.add_argument("--hexo-posts-dir", default=settings.hexo_posts_dir, help="Hexo posts directory to verify")
    parser.add_argument("--skip-hexo-files", action="store_true", help="skip checking generated Hexo markdown files")
    parser.add_argument("--strict-success", action="store_true", help="fail if the latest finished run is partial")
    return parser.parse_args()


async def main() -> int:
    """Collect evidence from the latest finished run and enforce production gates."""
    args = parse_args()
    domains = parse_csv(args.domains)
    min_digests = args.min_digests if args.min_digests is not None else len(domains)
    evidence = await collect_evidence()
    ok, summary = evaluate_evidence(
        evidence,
        domains=domains,
        posts_dir=Path(args.hexo_posts_dir),
        min_items=args.min_items,
        min_analyzed=args.min_analyzed,
        min_digests=min_digests,
        accepted_statuses={"succeeded"} if args.strict_success else {"succeeded", "partial"},
        require_hexo_files=not args.skip_hexo_files,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


async def collect_evidence(deps: SimpleNamespace | None = None) -> dict[str, Any]:
    deps = deps or _deps()
    async with deps.async_session() as session:
        result = await session.execute(
            select(deps.Run).where(deps.Run.finished_at.is_not(None)).order_by(deps.Run.started_at.desc()).limit(1)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return {"run": None, "item_count": 0, "analyzed_count": 0, "digests": []}

        item_count = await session.scalar(
            select(func.count()).select_from(deps.Item).where(deps.Item.run_id == run.id)
        )
        analyzed_count = await session.scalar(
            select(func.count()).select_from(deps.Item).where(deps.Item.run_id == run.id, deps.Item.analysis_stage >= 1)
        )
        digest_result = await session.execute(select(deps.Digest).where(deps.Digest.run_id == run.id))
        schema_result = await session.execute(select(deps.SchemaMigration.version))
        return {
            "run": run,
            "item_count": int(item_count or 0),
            "analyzed_count": int(analyzed_count or 0),
            "digests": list(digest_result.scalars().all()),
            "applied_migrations": list(schema_result.scalars().all()),
        }


def evaluate_evidence(
    evidence: dict[str, Any],
    *,
    domains: list[str],
    posts_dir: Path,
    min_items: int,
    min_analyzed: int,
    min_digests: int,
    accepted_statuses: set[str],
    require_hexo_files: bool,
) -> tuple[bool, dict[str, Any]]:
    """Evaluate the gathered evidence against the requested production thresholds."""
    run = evidence.get("run")
    item_count = int(evidence.get("item_count") or 0)
    analyzed_count = int(evidence.get("analyzed_count") or 0)
    digests = list(evidence.get("digests") or [])
    errors: list[str] = []

    summary: dict[str, Any] = {
        "status": "failed",
        "items": {"total": item_count, "analyzed": analyzed_count},
        "digests": [],
        "hexo_files": [],
        "migrations": _migration_summary(evidence.get("applied_migrations") or []),
    }

    if run is None:
        errors.append("no_finished_run")
        summary["errors"] = errors
        return False, summary

    if not summary["migrations"]["ok"]:
        errors.append("migration_policy_failed")

    summary["run"] = {
        "id": run.id,
        "status": run.status,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }
    if run.status not in accepted_statuses:
        errors.append(f"run_status_{run.status}")
    if item_count < min_items:
        errors.append(f"items_below_min:{item_count}<{min_items}")
    if analyzed_count < min_analyzed:
        errors.append(f"analyzed_below_min:{analyzed_count}<{min_analyzed}")

    stats_digest = (run.stats_json or {}).get("digest", {})
    digest_by_domain = {digest.domain: digest for digest in digests if digest.content_markdown}
    if len(digest_by_domain) < min_digests:
        errors.append(f"digests_below_min:{len(digest_by_domain)}<{min_digests}")

    for domain in domains:
        digest = digest_by_domain.get(domain)
        if digest is None:
            errors.append(f"missing_digest:{domain}")
            continue

        digest_status = stats_digest.get(domain, {})
        if digest_status.get("status") != "succeeded":
            errors.append(f"digest_not_succeeded:{domain}")
        if digest_status.get("digest_id") and digest_status["digest_id"] != digest.id:
            errors.append(f"digest_id_mismatch:{domain}")

        hexo_name = f"intelligence-{domain}-{_date_str(digest.date)}.md"
        hexo_path = posts_dir / hexo_name
        hexo_exists = hexo_path.exists()
        if require_hexo_files and not hexo_exists:
            errors.append(f"missing_hexo_file:{hexo_name}")

        summary["digests"].append(
            {
                "id": digest.id,
                "domain": domain,
                "date": _date_str(digest.date),
                "hexo_path": hexo_name,
                "oss_url": digest.oss_url,
            }
        )
        summary["hexo_files"].append({"path": str(hexo_path), "exists": hexo_exists})

    if errors:
        summary["errors"] = errors
        return False, summary

    summary["status"] = "ok"
    return True, summary


def _deps() -> SimpleNamespace:
    """Import production-verification dependencies lazily."""
    from src.db import async_session
    from src.models.digest import Digest
    from src.models.item import Item
    from src.models.run import Run
    from src.models.schema_migration import SchemaMigration

    return SimpleNamespace(async_session=async_session, Run=Run, Item=Item, Digest=Digest, SchemaMigration=SchemaMigration)


def _migration_summary(applied_versions: list[str]) -> dict[str, Any]:
    """Compare repository migrations with the versions recorded in the target database."""
    try:
        files = migrate.list_migration_files(Path("migrations"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    expected = [path.name for path in files]
    applied = sorted(applied_versions)
    pending = [name for name in expected if name not in applied]
    return {
        "ok": not pending,
        "latest": expected[-1],
        "count": len(expected),
        "applied": applied,
        "pending": pending,
    }


def _iso(value: Any) -> str | None:
    """Serialize datetime-like values to ISO strings for JSON summaries."""
    return value.isoformat() if value else None


def _date_str(value: Any) -> str:
    """Serialize date-like values to strings for filenames and JSON summaries."""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
