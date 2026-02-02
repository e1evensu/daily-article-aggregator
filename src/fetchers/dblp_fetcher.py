"""
DBLPFetcher - DBLP RSS 获取器
DBLPFetcher - DBLP RSS Fetcher

从 DBLP 获取安全四大顶会（IEEE S&P、ACM CCS、USENIX Security、NDSS）的论文。
Fetches papers from security top-4 conferences via DBLP RSS feeds.

需求 Requirements:
- 1.1: 从安全四大顶会获取论文
- 1.2: 提取论文的标题、作者、会议名称、发布年份和 URL
- 1.3: RSS 请求失败时记录错误并继续处理其他数据源
- 1.4: 根据论文 URL 进行去重
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import feedparser

from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class DBLPFetcher(BaseFetcher):
    """
    DBLP RSS 获取器 - 安全四大顶会
    DBLP RSS Fetcher - Security Top-4 Conferences
    
    从 DBLP 获取安全领域四大顶级会议的最新论文：
    - IEEE S&P (Oakland)
    - ACM CCS
    - USENIX Security
    - NDSS
    
    Attributes:
        enabled: 是否启用此 Fetcher
        enabled_conferences: 启用的会议列表
        timeout: 请求超时时间（秒）
        max_workers: 并发获取的最大线程数
    """
    
    # 预定义的会议 RSS 源
    # Predefined conference RSS feeds
    CONFERENCE_FEEDS: dict[str, dict[str, str]] = {
        'sp': {
            'url': 'https://dblp.org/db/conf/sp/sp.xml',
            'name': 'IEEE S&P',
            'full_name': 'IEEE Symposium on Security and Privacy'
        },
        'ccs': {
            'url': 'https://dblp.org/db/conf/ccs/ccs.xml',
            'name': 'ACM CCS',
            'full_name': 'ACM Conference on Computer and Communications Security'
        },
        'uss': {
            'url': 'https://dblp.org/db/conf/uss/uss.xml',
            'name': 'USENIX Security',
            'full_name': 'USENIX Security Symposium'
        },
        'ndss': {
            'url': 'https://dblp.org/db/conf/ndss/ndss.xml',
            'name': 'NDSS',
            'full_name': 'Network and Distributed System Security Symposium'
        }
    }
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化 DBLP Fetcher
        Initialize DBLP Fetcher
        
        Args:
            config: 配置字典，包含以下键：
                   - enabled: 是否启用 (bool, default=True)
                   - conferences: 启用的会议列表 (list[str], default=all)
                   - timeout: 请求超时时间秒数 (int, default=30)
                   - max_workers: 最大并发线程数 (int, default=4)
        
        Examples:
            >>> config = {
            ...     'enabled': True,
            ...     'conferences': ['sp', 'ccs'],
            ...     'timeout': 30
            ... }
            >>> fetcher = DBLPFetcher(config)
        """
        self.enabled: bool = config.get('enabled', True)
        self.enabled_conferences: list[str] = config.get(
            'conferences', 
            list(self.CONFERENCE_FEEDS.keys())
        )
        self.timeout: int = config.get('timeout', 30)
        self.max_workers: int = config.get('max_workers', 4)
    
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
        从启用的会议获取论文
        Fetch papers from enabled conferences
        
        并发获取所有启用会议的论文，单个会议失败不影响其他会议。
        Fetches papers from all enabled conferences concurrently.
        Single conference failure doesn't affect others.
        
        Returns:
            FetchResult: 包含获取的论文列表和可能的错误信息
        """
        if not self.is_enabled():
            return FetchResult(
                items=[],
                source_name='DBLP',
                source_type='dblp',
                error='Fetcher is disabled'
            )
        
        all_items: list[dict[str, Any]] = []
        errors: list[str] = []
        
        # 过滤出有效的会议
        # Filter valid conferences
        valid_conferences = [
            conf for conf in self.enabled_conferences 
            if conf in self.CONFERENCE_FEEDS
        ]
        
        if not valid_conferences:
            return FetchResult(
                items=[],
                source_name='DBLP',
                source_type='dblp',
                error='No valid conferences configured'
            )
        
        # 并发获取各会议的论文
        # Fetch papers from conferences concurrently
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_conf = {
                executor.submit(self._fetch_conference, conf): conf
                for conf in valid_conferences
            }
            
            for future in as_completed(future_to_conf):
                conf = future_to_conf[future]
                try:
                    items, error = future.result()
                    if items:
                        all_items.extend(items)
                    if error:
                        errors.append(error)
                except Exception as e:
                    error_msg = f"Error fetching {conf}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        
        # 根据 URL 去重
        # Deduplicate by URL
        all_items = self._deduplicate_by_url(all_items)
        
        logger.info(f"DBLP Fetcher: 获取了 {len(all_items)} 篇论文")
        
        return FetchResult(
            items=all_items,
            source_name='DBLP Security Conferences',
            source_type='dblp',
            error='; '.join(errors) if errors else None
        )
    
    def _fetch_conference(
        self, 
        conference: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        获取单个会议的论文
        Fetch papers from a single conference
        
        Args:
            conference: 会议标识符 (sp, ccs, uss, ndss)
        
        Returns:
            (论文列表, 错误信息) 元组
        """
        conf_info = self.CONFERENCE_FEEDS.get(conference)
        if not conf_info:
            return [], f"Unknown conference: {conference}"
        
        url = conf_info['url']
        conf_name = conf_info['name']
        
        try:
            logger.info(f"Fetching papers from {conf_name}...")
            
            # 使用 feedparser 获取 RSS
            # Fetch RSS using feedparser
            feed = feedparser.parse(url)
            
            # 检查是否有错误
            # Check for errors
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"DBLP {conf_name} 解析警告: {feed.bozo_exception}")
            
            items: list[dict[str, Any]] = []
            
            for entry in feed.entries:
                item = self._parse_dblp_entry(entry, conference, conf_name)
                if item:
                    items.append(item)
            
            logger.info(f"从 {conf_name} 获取了 {len(items)} 篇论文")
            return items, None
            
        except Exception as e:
            error_msg = f"Failed to fetch {conf_name}: {str(e)}"
            logger.error(error_msg)
            return [], error_msg
    
    def _parse_dblp_entry(
        self, 
        entry: Any, 
        conference: str,
        conf_name: str
    ) -> dict[str, Any] | None:
        """
        解析 DBLP RSS 条目
        Parse DBLP RSS entry
        
        Args:
            entry: feedparser 条目对象
            conference: 会议标识符
            conf_name: 会议名称
        
        Returns:
            解析后的论文字典，包含 title, authors, conference, year, url
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
            # 尝试从 id 获取
            url = entry.get('id', '').strip()
        if not url:
            return None
        
        # 提取作者
        # Extract authors
        authors = self._extract_authors(entry)
        
        # 提取年份
        # Extract year
        year = self._extract_year(entry, url)
        
        # 提取发布日期
        # Extract published date
        published_date = self._extract_published_date(entry)
        
        return {
            'title': title,
            'authors': authors,
            'conference': conf_name,
            'conference_id': conference,
            'year': year,
            'url': url,
            'source': conf_name,
            'source_type': 'dblp',
            'published_date': published_date,
        }
    
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
                # 可能是逗号分隔的作者列表
                # May be comma-separated author list
                authors = [a.strip() for a in author.split(',') if a.strip()]
        
        # 尝试从 dc:creator 获取
        # Try to get from dc:creator
        if not authors:
            creator = entry.get('dc_creator', '') or entry.get('creator', '')
            if creator:
                authors = [a.strip() for a in creator.split(',') if a.strip()]
        
        return authors
    
    def _extract_year(self, entry: Any, url: str) -> int | None:
        """
        从条目中提取年份
        Extract year from entry
        
        Args:
            entry: feedparser 条目对象
            url: 论文 URL
        
        Returns:
            年份（整数），如果无法提取则返回 None
        """
        # 尝试从 URL 中提取年份
        # Try to extract year from URL
        year_match = re.search(r'/(\d{4})/', url)
        if year_match:
            return int(year_match.group(1))
        
        # 尝试从发布日期提取
        # Try to extract from published date
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            return entry.published_parsed[0]
        
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            return entry.updated_parsed[0]
        
        return None
    
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
    
    def _deduplicate_by_url(
        self, 
        items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        根据 URL 去重，保留首次出现的条目
        Deduplicate by URL, keeping the first occurrence
        
        Args:
            items: 论文列表
        
        Returns:
            去重后的论文列表
        """
        seen_urls: set[str] = set()
        unique_items: list[dict[str, Any]] = []
        
        for item in items:
            url = item.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_items.append(item)
        
        return unique_items


def parse_dblp_entry(
    entry: dict[str, Any], 
    conference: str,
    conf_name: str
) -> dict[str, Any] | None:
    """
    解析 DBLP RSS 条目（独立函数，用于属性测试）
    Parse DBLP RSS entry (standalone function for property testing)
    
    Args:
        entry: 条目字典，包含 title, link, authors 等字段
        conference: 会议标识符
        conf_name: 会议名称
    
    Returns:
        解析后的论文字典，如果缺少必要字段则返回 None
    
    Examples:
        >>> entry = {
        ...     'title': 'A Security Paper',
        ...     'link': 'https://dblp.org/rec/conf/sp/2024/paper1',
        ...     'authors': [{'name': 'Alice'}, {'name': 'Bob'}]
        ... }
        >>> result = parse_dblp_entry(entry, 'sp', 'IEEE S&P')
        >>> result['title']
        'A Security Paper'
        >>> result['conference']
        'IEEE S&P'
    """
    # 提取标题
    title = entry.get('title', '').strip()
    if not title:
        return None
    
    # 提取 URL
    url = entry.get('link', '').strip()
    if not url:
        url = entry.get('id', '').strip()
    if not url:
        return None
    
    # 提取作者
    authors: list[str] = []
    if 'authors' in entry:
        for author in entry['authors']:
            if isinstance(author, dict):
                name = author.get('name', '').strip()
            else:
                name = str(author).strip()
            if name:
                authors.append(name)
    elif 'author' in entry:
        author_str = entry['author'].strip()
        if author_str:
            authors = [a.strip() for a in author_str.split(',') if a.strip()]
    
    # 提取年份
    year: int | None = None
    year_match = re.search(r'/(\d{4})/', url)
    if year_match:
        year = int(year_match.group(1))
    elif 'year' in entry:
        try:
            year = int(entry['year'])
        except (ValueError, TypeError):
            pass
    
    # 提取发布日期
    published_date = entry.get('published_date', '')
    
    return {
        'title': title,
        'authors': authors,
        'conference': conf_name,
        'conference_id': conference,
        'year': year,
        'url': url,
        'source': conf_name,
        'source_type': 'dblp',
        'published_date': published_date,
    }
