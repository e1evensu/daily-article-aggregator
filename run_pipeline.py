import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily intelligence pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run a manual smoke without committing DB changes; Hexo output goes to a temporary directory",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="maximum fetched items per domain to analyze during --dry-run; use 0 for no limit",
    )
    return parser.parse_args()


async def dry_run_pipeline(max_items_per_domain: int | None = 5) -> dict:
    """Run the pipeline without committing DB changes and return a JSON summary."""
    deps = _pipeline_deps()
    now = datetime.now(timezone.utc)
    stats_updates = 0
    with TemporaryDirectory(prefix="intelligence-pipeline-smoke-") as posts_dir:
        async with deps.async_session() as session:
            sources = await deps.load_approved_sources(session)
            source_ids = [source.id for source in sources]
            source_domains = {source.id: source.domain for source in sources}
            window_start, window_end = await deps.compute_run_window(session, now)

            async def runner(run):
                nonlocal stats_updates

                async def update_stats(stats_json):
                    nonlocal stats_updates
                    stats_updates += 1
                    run.stats_json = stats_json
                    await session.flush()

                options = deps.PipelineOptions(
                    run_id=run.id,
                    window_start=run.window_start,
                    window_end=run.window_end,
                    hexo_posts_dir=posts_dir,
                    oss_config=None,
                )
                result = await deps.run_daily_pipeline(
                    session,
                    deps.Analyzer.nvidia_from_settings(),
                    options,
                    collector=_limited_collector(max_items_per_domain, source_domains),
                    stats_updater=update_stats,
                )
                return result.status, result.stats_json

            lifecycle = await deps.run_with_lifecycle(
                session,
                run_id=f"dry_run_{now.strftime('%Y%m%d_%H%M%S')}",
                kind="manual_smoke",
                window_start=window_start,
                window_end=window_end,
                started_at=now,
                source_ids=source_ids,
                runner=runner,
            )
            summary = {
                "status": lifecycle.status,
                "skipped_reason": lifecycle.skipped_reason,
                "run_id": lifecycle.run.id if lifecycle.run else None,
                "source_count": len(source_ids),
                "max_items_per_domain": max_items_per_domain,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "stats_updates": stats_updates,
                "stats": lifecycle.run.stats_json if lifecycle.run else {},
            }
            await session.rollback()
            return summary


def _limited_collector(max_items_per_domain: int | None, source_domains: dict[str, str] | None = None):
    """Wrap the real collector so dry runs cap analyzed items per domain."""
    from src.collector.dispatcher import collect_sources

    if max_items_per_domain is None or max_items_per_domain <= 0:
        return collect_sources
    source_domains = source_domains or {}

    async def collect_limited(sources, since=None):
        remaining_by_domain: dict[str, int] = {}
        limited_results = []
        for result in await collect_sources(sources, since=since):
            domain = source_domains.get(result.source_id, result.source_id)
            remaining = remaining_by_domain.setdefault(domain, max_items_per_domain)
            items = result.items[: max(0, remaining)]
            remaining_by_domain[domain] = remaining - len(items)
            limited_results.append(_copy_fetch_result(result, items))
        return limited_results

    return collect_limited


def _copy_fetch_result(result: Any, items: list) -> Any:
    """Clone a fetch result with a trimmed item list."""
    from dataclasses import replace

    return replace(result, items=items)


def _pipeline_deps():
    """Import pipeline dependencies lazily so --help stays lightweight."""
    from types import SimpleNamespace

    from src.ai.analyzer import Analyzer
    from src.db import async_session
    from src.pipeline.run_lifecycle import compute_run_window, run_with_lifecycle
    from src.pipeline.runner import PipelineOptions, load_approved_sources, run_daily_pipeline

    return SimpleNamespace(
        Analyzer=Analyzer,
        PipelineOptions=PipelineOptions,
        async_session=async_session,
        compute_run_window=compute_run_window,
        load_approved_sources=load_approved_sources,
        run_daily_pipeline=run_daily_pipeline,
        run_with_lifecycle=run_with_lifecycle,
    )


async def _daily_pipeline():
    """Run the scheduler's real daily pipeline entrypoint once."""
    from src.scheduler.jobs import daily_pipeline

    await daily_pipeline()


if __name__ == "__main__":
    args = parse_args()
    if args.dry_run:
        collector_limit = None if args.max_items <= 0 else args.max_items
        print(json.dumps(asyncio.run(dry_run_pipeline(collector_limit)), ensure_ascii=False, sort_keys=True))
    else:
        asyncio.run(_daily_pipeline())
        print("PIPELINE DONE")
