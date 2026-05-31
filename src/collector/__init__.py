from src.collector.api import GenericAPICollector, HackerNewsCollector
from src.collector.catalog import (
    SourceCatalogEntry,
    as_source_model,
    catalog_approved_source_ids,
    catalog_by_id,
    catalog_source_ids,
    load_source_catalog,
    seed_candidate_sources,
)
from src.collector.dispatcher import (
    SourceFetchResult,
    collect_sources,
    collection_stats,
    create_collector,
    fetch_source,
)
from src.collector.github import GitHubAdvisoryCollector

__all__ = [
    "GenericAPICollector",
    "GitHubAdvisoryCollector",
    "HackerNewsCollector",
    "SourceFetchResult",
    "SourceCatalogEntry",
    "as_source_model",
    "catalog_approved_source_ids",
    "catalog_by_id",
    "catalog_source_ids",
    "collect_sources",
    "collection_stats",
    "create_collector",
    "fetch_source",
    "load_source_catalog",
    "seed_candidate_sources",
]
