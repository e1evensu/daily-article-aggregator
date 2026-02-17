"""
去重工具模块
Deduplication Utility Module

提供基于 URL 的去重功能，保留首次出现的条目。
Provides URL-based deduplication, keeping the first occurrence.

需求 Requirements:
- 1.4: 根据论文 URL 进行去重
"""

import logging
from typing import Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """
    标准化 URL 以便进行比较
    Normalize URL for comparison
    
    移除 URL 中的查询参数、片段标识符，并统一大小写。
    Removes query parameters, fragment identifiers, and normalizes case.
    
    Args:
        url: 原始 URL
    
    Returns:
        标准化后的 URL
    
    Examples:
        >>> normalize_url('https://Example.com/Path?query=1#section')
        'https://example.com/path'
        >>> normalize_url('HTTPS://EXAMPLE.COM/PATH/')
        'https://example.com/path/'
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url.strip())
        
        # 标准化 scheme 和 netloc 为小写
        # Normalize scheme and netloc to lowercase
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # 保留路径，但移除查询参数和片段
        # Keep path but remove query and fragment
        path = parsed.path
        
        # 重新构建 URL
        # Rebuild URL
        normalized = urlunparse((scheme, netloc, path, '', '', ''))
        
        return normalized
    except Exception:
        # 如果解析失败，返回原始 URL 的小写版本
        # If parsing fails, return lowercase original URL
        return url.strip().lower()


def deduplicate_by_url(
    items: list[dict[str, Any]],
    url_key: str = 'url',
    normalize: bool = True
) -> list[dict[str, Any]]:
    """
    根据 URL 去重，保留首次出现的条目
    Deduplicate by URL, keeping the first occurrence
    
    Args:
        items: 条目列表，每个条目应包含 URL 字段
        url_key: URL 字段的键名，默认为 'url'
        normalize: 是否标准化 URL 进行比较，默认为 True
    
    Returns:
        去重后的条目列表
    
    Examples:
        >>> items = [
        ...     {'title': 'A', 'url': 'https://example.com/1'},
        ...     {'title': 'B', 'url': 'https://example.com/2'},
        ...     {'title': 'A Duplicate', 'url': 'https://example.com/1'},
        ... ]
        >>> result = deduplicate_by_url(items)
        >>> len(result)
        2
        >>> result[0]['title']
        'A'
    """
    if not items:
        return []
    
    seen_urls: set[str] = set()
    unique_items: list[dict[str, Any]] = []
    
    for item in items:
        url = item.get(url_key, '')
        
        if not url:
            # 没有 URL 的条目直接保留
            # Keep items without URL
            unique_items.append(item)
            continue
        
        # 标准化 URL 进行比较
        # Normalize URL for comparison
        compare_url = normalize_url(url) if normalize else url
        
        if compare_url not in seen_urls:
            seen_urls.add(compare_url)
            unique_items.append(item)
    
    removed_count = len(items) - len(unique_items)
    if removed_count > 0:
        logger.info(f"Deduplication: removed {removed_count} duplicate items")
    
    return unique_items


def deduplicate_articles(
    articles: list[dict[str, Any]],
    normalize: bool = True
) -> list[dict[str, Any]]:
    """
    对文章列表进行去重
    Deduplicate article list
    
    这是 deduplicate_by_url 的便捷包装，专门用于文章去重。
    This is a convenience wrapper for deduplicate_by_url, specifically for articles.
    
    Args:
        articles: 文章列表
        normalize: 是否标准化 URL 进行比较
    
    Returns:
        去重后的文章列表
    
    Examples:
        >>> articles = [
        ...     {'title': 'Paper 1', 'url': 'https://arxiv.org/abs/2401.00001'},
        ...     {'title': 'Paper 2', 'url': 'https://arxiv.org/abs/2401.00002'},
        ...     {'title': 'Paper 1 Copy', 'url': 'https://arxiv.org/abs/2401.00001'},
        ... ]
        >>> result = deduplicate_articles(articles)
        >>> len(result)
        2
    """
    return deduplicate_by_url(articles, url_key='url', normalize=normalize)


def merge_and_deduplicate(
    *item_lists: list[dict[str, Any]],
    url_key: str = 'url',
    normalize: bool = True
) -> list[dict[str, Any]]:
    """
    合并多个条目列表并去重
    Merge multiple item lists and deduplicate
    
    Args:
        *item_lists: 多个条目列表
        url_key: URL 字段的键名
        normalize: 是否标准化 URL 进行比较
    
    Returns:
        合并并去重后的条目列表
    
    Examples:
        >>> list1 = [{'title': 'A', 'url': 'https://example.com/1'}]
        >>> list2 = [{'title': 'B', 'url': 'https://example.com/2'}]
        >>> list3 = [{'title': 'A Copy', 'url': 'https://example.com/1'}]
        >>> result = merge_and_deduplicate(list1, list2, list3)
        >>> len(result)
        2
    """
    # 合并所有列表
    # Merge all lists
    merged: list[dict[str, Any]] = []
    for item_list in item_lists:
        if item_list:
            merged.extend(item_list)
    
    # 去重
    # Deduplicate
    return deduplicate_by_url(merged, url_key=url_key, normalize=normalize)
