from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.sql.expression import true
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.analyzer import Analyzer, should_run_stage2
from src.collector.dispatcher import collect_sources
from src.config import parse_csv, settings
from src.models.digest import Digest
from src.models.item import Item
from src.models.source import Source
from src.pipeline.cleanup import delete_expired_items
from src.pipeline.digest import DigestArtifact, DigestItem, beijing_digest_date, build_digest_artifact
from src.pipeline.ingestion import NormalizationError, normalize_raw_item
from src.pipeline.output import OSSConfig, OutputError, upload_digest_backup, write_hexo_post
from src.pipeline.persistence import (
    apply_stage1_outcome,
    apply_stage2_outcome,
    persist_normalized_items,
    source_authority_map,
)
from src.pipeline.run_stats import (
    apply_source_stats,
    decide_final_run_status,
    digest_result,
    initial_run_stats,
    update_digest_stats,
)


@dataclass(frozen=True)
class PipelineRunResult:
    status: str
    stats_json: dict[str, Any]
    inserted_count: int
    duplicate_count: int
    normalized_error_count: int
    cleanup_deleted: int


@dataclass(frozen=True)
class PipelineOptions:
    run_id: str
    window_start: datetime
    window_end: datetime
    hexo_posts_dir: str | Path
    oss_config: OSSConfig | None = None


async def run_daily_pipeline(
    session: AsyncSession,
    analyzer: Analyzer,
    options: PipelineOptions,
    *,
    collector=collect_sources,
    hexo_writer=write_hexo_post,
    oss_uploader=upload_digest_backup,
    stats_updater: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> PipelineRunResult:
    sources = await load_approved_sources(session)
    stats = initial_run_stats([source.id for source in sources])
    await _emit_stats(stats, stats_updater)

    fetch_results = await collector(sources, since=options.window_start)
    for result in fetch_results:
        stats = apply_source_stats(stats, result.source_id, result.stats_entry())
        await _emit_stats(stats, stats_updater)

    raw_items = [raw for result in fetch_results for raw in result.items]
    normalized_items = []
    normalized_error_count = 0
    source_by_id = {source.id: source for source in sources}
    for raw in raw_items:
        source = source_by_id.get(raw.source_id)
        if source is None:
            normalized_error_count += 1
            continue
        try:
            normalized_items.append(
                normalize_raw_item(
                    raw,
                    source_domain=source.domain,
                    run_id=options.run_id,
                    fetched_at=options.window_end,
                    now=options.window_end,
                )
            )
        except NormalizationError:
            normalized_error_count += 1

    persist_result = await persist_normalized_items(
        session,
        normalized_items,
        source_authority_by_id=source_authority_map(sources),
    )
    stats["dedup_skipped"] = persist_result.duplicates
    await _emit_stats(stats, stats_updater)

    inserted_items = persist_result.inserted
    stats["stage1"] = {"total": len(inserted_items), "succeeded": 0, "failed": 0}
    await _emit_stats(stats, stats_updater)
    for item in inserted_items:
        source = source_by_id[item.source_id]
        outcome = await analyzer.analyze_stage1(_item_payload(item), _source_payload(source))
        apply_stage1_outcome(item, outcome)
        if outcome.error:
            stats["stage1"]["failed"] += 1
        else:
            stats["stage1"]["succeeded"] += 1
        await _emit_stats(stats, stats_updater)

    stage2_items = [item for item in inserted_items if should_run_stage2(item.insight_score)]
    stats["stage2"] = {"total": len(stage2_items), "succeeded": 0, "failed": 0}
    await _emit_stats(stats, stats_updater)
    for item in stage2_items:
        source = source_by_id[item.source_id]
        outcome = await analyzer.analyze_stage2(_item_payload(item), _source_payload(source), item.also_seen_in)
        apply_stage2_outcome(item, outcome)
        if outcome.error:
            stats["stage2"]["failed"] += 1
        else:
            stats["stage2"]["succeeded"] += 1
        await _emit_stats(stats, stats_updater)

    stats["digest"]["status"] = "running"
    await _emit_stats(stats, stats_updater)
    digest_date = beijing_digest_date(options.window_end)
    generated_digests = []
    for domain in parse_csv(settings.digest_domains):
        domain_result = await _generate_and_store_digest(
            domain=domain,
            digest_date=digest_date,
            items=[item for item in inserted_items if item.domain == domain],
            run_id=options.run_id,
            stats=stats,
            analyzer=analyzer,
            posts_dir=options.hexo_posts_dir,
            oss_config=options.oss_config,
            hexo_writer=hexo_writer,
            oss_uploader=oss_uploader,
        )
        generated_digests.extend(domain_result["digests"])
        stats = update_digest_stats(stats, **{domain: domain_result["result"]})
        await _emit_stats(stats, stats_updater)

    for digest in generated_digests:
        session.add(digest)

    cleanup_deleted = await delete_expired_items(session, options.window_end)
    stats["retention_deleted"] = cleanup_deleted
    await _emit_stats(stats, stats_updater)

    final_status = decide_final_run_status(stats)
    return PipelineRunResult(
        status=final_status,
        stats_json=stats,
        inserted_count=len(inserted_items),
        duplicate_count=persist_result.duplicates,
        normalized_error_count=normalized_error_count + persist_result.errors,
        cleanup_deleted=cleanup_deleted,
    )


async def load_approved_sources(session: AsyncSession) -> list[Source]:
    result = await session.execute(
        select(Source).where(Source.is_active == true(), Source.status == "approved", Source.health != "disabled")
    )
    return list(result.scalars().all())


async def _generate_and_store_digest(
    *,
    domain: str,
    digest_date,
    items: list[Item],
    run_id: str,
    stats: dict[str, Any],
    analyzer: Analyzer,
    posts_dir: str | Path,
    oss_config: OSSConfig | None,
    hexo_writer,
    oss_uploader,
) -> dict[str, Any]:
    digest_items = [_digest_item(item) for item in items if item.analysis_stage >= 1 and item.insight_score is not None]
    candidate_items = [item for item in digest_items if item.insight_score >= settings.digest_candidate_threshold]
    if not candidate_items:
        return {"result": digest_result(status="skipped"), "digests": []}

    overview = await _generate_digest_overview(analyzer, domain, candidate_items)
    artifact = build_digest_artifact(
        digest_date=digest_date,
        domain=domain,
        items=digest_items,
        collected_count=sum(source.get("items", 0) for source in stats.get("sources", {}).values()),
        analyzed_count=stats.get("stage1", {}).get("succeeded", 0),
        failed_sources=sum(1 for source in stats.get("sources", {}).values() if source.get("status") == "failed"),
        overview=overview,
        generated_at=datetime.now(timezone.utc),
        candidate_threshold=settings.digest_candidate_threshold,
        high_value_threshold=settings.stage2_threshold,
        top_n_per_category=settings.digest_top_n_per_category,
    )
    if artifact is None:
        return {"result": digest_result(status="skipped"), "digests": []}

    try:
        hexo_writer(artifact, posts_dir)
    except OutputError as exc:
        return {"result": digest_result(status="failed", digest_id=artifact.id, hexo_path=artifact.hexo_path, error=exc.category), "digests": []}

    oss_url = None
    if oss_config:
        try:
            oss_url = oss_uploader(artifact, oss_config)
        except OutputError:
            oss_url = None

    digest = _digest_model_from_artifact(artifact, run_id=run_id, oss_url=oss_url)
    return {
        "result": digest_result(status="succeeded", digest_id=digest.id, hexo_path=artifact.hexo_path, oss_url=oss_url),
        "digests": [digest],
    }


async def _generate_digest_overview(analyzer: Analyzer, domain: str, items: list[DigestItem]) -> str | None:
    high_value_payload = [
        {
            "title": item.title,
            "category": item.category,
            "summary_zh": item.summary_zh,
            "insight_score": item.insight_score,
            "action_suggestion": item.action_suggestion,
        }
        for item in items
        if item.insight_score >= settings.stage2_threshold
    ][: settings.digest_overview_max_items]
    outcome = await analyzer.generate_digest_overview(domain, high_value_payload)
    if outcome.analysis is None:
        return None
    return outcome.analysis.overview_zh


def _digest_model_from_artifact(artifact: DigestArtifact, *, run_id: str, oss_url: str | None) -> Digest:
    return Digest(
        id=artifact.id,
        run_id=run_id,
        date=artifact.date,
        domain=artifact.domain,
        title=artifact.title,
        summary=artifact.summary,
        stats_json=artifact.stats_json,
        highlights_json=artifact.highlights_json,
        content_markdown=artifact.content_markdown,
        oss_url=oss_url,
        generated_at=artifact.generated_at,
    )


def _digest_item(item: Item) -> DigestItem:
    return DigestItem(
        id=item.id,
        title=item.title,
        source_id=item.source_id,
        category=item.category or "other",
        summary_zh=item.summary_zh,
        insight_score=item.insight_score or 0,
        confidence=item.confidence,
        action_suggestion=item.action_suggestion,
    )


def _item_payload(item: Item) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "canonical_url": item.canonical_url,
        "content_text": item.content_text,
        "published_at": item.published_at,
        "category": item.category,
        "tags": item.tags,
        "summary_zh": item.summary_zh,
        "insight_score": item.insight_score,
        "credibility": item.credibility,
    }


def _source_payload(source: Source) -> dict[str, Any]:
    return {
        "id": source.id,
        "name": source.name,
        "authority": source.authority,
    }


async def _emit_stats(stats: dict[str, Any], stats_updater: Callable[[dict[str, Any]], Awaitable[None]] | None) -> None:
    if stats_updater:
        await stats_updater(stats)
