"""
BlogFetcher - 大厂博客 RSS 获取器
BlogFetcher - Tech Company Blog RSS Fetcher

从 AI 大厂官方博客获取最新文章。
Fetches latest articles from AI tech company official blogs.

需求 Requirements:
- 4.1: 支持 OpenAI、DeepMind、Anthropic 博客
- 4.2: 提取标题、发布日期、摘要和原文链接
- 4.3: 请求失败时记录错误并继续处理其他数据源
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import feedparser

from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class BlogFetcher(BaseFetcher):
    """
    大厂博客 RSS 获取器
    Tech Company Blog RSS Fetcher
    
    从 AI 大厂官方博客获取最新文章，支持 OpenAI、DeepMind、Anthropic。
    Fetches latest articles from AI tech company official blogs.
    
    Attributes:
        enabled: 是否启用此 Fetcher
        enabled_blogs: 启用的博客列表
        timeout: 请求超时时间（秒）
        max_workers: 并发获取的最大线程数
    """
    
    # 预定义的博客 RSS 源
    # Predefined blog RSS feeds
    BLOG_FEEDS: dict[str, dict[str, str]] = {
        'openai': {
            'url': 'https://openai.com/blog/rss/',
            'name': 'OpenAI Blog',
            'company': 'OpenAI'
        },
        'deepmind': {
            'url': 'https://deepmind.google/blog/rss.xml',
            'name': 'DeepMind Blog',
            'company': 'DeepMind'
        },
        'anthropic': {
            'url': 'https://www.anthropic.com/rss.xml',
            'name': 'Anthropic Blog',
            'company': 'Anthropic'
        }
    }
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化 Blog Fetcher
        Initialize Blog Fetcher
        
        Args:
            config: 配置字典，包含以下键：
                   - enabled: 是否启用 (bool, default=True)
                   - sources: 启用的博客列表 (list[str], default=all)
                   - timeout: 请求超时时间秒数 (int, default=30)
                   - max_workers: 最大并发线程数 (int, default=3)
        
        Examples:
            >>> config = {
            ...     'enabled': True,
            ...     'sources': ['openai', 'anthropic'],
            ...     'timeout': 30
            ... }
            >>> fetcher = BlogFetcher(config)
        """
        self.enabled: bool = config.get('enabled', True)
        self.enabled_blogs: list[str] = config.get(
            'sources', 
            list(self.BLOG_FEEDS.keys())
        )
        self.timeout: int = config.get('timeout', 30)
        self.max_workers: int = config.get('max_workers', 3)
    
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
        获取博客文章
        Fetch blog articles
        
        并发获取所有启用博客的文章，单个博客失败不影响其他博客。
        Fetches articles from all enabled blogs concurrently.
        Single blog failure doesn't affect others.
        
        Returns:
            FetchResult: 包含获取的文章列表和可能的错误信息
        """
        if not self.is_enabled():
            return FetchResult(
                items=[],
                source_name='Tech Blogs',
                source_type='blog',
                error='Fetcher is disabled'
            )
        
        all_items: list[dict[str, Any]] = []
        errors: list[str] = []
        
        # 过滤出有效的博客
        # Filter valid blogs
        valid_blogs = [
            blog for blog in self.enabled_blogs 
            if blog in self.BLOG_FEEDS
        ]
        
        if not valid_blogs:
            return FetchResult(
                items=[],
                source_name='Tech Blogs',
                source_type='blog',
                error='No valid blogs configured'
            )
        
        # 并发获取各博客的文章
        # Fetch articles from blogs concurrently
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_blog = {
                executor.submit(self._fetch_blog, blog): blog
                for blog in valid_blogs
            }
            
            for future in as_completed(future_to_blog):
                blog = future_to_blog[future]
                try:
                    items, error = future.result()
                    if items:
                        all_items.extend(items)
                    if error:
                        errors.append(error)
                except Exception as e:
                    error_msg = f"Error fetching {blog}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        
        logger.info(f"Blog Fetcher: 获取了 {len(all_items)} 篇文章")
        
        return FetchResult(
            items=all_items,
            source_name='Tech Blogs',
            source_type='blog',
            error='; '.join(errors) if errors else None
        )
    
    def _fetch_blog(
        self, 
        blog: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        获取单个博客的文章
        Fetch articles from a single blog
        
        Args:
            blog: 博客标识符 (openai, deepmind, anthropic)
        
        Returns:
            (文章列表, 错误信息) 元组
        """
        blog_info = self.BLOG_FEEDS.get(blog)
        if not blog_info:
            return [], f"Unknown blog: {blog}"
        
        url = blog_info['url']
        blog_name = blog_info['name']
        company = blog_info['company']
        
        try:
            logger.info(f"Fetching articles from {blog_name}...")
            
            # 使用 feedparser 获取 RSS
            # Fetch RSS using feedparser
            feed = feedparser.parse(url)
            
            # 检查是否有错误
            # Check for errors
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"{blog_name} 解析警告: {feed.bozo_exception}")
            
            items: list[dict[str, Any]] = []
            
            for entry in feed.entries:
                item = self._parse_blog_entry(entry, blog, blog_name, company)
                if item:
                    items.append(item)
            
            logger.info(f"从 {blog_name} 获取了 {len(items)} 篇文章")
            return items, None
            
        except Exception as e:
            error_msg = f"Failed to fetch {blog_name}: {str(e)}"
            logger.error(error_msg)
            return [], error_msg
    
    def _parse_blog_entry(
        self, 
        entry: Any, 
        blog: str,
        blog_name: str,
        company: str
    ) -> dict[str, Any] | None:
        """
        解析博客 RSS 条目
        Parse blog RSS entry
        
        Args:
            entry: feedparser 条目对象
            blog: 博客标识符
            blog_name: 博客名称
            company: 公司名称
        
        Returns:
            解析后的文章字典，包含 title, url, summary, published_date
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
        
        return {
            'title': title,
            'url': url,
            'summary': summary,
            'published_date': published_date,
            'blog_id': blog,
            'blog_name': blog_name,
            'company': company,
            'source': blog_name,
            'source_type': 'blog',
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


def parse_blog_entry(
    entry: dict, 
    blog: str,
    blog_name: str,
    company: str
) -> dict[str, Any] | None:
    """
    解析博客 RSS 条目（独立函数，用于属性测试）
    Parse blog RSS entry (standalone function for property testing)
    
    Args:
        entry: 条目字典，包含 title, link, summary 等字段
        blog: 博客标识符
        blog_name: 博客名称
        company: 公司名称
    
    Returns:
        解析后的文章字典，如果缺少必要字段则返回 None
    
    Examples:
        >>> entry = {
        ...     'title': 'New AI Model Released',
        ...     'link': 'https://openai.com/blog/new-model',
        ...     'summary': 'We are excited to announce...',
        ...     'published_date': '2024-01-15'
        ... }
        >>> result = parse_blog_entry(entry, 'openai', 'OpenAI Blog', 'OpenAI')
        >>> result['title']
        'New AI Model Released'
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
    
    return {
        'title': title,
        'url': url,
        'summary': summary,
        'published_date': published_date,
        'blog_id': blog,
        'blog_name': blog_name,
        'company': company,
        'source': blog_name,
        'source_type': 'blog',
    }
