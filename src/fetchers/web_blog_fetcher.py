"""
通用网页博客抓取器

支持从没有 RSS 的博客网站抓取文章。
通过配置支持不同类型的网站（JSON API 或 HTML 解析）。
"""

import logging
import re
from abc import abstractmethod
from datetime import datetime, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup

from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class WebBlogFetcher(BaseFetcher):
    """
    通用网页博客抓取器基类
    
    子类需要实现 _parse_response 方法来处理不同网站的响应格式。
    """
    
    # 子类需要覆盖这些属性
    SOURCE_NAME: str = "Web Blog"
    SOURCE_TYPE: str = "web_blog"
    BASE_URL: str = ""
    
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self.timeout = self.config.get('timeout', 30)
        self.days_back = self.config.get('days_back', 30)
        
        logger.info(f"{self.__class__.__name__} initialized: timeout={self.timeout}s")
    
    def is_enabled(self) -> bool:
        return self.enabled
    
    def fetch(self) -> FetchResult:
        """获取文章列表"""
        if not self.is_enabled():
            return FetchResult(
                items=[],
                source_name=self.SOURCE_NAME,
                source_type=self.SOURCE_TYPE,
                error='Fetcher is disabled'
            )
        
        try:
            logger.info(f"Fetching articles from {self.SOURCE_NAME}...")
            
            response = self._make_request()
            articles = self._parse_response(response)
            
            # 过滤日期
            if self.days_back > 0:
                articles = self._filter_by_date(articles)
            
            logger.info(f"Fetched {len(articles)} articles from {self.SOURCE_NAME}")
            
            return FetchResult(
                items=articles,
                source_name=self.SOURCE_NAME,
                source_type=self.SOURCE_TYPE,
                error=None
            )
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {e}"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name=self.SOURCE_NAME,
                source_type=self.SOURCE_TYPE,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Error fetching {self.SOURCE_NAME}: {e}"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name=self.SOURCE_NAME,
                source_type=self.SOURCE_TYPE,
                error=error_msg
            )
    
    def _make_request(self) -> requests.Response:
        """发起 HTTP 请求，子类可覆盖"""
        return requests.get(
            self.BASE_URL,
            timeout=self.timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
    
    @abstractmethod
    def _parse_response(self, response: requests.Response) -> list[dict[str, Any]]:
        """解析响应，子类必须实现"""
        pass
    
    def _filter_by_date(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按日期过滤文章"""
        cutoff_date = datetime.now() - timedelta(days=self.days_back)
        filtered = []
        
        for article in articles:
            pub_date_str = article.get('published_date', '')
            if not pub_date_str:
                filtered.append(article)
                continue
            
            try:
                # 尝试解析日期
                pub_date_str = pub_date_str.replace('Z', '+00:00')
                if 'T' in pub_date_str:
                    pub_date = datetime.fromisoformat(pub_date_str)
                else:
                    pub_date = datetime.strptime(pub_date_str[:10], '%Y-%m-%d')
                
                if pub_date.replace(tzinfo=None) >= cutoff_date:
                    filtered.append(article)
            except (ValueError, TypeError):
                filtered.append(article)
        
        return filtered
    
    def _build_article(
        self,
        title: str,
        url: str,
        summary: str = '',
        content: str = '',
        published_date: str = '',
        authors: list[str] | None = None
    ) -> dict[str, Any]:
        """构建标准文章字典"""
        return {
            'title': title,
            'url': url,
            'summary': summary,
            'content': content or summary,
            'published_date': published_date or datetime.now().strftime('%Y-%m-%d'),
            'source': self.SOURCE_NAME,
            'source_type': self.SOURCE_TYPE,
            'authors': authors or [],
            'fetched_at': datetime.now().isoformat(),
        }


class HunyuanFetcher(WebBlogFetcher):
    """腾讯混元研究博客抓取器"""
    
    SOURCE_NAME = "腾讯混元研究"
    SOURCE_TYPE = "hunyuan"
    BASE_URL = "https://api.hunyuan.tencent.com/api/blog/publicList"
    SITE_URL = "https://hy.tencent.com/research"
    
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.page_size = self.config.get('page_size', 20)
    
    def _make_request(self) -> requests.Response:
        """使用 POST 请求 JSON API"""
        return requests.post(
            self.BASE_URL,
            json={"page": 1, "pageSize": self.page_size},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout
        )
    
    def _parse_response(self, response: requests.Response) -> list[dict[str, Any]]:
        """解析 JSON API 响应"""
        data = response.json()
        if data.get('code') != 0:
            logger.error(f"API error: {data.get('msg')}")
            return []
        
        articles = []
        blog_list = data.get('data', {}).get('list', [])
        
        for item in blog_list:
            article = self._parse_item(item)
            if article:
                articles.append(article)
        
        return articles
    
    def _parse_item(self, item: dict) -> dict[str, Any] | None:
        """解析单个文章"""
        title = item.get('title', '').strip()
        if not title:
            return None
        
        # 构建 URL
        article_id = item.get('id', '')
        url = item.get('link', '') or item.get('url', '')
        if not url and article_id:
            url = f"{self.SITE_URL}/{article_id}"
        
        # 解析日期
        pub_date = item.get('publishTime', '') or item.get('createTime', '')
        if pub_date:
            try:
                if isinstance(pub_date, int):
                    pub_date = datetime.fromtimestamp(pub_date / 1000).strftime('%Y-%m-%d')
                elif 'T' not in str(pub_date):
                    pub_date = str(pub_date)[:10]
            except (ValueError, TypeError):
                pub_date = datetime.now().strftime('%Y-%m-%d')
        
        # 作者
        authors = item.get('authors', [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(',') if a.strip()]
        
        summary = item.get('summary', '') or item.get('description', '') or ''
        
        return self._build_article(
            title=title,
            url=url,
            summary=summary,
            content=item.get('content', '') or summary,
            published_date=pub_date,
            authors=authors
        )


class AnthropicRedFetcher(WebBlogFetcher):
    """Anthropic Red Team 博客抓取器"""
    
    SOURCE_NAME = "Anthropic Red Team"
    SOURCE_TYPE = "anthropic_red"
    BASE_URL = "https://red.anthropic.com"
    
    MONTH_MAP = {
        'January': '01', 'February': '02', 'March': '03', 'April': '04',
        'May': '05', 'June': '06', 'July': '07', 'August': '08',
        'September': '09', 'October': '10', 'November': '11', 'December': '12'
    }
    
    def _parse_response(self, response: requests.Response) -> list[dict[str, Any]]:
        """解析 HTML 页面"""
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []
        current_date = None
        
        for element in soup.find_all(['div', 'a']):
            text = element.get_text(strip=True)
            
            # 检查日期元素
            date_match = re.match(
                r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})$',
                text
            )
            if date_match and element.name == 'div':
                month = self.MONTH_MAP[date_match.group(1)]
                year = date_match.group(2)
                current_date = f"{year}-{month}"
                continue
            
            # 检查文章链接
            if element.name == 'a' and element.get('href'):
                href = element.get('href', '')
                if re.match(r'^/?20\d{2}/', href):
                    article = self._parse_link(element, current_date)
                    if article:
                        articles.append(article)
        
        return articles
    
    def _parse_link(self, link_element, current_date: str | None) -> dict[str, Any] | None:
        """解析文章链接"""
        href = link_element.get('href', '')
        if not href:
            return None
        
        # 构建 URL
        if href.startswith('/'):
            url = f"{self.BASE_URL}{href}"
        elif not href.startswith('http'):
            url = f"{self.BASE_URL}/{href}"
        else:
            url = href
        
        # 提取标题
        h3 = link_element.find('h3')
        title = h3.get_text(strip=True) if h3 else ''
        if not title:
            return None
        
        # 提取摘要
        full_text = link_element.get_text(strip=True)
        summary = full_text.replace(title, '').strip()
        if summary.startswith('-'):
            summary = summary[1:].strip()
        
        # 解析日期
        date_match = re.search(r'/(\d{4})/', href)
        if date_match:
            year = date_match.group(1)
            if current_date and current_date.startswith(year):
                published_date = f"{current_date}-01"
            else:
                published_date = f"{year}-01-01"
        else:
            published_date = datetime.now().strftime('%Y-%m-%d')
        
        return self._build_article(
            title=title,
            url=url,
            summary=summary,
            published_date=published_date,
            authors=['Anthropic Frontier Red Team']
        )



class AtumBlogFetcher(WebBlogFetcher):
    """Atum 博客抓取器 (atum.li)"""
    
    SOURCE_NAME = "Atum Blog"
    SOURCE_TYPE = "atum_blog"
    BASE_URL = "https://atum.li/cn/"
    
    MONTH_MAP = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    
    def _parse_response(self, response: requests.Response) -> list[dict[str, Any]]:
        """解析 HTML 页面"""
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []
        
        # 查找所有文章条目 - 格式: ==> atum, Feb 6, 2026, [tags], title <==
        for element in soup.find_all('div'):
            text = element.get_text(strip=True)
            
            # 匹配文章条目格式
            if text.startswith('==>') and text.endswith('<=='):
                article = self._parse_article_entry(element)
                if article:
                    articles.append(article)
        
        return articles
    
    def _parse_article_entry(self, element) -> dict[str, Any] | None:
        """解析单个文章条目"""
        # 查找文章链接
        links = element.find_all('a')
        article_link = None
        tags = []
        
        for link in links:
            href = link.get('href', '')
            if '/blog/' in href:
                article_link = link
            elif '/tag/' in href:
                tags.append(link.get_text(strip=True))
        
        if not article_link:
            return None
        
        href = article_link.get('href', '')
        title = article_link.get_text(strip=True)
        
        if not title or not href:
            return None
        
        # 构建完整 URL
        if href.startswith('/'):
            url = f"https://atum.li{href}"
        else:
            url = href
        
        # 解析日期 - 格式: "Feb 6, 2026" 或 "Nov 14, 2025"
        text = element.get_text()
        date_match = re.search(
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s+(\d{4})',
            text
        )
        
        if date_match:
            month = self.MONTH_MAP[date_match.group(1)]
            day = date_match.group(2).zfill(2)
            year = date_match.group(3)
            published_date = f"{year}-{month}-{day}"
        else:
            published_date = datetime.now().strftime('%Y-%m-%d')
        
        # 获取摘要 - 下一个兄弟元素
        summary = ""
        next_sibling = element.find_next_sibling('div')
        if next_sibling:
            summary_text = next_sibling.get_text(strip=True)
            # 确保不是另一个文章条目
            if not summary_text.startswith('==>'):
                summary = summary_text
        
        return self._build_article(
            title=title,
            url=url,
            summary=summary,
            published_date=published_date,
            authors=['atum']
        )
