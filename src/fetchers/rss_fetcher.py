"""
RSSFetcher - RSS订阅源获取器
RSSFetcher - RSS Feed Fetcher

从RSS订阅源获取文章，支持OPML解析和并发获取。
Fetches articles from RSS feeds with OPML parsing and concurrent fetching.

需求 Requirements:
- 2.1: 解析OPML文件获取订阅源列表
- 2.2: 并发获取多个订阅源的文章
- 2.3: 提取文章的标题、链接、发布日期
- 2.4: 将所有文章加入待处理列表（不限制发布日期）
- 2.5: RSS订阅源请求失败时记录错误并继续处理其他订阅源
- 断点续传: 支持从中断处恢复抓取
"""

import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable
from time import struct_time

import feedparser

logger = logging.getLogger(__name__)


# 回调函数类型定义
FeedCallback = Callable[[str, str, list[dict[str, Any]]], None]  # (url, name, articles) -> None


class RSSFetcher:
    """
    RSS订阅源获取器
    RSS Feed Fetcher
    
    从OPML文件解析订阅源列表，并发获取所有订阅源的文章。
    Parses feed URLs from OPML file and fetches articles from all feeds concurrently.
    
    Attributes:
        opml_path: OPML文件路径
        proxy: 代理URL（可选）
        max_workers: 并发获取的最大线程数
        timeout: 请求超时时间（秒）
    """
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化获取器
        Initialize the fetcher
        
        Args:
            config: 配置字典，包含以下键：
                   - opml_path: OPML文件路径 (str)
                   - proxy: 代理URL (str, optional)
                   - max_workers: 最大并发线程数 (int, optional, default=5)
                   - timeout: 请求超时时间秒数 (int, optional, default=30)
        
        Examples:
            >>> config = {
            ...     'opml_path': 'feeds.opml',
            ...     'proxy': None,
            ...     'max_workers': 5,
            ...     'timeout': 30
            ... }
            >>> fetcher = RSSFetcher(config)
        """
        self.opml_path: str = config.get('opml_path', '')
        self.opml_files: list[str] = config.get('opml_files', [])  # 额外的 OPML 文件列表
        self.proxy: str | None = config.get('proxy')
        self.max_workers: int = config.get('max_workers', 5)
        self.timeout: int = config.get('timeout', 30)

        # 如果有额外的 opml_files，合并所有 URL
        self._all_opml_urls: list[str] = []
        if self.opml_path:
            self._all_opml_urls.extend(self._parse_opml_urls(self.opml_path))
        for opml_file in self.opml_files:
            if Path(opml_file).exists():
                self._all_opml_urls.extend(self._parse_opml_urls(opml_file))
            else:
                logger.warning(f"OPML文件不存在: {opml_file}")
        if self._all_opml_urls:
            logger.info(f"共加载 {len(self._all_opml_urls)} 个 RSS 订阅源（主文件 + {len(self.opml_files)} 个额外文件）")

    def _parse_opml_urls(self, opml_path: str) -> list[str]:
        """解析 OPML 文件获取 URL 列表（内部方法）"""
        try:
            tree = ET.parse(opml_path)
            root = tree.getroot()
            urls: list[str] = []
            for outline in root.iter('outline'):
                xml_url = outline.get('xmlUrl')
                if xml_url:
                    urls.append(xml_url)
            return urls
        except Exception as e:
            logger.error(f"解析 OPML 文件失败 {opml_path}: {e}")
            return []

    def parse_opml(self, opml_path: str) -> list[str]:
        """
        解析OPML文件获取订阅源URL列表
        Parse OPML file to get feed URL list
        
        从OPML文件中提取所有RSS订阅源的xmlUrl属性。
        Extracts xmlUrl attributes from all RSS feed outlines in the OPML file.
        
        Args:
            opml_path: OPML文件路径
        
        Returns:
            订阅源URL列表
        
        Raises:
            FileNotFoundError: 文件不存在
            ET.ParseError: XML解析错误
        
        Examples:
            >>> fetcher = RSSFetcher({})
            >>> urls = fetcher.parse_opml('feeds.opml')
            >>> isinstance(urls, list)
            True
        """
        try:
            tree = ET.parse(opml_path)
            root = tree.getroot()

            urls: list[str] = []

            # 递归查找所有带有xmlUrl属性的outline元素
            # Recursively find all outline elements with xmlUrl attribute
            for outline in root.iter('outline'):
                xml_url = outline.get('xmlUrl')
                if xml_url:
                    urls.append(xml_url)

            logger.info(f"从OPML文件 {opml_path} 解析出 {len(urls)} 个订阅源")
            return urls

    def get_all_feed_urls(self) -> list[str]:
        """获取所有加载的 RSS 订阅源 URL（包括 opml_path 和 opml_files）"""
        return self._all_opml_urls.copy()
            
        except FileNotFoundError:
            logger.error(f"OPML文件不存在: {opml_path}")
            raise
        except ET.ParseError as e:
            logger.error(f"OPML文件解析错误: {e}")
            raise
    
    def fetch_feed(self, url: str) -> tuple[str, list[dict[str, Any]]]:
        """
        获取单个订阅源的文章
        Fetch articles from a single feed
        
        使用feedparser解析RSS订阅源，提取文章的标题、链接、发布日期。
        Uses feedparser to parse RSS feed and extract article title, link, and published date.
        
        Args:
            url: 订阅源URL
        
        Returns:
            (订阅源名称, 文章列表) 元组
            文章字典包含: title, url, source, source_type, published_date
        
        Examples:
            >>> fetcher = RSSFetcher({})
            >>> name, articles = fetcher.fetch_feed('https://example.com/feed.xml')
            >>> isinstance(name, str)
            True
            >>> isinstance(articles, list)
            True
        """
        try:
            # 使用feedparser获取订阅源
            # Fetch feed using feedparser
            feed = feedparser.parse(url)
            
            # 检查是否有错误
            # Check for errors
            if feed.bozo and feed.bozo_exception:
                # bozo表示解析时遇到问题，但可能仍有部分数据
                # bozo indicates parsing issues, but may still have partial data
                # 过滤常见但无害的编码警告
                bozo_msg = str(feed.bozo_exception)
                if 'us-ascii' not in bozo_msg or 'encoding' not in bozo_msg.lower():
                    logger.warning(f"订阅源 {url} 解析警告: {feed.bozo_exception}")
            
            # 获取订阅源名称
            # Get feed name
            feed_name = feed.feed.get('title', url)
            
            articles: list[dict[str, Any]] = []
            
            for entry in feed.entries:
                article = self._entry_to_dict(entry, feed_name)
                if article:
                    articles.append(article)
            
            logger.info(f"从订阅源 '{feed_name}' 获取了 {len(articles)} 篇文章")
            return feed_name, articles
            
        except Exception as e:
            logger.error(f"获取订阅源 {url} 失败: {e}")
            # 返回空结果，不中断其他订阅源的处理
            # Return empty result, don't interrupt processing of other feeds
            return url, []
    
    def _entry_to_dict(self, entry: Any, feed_name: str) -> dict[str, Any] | None:
        """
        将feedparser条目转换为文章字典
        Convert feedparser entry to article dictionary
        
        Args:
            entry: feedparser条目对象
            feed_name: 订阅源名称
        
        Returns:
            文章字典，包含title, url, source, source_type, published_date
            如果缺少必要字段则返回None
        """
        # 提取标题
        # Extract title
        title = entry.get('title', '').strip()
        if not title:
            return None
        
        # 提取链接
        # Extract link
        url = entry.get('link', '').strip()
        if not url:
            return None
        
        # 提取发布日期
        # Extract published date
        published_date = self._parse_published_date(entry)
        
        return {
            'title': title,
            'url': url,
            'source': feed_name,
            'source_type': 'rss',
            'published_date': published_date,
        }
    
    def _parse_published_date(self, entry: Any) -> str:
        """
        解析条目的发布日期
        Parse entry's published date
        
        尝试从多个字段获取发布日期：published_parsed, updated_parsed
        Tries to get published date from multiple fields: published_parsed, updated_parsed
        
        Args:
            entry: feedparser条目对象
        
        Returns:
            ISO格式的日期字符串，如果无法解析则返回空字符串
        """
        # 尝试获取发布时间
        # Try to get published time
        time_struct: struct_time | None = None
        
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
    
    def fetch_all_feeds(
        self, 
        urls: list[str],
        on_feed_complete: FeedCallback | None = None,
        on_feed_error: Callable[[str, str], None] | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """
        并发获取所有订阅源的文章
        Fetch articles from all feeds concurrently
        
        使用线程池并发获取多个订阅源，失败的订阅源会记录错误但不影响其他订阅源。
        支持回调函数用于断点续传。
        Uses thread pool to fetch multiple feeds concurrently. Failed feeds are logged but don't affect others.
        Supports callbacks for checkpoint/resume functionality.
        
        Args:
            urls: 订阅源URL列表
            on_feed_complete: 订阅源完成回调 (url, feed_name, articles) -> None
            on_feed_error: 订阅源失败回调 (url, error) -> None
        
        Returns:
            {订阅源名称: 文章列表} 字典
        
        Examples:
            >>> fetcher = RSSFetcher({'max_workers': 3})
            >>> urls = ['https://example.com/feed1.xml', 'https://example.com/feed2.xml']
            >>> results = fetcher.fetch_all_feeds(urls)
            >>> isinstance(results, dict)
            True
        """
        if not urls:
            logger.warning("没有提供订阅源URL")
            return {}
        
        results: dict[str, list[dict[str, Any]]] = {}
        
        # 使用线程池并发获取
        # Use thread pool for concurrent fetching
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            # Submit all tasks
            future_to_url = {
                executor.submit(self.fetch_feed, url): url 
                for url in urls
            }
            
            # 收集结果
            # Collect results
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    feed_name, articles = future.result()
                    if articles:  # 只添加有文章的订阅源
                        results[feed_name] = articles
                    
                    # 调用完成回调（用于断点续传）
                    if on_feed_complete:
                        try:
                            on_feed_complete(url, feed_name, articles)
                        except Exception as cb_error:
                            logger.warning(f"回调函数执行失败: {cb_error}")
                            
                except Exception as e:
                    # 记录错误但继续处理其他订阅源
                    # Log error but continue processing other feeds
                    error_msg = str(e)
                    logger.error(f"处理订阅源 {url} 时发生错误: {error_msg}")
                    
                    # 调用错误回调
                    if on_feed_error:
                        try:
                            on_feed_error(url, error_msg)
                        except Exception as cb_error:
                            logger.warning(f"错误回调函数执行失败: {cb_error}")
        
        total_articles = sum(len(articles) for articles in results.values())
        logger.info(f"从 {len(results)} 个订阅源共获取 {total_articles} 篇文章")
        
        return results


def parse_opml_content(opml_content: str) -> list[str]:
    """
    解析OPML内容获取订阅源URL列表（独立函数，用于属性测试）
    Parse OPML content to get feed URL list (standalone function for property testing)
    
    从OPML XML内容中提取所有RSS订阅源的xmlUrl属性。
    Extracts xmlUrl attributes from all RSS feed outlines in the OPML XML content.
    
    Args:
        opml_content: OPML格式的XML字符串
    
    Returns:
        订阅源URL列表
    
    Raises:
        ET.ParseError: XML解析错误
    
    Examples:
        >>> opml = '''<?xml version="1.0"?>
        ... <opml version="2.0">
        ...   <body>
        ...     <outline type="rss" xmlUrl="https://example.com/feed.xml"/>
        ...   </body>
        ... </opml>'''
        >>> parse_opml_content(opml)
        ['https://example.com/feed.xml']
    """
    root = ET.fromstring(opml_content)
    
    urls: list[str] = []
    
    # 递归查找所有带有xmlUrl属性的outline元素
    # Recursively find all outline elements with xmlUrl attribute
    for outline in root.iter('outline'):
        xml_url = outline.get('xmlUrl')
        if xml_url:
            urls.append(xml_url)
    
    return urls
