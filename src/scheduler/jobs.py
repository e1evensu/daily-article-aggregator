import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.ai.analyzer import Analyzer
from src.config import settings
from src.db import async_session
from src.pipeline.output import oss_config_from_settings
from src.pipeline.run_lifecycle import compute_run_window, run_with_lifecycle
from src.pipeline.runner import PipelineOptions, load_approved_sources, run_daily_pipeline

logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
log = logging.getLogger(__name__)


async def daily_pipeline():
    """Run one scheduled daily pipeline execution inside the lifecycle wrapper."""
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        sources = await load_approved_sources(session)
        source_ids = [source.id for source in sources]
        window_start, window_end = await compute_run_window(session, now)

        async def runner(run):
            async def update_stats(stats_json):
                run.stats_json = stats_json
                await session.flush()

            options = PipelineOptions(
                run_id=run.id,
                window_start=run.window_start,
                window_end=run.window_end,
                hexo_posts_dir=settings.hexo_posts_dir,
                oss_config=oss_config_from_settings() if settings.oss_bucket else None,
            )
            result = await run_daily_pipeline(
                session,
                Analyzer.nvidia_from_settings(),
                options,
                stats_updater=update_stats,
            )
            return result.status, result.stats_json

        lifecycle = await run_with_lifecycle(
            session,
            run_id=f"run_{now.strftime('%Y%m%d_%H%M%S')}",
            kind="daily",
            window_start=window_start,
            window_end=window_end,
            started_at=now,
            source_ids=source_ids,
            runner=runner,
        )
        await session.commit()
    if lifecycle.status == "skipped":
        log.info("Daily pipeline skipped: %s", lifecycle.skipped_reason)
        return
    log.info("Daily pipeline finished: status=%s stats=%s", lifecycle.status, lifecycle.run.stats_json if lifecycle.run else None)


async def _serve():
    """Start APScheduler on the current event loop and keep the process alive."""
    # AsyncIOScheduler.start() needs a *running* loop (py3.10+), so start it
    # from inside asyncio.run and then idle forever.
    scheduler = AsyncIOScheduler()
    minute, hour, *_ = settings.collect_cron.split()
    scheduler.add_job(daily_pipeline, "cron", hour=int(hour), minute=int(minute), id="daily_pipeline")
    scheduler.start()
    log.info("Scheduler started — daily pipeline at %02d:%02d UTC", int(hour), int(minute))
    try:
        await asyncio.Event().wait()  # run until the process is stopped
    finally:
        scheduler.shutdown(wait=False)


def main():
    """Run the scheduler entrypoint as a standalone process."""
    import asyncio
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
