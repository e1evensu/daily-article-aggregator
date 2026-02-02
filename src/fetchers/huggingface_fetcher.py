"""
HuggingFaceFetcher - HuggingFace Papers RSS 获取器
HuggingFaceFetcher - HuggingFace Papers RSS Fetcher

从 HuggingFace 获取每日 trending AI 论文。
Fetches daily trending AI papers from HuggingFace.

需求 Requirements:
- 3.1: 通过 RSS 获取每日 trending 论文
- 3.4: 请求失败时记录错误并继续处理其他数据源
"""

import logging
from datetime import datetime
from typing import Any

import feedparser

from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class HuggingFaceFetcher(BaseFetcher):
    """
    HuggingFace Papers RSS 获取器
    HuggingFace Papers RSS Fetcher
    
    从 HuggingFace 获取每日 trending AI 论文。
    Fetches daily trending AI papers from HuggingFace.
    
    Attributes:
        enabled: 是否启用此 Fetcher
        timeout: 请求超时时间（秒）
    """
    
    RSS_URL = "https://huggingface.co/papers/rss"
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化 HuggingFace Fetcher
        Initialize HuggingFace Fetcher
        
        Args:
            config: 配置字典，包含以下键：
                   - enabled: 是否启用 (bool, default=True)
                   - timeout: 请求超时时间秒数 (int, default=30)
        
        Examples:
            >>> config = {
            ...     'enabled': True,
            ...     'timeout': 30
            ... }
            >>> fetcher = HuggingFaceFetcher(config)
        """
        self.enabled: bool = config.get('enabled', True)
        self.timeout: int = config.get('timeout', 30)
    
    def is_enabled(self) -> bool:
        """
        检查 Fetcher 是否启用
        Check if the Fetcher is enabled
        
        Returns:
            bool: True 如果 Fetcher 已启用
        """
        return self.enabled
    
    def fetch(self) -> FetchResult:
        """
        获取 trending papers
        Fetch trending papers
        
        从 HuggingFace RSS 获取每日 trending AI 论文。
        Fetches daily trending AI papers from HuggingFace RSS.
        
        Returns:
            FetchResult: 包含获取的论文列表和可能的错误信息
        """
        if not self.is_enabled():
            return FetchResult(
                items=[],
                source_name='HuggingFace Papers',
                source_type='huggingface',
                error='Fetcher is disabled'
            )
        
        try:
            logger.info("Fetching trending papers from HuggingFace...")
            
            # 使用 feedparser 获取 RSS
            # Fetch RSS using feedparser
            feed = feedparser.parse(self.RSS_URL)
            
            # 检查是否有错误
            # Check for errors
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"HuggingFace RSS 解析警告: {feed.bozo_exception}")
            
            items: list[dict[str, Any]] = []
            
            for entry in feed.entries:
                item = self._parse_entry(entry)
                if item:
                    items.append(item)
            
            logger.info(f"HuggingFace Fetcher: 获取了 {len(items)} 篇论文")
            
            return FetchResult(
                items=items,
                source_name='HuggingFace Papers',
                source_type='huggingface'
            )
            
        except Exception as e:
            error_msg = f"HuggingFace Fetcher error: {str(e)}"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name='HuggingFace Papers',
                source_type='huggingface',
                error=error_msg
            )
    
    def _parse_entry(self, entry: Any) -> dict[str, Any] | None:
        """
        解析 RSS 条目
        Parse RSS entry
        
        Args:
            entry: feedparser 条目对象
        
        Returns:
            解析后的论文字典，包含 title, url, summary, published_date
            如果缺少必要字段则返回 None
        """
        # 提取标题
        # Extract title
        title = entry.get('title', '').strip()
        if not title:
            return None
        
        # 提取 URL
        # Extract URL
        url = entry.get('link', '').strip()
        if not url:
            return None
        
        # 提取摘要
        # Extract summary
        summary = entry.get('summary', '').strip()
        if not summary:
            summary = entry.get('description', '').strip()
        
        # 提取发布日期
        # Extract published date
        published_date = self._extract_published_date(entry)
        
        # 提取作者
        # Extract authors
        authors = self._extract_authors(entry)
        
        return {
            'title': title,
            'url': url,
            'summary': summary,
            'authors': authors,
            'published_date': published_date,
            'source': 'HuggingFace Papers',
            'source_type': 'huggingface',
        }
    
    def _extract_published_date(self, entry: Any) -> str:
        """
        从条目中提取发布日期
        Extract published date from entry
        
        Args:
            entry: feedparser 条目对象
        
        Returns:
            ISO 格式的日期字符串，如果无法提取则返回空字符串
        """
        time_struct = None
        
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            time_struct = entry.published_parsed
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            time_struct = entry.updated_parsed
        
        if time_struct:
            try:
                dt = datetime(*time_struct[:6])
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
        
        return ""
    
    def _extract_authors(self, entry: Any) -> list[str]:
        """
        从条目中提取作者列表
        Extract author list from entry
        
        Args:
            entry: feedparser 条目对象
        
        Returns:
            作者名称列表
        """
        authors: list[str] = []
        
        # 尝试从 authors 字段获取
        # Try to get from authors field
        if hasattr(entry, 'authors'):
            for author in entry.authors:
                name = author.get('name', '').strip()
                if name:
                    authors.append(name)
        
        # 尝试从 author 字段获取
        # Try to get from author field
        if not authors and hasattr(entry, 'author'):
            author = entry.author.strip()
            if author:
                authors = [a.strip() for a in author.split(',') if a.strip()]
        
        return authors


def parse_huggingface_entry(entry: dict) -> dict[str, Any] | None:
    """
    解析 HuggingFace RSS 条目（独立函数，用于属性测试）
    Parse HuggingFace RSS entry (standalone function for property testing)
    
    Args:
        entry: 条目字典，包含 title, link, summary 等字段
    
    Returns:
        解析后的论文字典，如果缺少必要字段则返回 None
    
    Examples:
        >>> entry = {
        ...     'title': 'A New AI Paper',
        ...     'link': 'https://huggingface.co/papers/2401.12345',
        ...     'summary': 'This paper presents...'
        ... }
        >>> result = parse_huggingface_entry(entry)
        >>> result['title']
        'A New AI Paper'
    """
    # 提取标题
    title = entry.get('title', '').strip()
    if not title:
        return None
    
    # 提取 URL
    url = entry.get('link', '').strip()
    if not url:
        return None
    
    # 提取摘要
    summary = entry.get('summary', '').strip()
    if not summary:
        summary = entry.get('description', '').strip()
    
    # 提取发布日期
    published_date = entry.get('published_date', '')
    
    # 提取作者
    authors = entry.get('authors', [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(',') if a.strip()]
    
    return {
        'title': title,
        'url': url,
        'summary': summary,
        'authors': authors,
        'published_date': published_date,
        'source': 'HuggingFace Papers',
        'source_type': 'huggingface',
    }
