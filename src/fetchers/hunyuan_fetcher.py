"""
腾讯混元研究博客抓取器

从腾讯混元研究页面获取最新的研究文章。
API: https://api.hunyuan.tencent.com/api/blog/publicList
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class HunyuanFetcher(BaseFetcher):
    """
    腾讯混元研究博客抓取器
    
    从腾讯混元研究页面获取最新的 AI 研究文章。
    
    Attributes:
        api_url: API 地址
        timeout: 请求超时时间
        days_back: 获取多少天内的文章
    """
    
    API_URL = "https://api.hunyuan.tencent.com/api/blog/publicList"
    BASE_URL = "https://hy.tencent.com/research"
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化抓取器
        
        Args:
            config: 配置字典，支持以下参数：
                - enabled: 是否启用（默认 True）
                - timeout: 请求超时时间（默认 30 秒）
                - days_back: 获取多少天内的文章（默认 7 天）
                - page_size: 每页获取数量（默认 20）
        """
        self.config = config or {}
        self.timeout = self.config.get('timeout', 30)
        self.days_back = self.config.get('days_back', 7)
        self.page_size = self.config.get('page_size', 20)
        
        logger.info(
            f"HunyuanFetcher initialized: timeout={self.timeout}s, "
            f"days_back={self.days_back}, page_size={self.page_size}"
        )
    
    def fetch(self) -> list[dict[str, Any]]:
        """
        获取腾讯混元研究文章
        
        Returns:
            文章列表，每篇文章包含：
            - title: 标题
            - url: 文章链接
            - summary: 摘要
            - content: 内容
            - published_date: 发布日期
            - source: 来源名称
            - source_type: 来源类型
            - authors: 作者列表
        """
        articles = []
        cutoff_date = datetime.now() - timedelta(days=self.days_back)
        
        try:
            # 获取文章列表
            response = requests.post(
                self.API_URL,
                json={"page": 1, "pageSize": self.page_size},
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            if data.get('code') != 0:
                logger.error(f"API error: {data.get('msg')}")
                return []
            
            blog_list = data.get('data', {}).get('list', [])
            logger.info(f"Fetched {len(blog_list)} articles from Hunyuan Research")
            
            for item in blog_list:
                try:
                    article = self._parse_article(item)
                    if article:
                        # 检查日期
                        pub_date_str = article.get('published_date', '')
                        if pub_date_str:
                            try:
                                pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                                if pub_date.replace(tzinfo=None) < cutoff_date:
                                    continue
                            except ValueError:
                                pass
                        
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"Error parsing article: {e}")
                    continue
            
            logger.info(f"Parsed {len(articles)} valid articles from Hunyuan Research")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching Hunyuan Research: {e}")
        except Exception as e:
            logger.error(f"Error fetching Hunyuan Research: {e}")
        
        return articles
    
    def _parse_article(self, item: dict) -> dict[str, Any] | None:
        """
        解析单篇文章
        
        Args:
            item: API 返回的文章数据
        
        Returns:
            解析后的文章字典
        """
        title = item.get('title', '').strip()
        if not title:
            return None
        
        # 构建文章 URL
        article_id = item.get('id', '')
        url = item.get('link', '') or item.get('url', '')
        if not url and article_id:
            url = f"{self.BASE_URL}/{article_id}"
        
        # 解析日期
        pub_date = item.get('publishTime', '') or item.get('createTime', '')
        if pub_date:
            try:
                # 尝试解析不同格式的日期
                if isinstance(pub_date, int):
                    pub_date = datetime.fromtimestamp(pub_date / 1000).isoformat()
                elif 'T' not in pub_date:
                    pub_date = datetime.strptime(pub_date, '%Y-%m-%d').isoformat()
            except (ValueError, TypeError):
                pub_date = datetime.now().isoformat()
        else:
            pub_date = datetime.now().isoformat()
        
        # 获取作者
        authors = item.get('authors', [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(',') if a.strip()]
        
        # 获取摘要和内容
        summary = item.get('summary', '') or item.get('description', '') or ''
        content = item.get('content', '') or summary
        
        return {
            'title': title,
            'url': url,
            'summary': summary,
            'content': content,
            'published_date': pub_date,
            'source': '腾讯混元研究',
            'source_type': 'hunyuan',
            'authors': authors,
            'fetched_at': datetime.now().isoformat(),
        }
    
    @property
    def source_type(self) -> str:
        """返回数据源类型"""
        return 'hunyuan'
    
    @property
    def source_name(self) -> str:
        """返回数据源名称"""
        return '腾讯混元研究'
    
    def is_enabled(self) -> bool:
        """
        检查 Fetcher 是否启用
        
        Returns:
            bool: True 如果 Fetcher 已启用
        """
        return self.config.get('enabled', True)
