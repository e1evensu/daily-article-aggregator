# Fetchers module - 数据获取模块
# 包含 BaseFetcher 基类、FetchResult 数据类和各种数据源 Fetcher

from .base import BaseFetcher, FetchResult
from .arxiv_fetcher import (
    ArxivFetcher,
    deduplicate_papers,
    filter_papers_by_keywords,
)
from .rss_fetcher import RSSFetcher, parse_opml_content
from .dblp_fetcher import DBLPFetcher, parse_dblp_entry
from .nvd_fetcher import NVDFetcher, parse_cve
from .kev_fetcher import KEVFetcher, parse_kev_entry
from .huggingface_fetcher import HuggingFaceFetcher, parse_huggingface_entry
from .hunyuan_fetcher import HunyuanFetcher
from .pwc_fetcher import PWCFetcher, parse_pwc_paper
from .blog_fetcher import BlogFetcher, parse_blog_entry

__all__ = [
    # Base classes
    "BaseFetcher",
    "FetchResult",
    # Existing fetchers
    "ArxivFetcher",
    "RSSFetcher",
    "deduplicate_papers",
    "filter_papers_by_keywords",
    "parse_opml_content",
    # New fetchers - Security conferences
    "DBLPFetcher",
    "parse_dblp_entry",
    # New fetchers - Vulnerability databases
    "NVDFetcher",
    "parse_cve",
    "KEVFetcher",
    "parse_kev_entry",
    # New fetchers - AI papers
    "HuggingFaceFetcher",
    "parse_huggingface_entry",
    "HunyuanFetcher",
    "PWCFetcher",
    "parse_pwc_paper",
    # New fetchers - Tech blogs
    "BlogFetcher",
    "parse_blog_entry",
]
