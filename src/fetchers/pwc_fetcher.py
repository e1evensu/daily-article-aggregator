"""
PWCFetcher - Papers With Code 获取器
PWCFetcher - Papers With Code Fetcher

从 Papers With Code 获取关联 GitHub 代码的论文。
Fetches papers with associated GitHub code from Papers With Code.

需求 Requirements:
- 3.2: 获取关联 GitHub 代码的论文
- 3.3: 提取论文标题、摘要、GitHub 仓库链接和 star 数量
- 3.4: 请求失败时记录错误并继续处理其他数据源
"""

import logging
from typing import Any

import requests

from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class PWCFetcher(BaseFetcher):
    """
    Papers With Code 获取器
    Papers With Code Fetcher
    
    从 Papers With Code 获取关联 GitHub 代码的最新论文。
    Fetches latest papers with associated GitHub code from Papers With Code.
    
    Attributes:
        enabled: 是否启用此 Fetcher
        timeout: 请求超时时间（秒）
        limit: 获取论文数量限制
    """
    
    API_BASE = "https://paperswithcode.com/api/v1"
    
    # 备用：直接抓取 trending 页面
    TRENDING_URL = "https://paperswithcode.com/latest"
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化 PWC Fetcher
        Initialize PWC Fetcher
        
        Args:
            config: 配置字典，包含以下键：
                   - enabled: 是否启用 (bool, default=True)
                   - timeout: 请求超时时间秒数 (int, default=30)
                   - limit: 获取论文数量限制 (int, default=50)
        
        Examples:
            >>> config = {
            ...     'enabled': True,
            ...     'timeout': 30,
            ...     'limit': 50
            ... }
            >>> fetcher = PWCFetcher(config)
        """
        self.enabled: bool = config.get('enabled', True)
        self.timeout: int = config.get('timeout', 30)
        self.limit: int = config.get('limit', 50)
    
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
        获取最新论文
        Fetch latest papers
        
        从 Papers With Code API 获取最新的关联代码的论文。
        Fetches latest papers with code from Papers With Code API.
        
        Returns:
            FetchResult: 包含获取的论文列表和可能的错误信息
        """
        if not self.is_enabled():
            return FetchResult(
                items=[],
                source_name='Papers With Code',
                source_type='pwc',
                error='Fetcher is disabled'
            )
        
        # 先尝试 API
        items = self._fetch_from_api()
        
        if not items:
            logger.warning("PWC API 失败，跳过")
        
        logger.info(f"PWC Fetcher: 获取了 {len(items)} 篇论文")
        
        return FetchResult(
            items=items,
            source_name='Papers With Code',
            source_type='pwc'
        )
    
    def _fetch_from_api(self) -> list[dict[str, Any]]:
        """从 API 获取论文"""
        try:
            logger.info(f"Fetching papers from Papers With Code (limit={self.limit})...")
            
            # 获取最新论文
            papers_url = f"{self.API_BASE}/papers/"
            params = {
                'items_per_page': min(self.limit, 50),  # API 限制每页最多 50
                'page': 1,
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; DailyArticleAggregator/1.0)',
                'Accept': 'application/json',
            }
            
            response = requests.get(
                papers_url,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            items: list[dict[str, Any]] = []
            results = data.get('results', [])
            
            for paper in results:
                parsed = self._parse_paper(paper)
                if parsed:
                    items.append(parsed)
            
            return items
            
        except requests.exceptions.Timeout:
            logger.error(f"PWC API request timeout after {self.timeout}s")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"PWC API request failed: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"PWC Fetcher error: {str(e)}")
            return []
    
    def _parse_paper(self, paper: dict) -> dict[str, Any] | None:
        """
        解析论文条目
        Parse paper entry
        
        Args:
            paper: Papers With Code API 返回的论文对象
        
        Returns:
            解析后的论文字典，包含 title, abstract, url, github_url, 
            github_stars, published_date
            如果缺少必要字段则返回 None
        """
        # 提取标题
        # Extract title
        title = paper.get('title', '').strip()
        if not title:
            return None
        
        # 提取摘要
        # Extract abstract
        abstract = paper.get('abstract', '').strip()
        
        # 提取论文 URL
        # Extract paper URL
        paper_url = paper.get('url_abs', '') or paper.get('url_pdf', '')
        if not paper_url:
            # 构建 PWC URL
            paper_id = paper.get('id', '')
            if paper_id:
                paper_url = f"https://paperswithcode.com/paper/{paper_id}"
        
        # 提取发布日期
        # Extract published date
        published_date = paper.get('published', '')
        if published_date:
            # 只保留日期部分
            published_date = published_date[:10] if len(published_date) >= 10 else published_date
        
        # 提取 GitHub 信息
        # Extract GitHub info
        github_url, github_stars = self._extract_github_info(paper)
        
        # 提取作者
        # Extract authors
        authors = paper.get('authors', [])
        if isinstance(authors, list):
            authors = [a if isinstance(a, str) else a.get('name', '') for a in authors]
            authors = [a for a in authors if a]
        
        return {
            'title': title,
            'abstract': abstract,
            'url': paper_url,
            'github_url': github_url,
            'github_stars': github_stars,
            'published_date': published_date,
            'authors': authors,
            'source': 'Papers With Code',
            'source_type': 'pwc',
        }
    
    def _extract_github_info(self, paper: dict) -> tuple[str | None, int | None]:
        """
        从论文中提取 GitHub 信息
        Extract GitHub info from paper
        
        Args:
            paper: 论文对象
        
        Returns:
            (GitHub URL, star 数) 元组
        """
        github_url: str | None = None
        github_stars: int | None = None
        
        # 尝试从 repository 字段获取
        # Try to get from repository field
        repository = paper.get('repository')
        if repository:
            if isinstance(repository, dict):
                github_url = repository.get('url', '')
                github_stars = repository.get('stars')
            elif isinstance(repository, str):
                github_url = repository
        
        # 尝试从 repositories 列表获取
        # Try to get from repositories list
        if not github_url:
            repositories = paper.get('repositories', [])
            if repositories and isinstance(repositories, list):
                repo = repositories[0]
                if isinstance(repo, dict):
                    github_url = repo.get('url', '')
                    github_stars = repo.get('stars')
                elif isinstance(repo, str):
                    github_url = repo
        
        return github_url, github_stars


def parse_pwc_paper(paper: dict) -> dict[str, Any] | None:
    """
    解析 PWC 论文条目（独立函数，用于属性测试）
    Parse PWC paper entry (standalone function for property testing)
    
    Args:
        paper: 论文字典，包含 title, abstract, url_abs 等字段
    
    Returns:
        解析后的论文字典，如果缺少必要字段则返回 None
    
    Examples:
        >>> paper = {
        ...     'title': 'A New AI Paper',
        ...     'abstract': 'This paper presents...',
        ...     'url_abs': 'https://arxiv.org/abs/2401.12345',
        ...     'repository': {'url': 'https://github.com/user/repo', 'stars': 100}
        ... }
        >>> result = parse_pwc_paper(paper)
        >>> result['title']
        'A New AI Paper'
    """
    # 提取标题
    title = paper.get('title', '').strip()
    if not title:
        return None
    
    # 提取摘要
    abstract = paper.get('abstract', '').strip()
    
    # 提取论文 URL
    paper_url = paper.get('url_abs', '') or paper.get('url_pdf', '') or paper.get('url', '')
    if not paper_url:
        paper_id = paper.get('id', '')
        if paper_id:
            paper_url = f"https://paperswithcode.com/paper/{paper_id}"
    
    # 提取发布日期
    published_date = paper.get('published', '') or paper.get('published_date', '')
    if published_date:
        published_date = published_date[:10] if len(published_date) >= 10 else published_date
    
    # 提取 GitHub 信息
    github_url: str | None = None
    github_stars: int | None = None
    
    repository = paper.get('repository')
    if repository:
        if isinstance(repository, dict):
            github_url = repository.get('url', '')
            github_stars = repository.get('stars')
        elif isinstance(repository, str):
            github_url = repository
    
    if not github_url:
        repositories = paper.get('repositories', [])
        if repositories and isinstance(repositories, list):
            repo = repositories[0]
            if isinstance(repo, dict):
                github_url = repo.get('url', '')
                github_stars = repo.get('stars')
            elif isinstance(repo, str):
                github_url = repo
    
    # 提取作者
    authors = paper.get('authors', [])
    if isinstance(authors, list):
        authors = [a if isinstance(a, str) else a.get('name', '') for a in authors]
        authors = [a for a in authors if a]
    
    return {
        'title': title,
        'abstract': abstract,
        'url': paper_url,
        'github_url': github_url,
        'github_stars': github_stars,
        'published_date': published_date,
        'authors': authors,
        'source': 'Papers With Code',
        'source_type': 'pwc',
    }
