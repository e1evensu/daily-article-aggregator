"""
ArxivFetcher - arXiv论文获取器
ArxivFetcher - arXiv Paper Fetcher

从arXiv获取最新论文，支持分类过滤、关键词过滤和去重。
Fetches latest papers from arXiv with category filtering, keyword filtering, and deduplication.

需求 Requirements:
- 1.1: 从用户配置的arXiv分类列表获取最新论文
- 1.2: 提取论文的标题、ID、摘要、URL和发布日期
- 1.3: 根据论文ID进行去重（跨多个分类）
- 1.4: 根据关键词过滤论文（不区分大小写）
"""

import logging
from datetime import datetime
from typing import Any

import arxiv

logger = logging.getLogger(__name__)


class ArxivFetcher:
    """
    arXiv论文获取器
    arXiv Paper Fetcher
    
    从arXiv API获取论文，支持按分类获取、关键词过滤和ID去重。
    Fetches papers from arXiv API with category filtering, keyword filtering, and ID deduplication.
    
    Attributes:
        categories: arXiv分类列表，如 ['cs.AI', 'cs.CL']
        keywords: 关键词列表，用于过滤论文
        use_llm_filter: 是否使用LLM进行筛选
        max_results: 每个分类的最大获取数量
    """
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化获取器
        Initialize the fetcher
        
        Args:
            config: 配置字典，包含以下键：
                   - categories: arXiv分类列表 (list[str])
                   - keywords: 关键词列表 (list[str])
                   - use_llm_filter: 是否使用LLM筛选 (bool, optional)
                   - max_results: 每个分类的最大获取数量 (int, optional)
        
        Examples:
            >>> config = {
            ...     'categories': ['cs.AI', 'cs.CL'],
            ...     'keywords': ['llm', 'security'],
            ...     'use_llm_filter': False,
            ...     'max_results': 100
            ... }
            >>> fetcher = ArxivFetcher(config)
        """
        self.categories: list[str] = config.get('categories', [])
        self.keywords: list[str] = config.get('keywords', [])
        self.use_llm_filter: bool = config.get('use_llm_filter', False)
        self.max_results: int = config.get('max_results', 100)
        
        # 创建arXiv客户端
        # Create arXiv client
        self.client = arxiv.Client()
    
    def fetch_papers(self, max_results: int | None = None) -> list[dict[str, Any]]:
        """
        获取最新论文
        Fetch latest papers
        
        从配置的所有分类中获取论文，并进行ID去重。
        Fetches papers from all configured categories and deduplicates by ID.
        
        Args:
            max_results: 每个分类的最大获取数量，默认使用配置值
                        Maximum results per category, defaults to config value
        
        Returns:
            论文列表，每个论文包含以下字段：
            List of papers, each containing:
            - title: 论文标题
            - url: 论文URL
            - source: 来源分类（如 'cs.AI'）
            - source_type: 来源类型，固定为 'arxiv'
            - published_date: 发布日期（ISO格式）
            - content: 论文摘要
            - arxiv_id: arXiv ID（用于去重）
        
        Examples:
            >>> fetcher = ArxivFetcher({'categories': ['cs.AI']})
            >>> papers = fetcher.fetch_papers(max_results=10)
            >>> len(papers) <= 10
            True
        """
        if max_results is None:
            max_results = self.max_results
        
        all_papers: list[dict[str, Any]] = []
        
        for category in self.categories:
            try:
                papers = self._fetch_category(category, max_results)
                all_papers.extend(papers)
                logger.info(f"从分类 {category} 获取了 {len(papers)} 篇论文")
            except Exception as e:
                logger.error(f"获取分类 {category} 的论文失败: {e}")
                continue
        
        # 根据论文ID去重
        # Deduplicate by paper ID
        deduplicated = self._deduplicate_papers(all_papers)
        logger.info(f"去重后共 {len(deduplicated)} 篇论文（原始 {len(all_papers)} 篇）")
        
        return deduplicated
    
    def _fetch_category(self, category: str, max_results: int) -> list[dict[str, Any]]:
        """
        获取单个分类的论文
        Fetch papers from a single category
        
        Args:
            category: arXiv分类，如 'cs.AI'
            max_results: 最大获取数量
        
        Returns:
            论文列表
        """
        # 构建搜索查询
        # Build search query
        search = arxiv.Search(
            query=f"cat:{category}",
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )
        
        papers: list[dict[str, Any]] = []
        
        for result in self.client.results(search):
            paper = self._result_to_dict(result, category)
            papers.append(paper)
        
        return papers
    
    def _result_to_dict(self, result: arxiv.Result, category: str) -> dict[str, Any]:
        """
        将arXiv结果转换为字典格式
        Convert arXiv result to dictionary format
        
        Args:
            result: arXiv API返回的结果对象
            category: 来源分类
        
        Returns:
            论文字典，包含title, url, source, source_type, published_date, content, arxiv_id
        """
        # 提取arXiv ID（从URL或entry_id中提取）
        # Extract arXiv ID from URL or entry_id
        arxiv_id = result.entry_id.split('/')[-1]
        
        # 格式化发布日期
        # Format published date
        published_date = ""
        if result.published:
            published_date = result.published.strftime("%Y-%m-%d")
        
        return {
            'title': result.title,
            'url': result.entry_id,
            'source': category,
            'source_type': 'arxiv',
            'published_date': published_date,
            'content': result.summary,  # 摘要作为内容
            'arxiv_id': arxiv_id,  # 用于去重
        }
    
    def _deduplicate_papers(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        根据论文ID去重
        Deduplicate papers by ID
        
        保留每个唯一ID的第一次出现。
        Keeps the first occurrence of each unique ID.
        
        Args:
            papers: 论文列表
        
        Returns:
            去重后的论文列表
        
        Examples:
            >>> papers = [
            ...     {'arxiv_id': '2401.00001', 'title': 'Paper 1'},
            ...     {'arxiv_id': '2401.00001', 'title': 'Paper 1 Duplicate'},
            ...     {'arxiv_id': '2401.00002', 'title': 'Paper 2'}
            ... ]
            >>> fetcher = ArxivFetcher({'categories': []})
            >>> result = fetcher._deduplicate_papers(papers)
            >>> len(result)
            2
        """
        seen_ids: set[str] = set()
        deduplicated: list[dict[str, Any]] = []
        
        for paper in papers:
            paper_id = paper.get('arxiv_id', '')
            if paper_id and paper_id not in seen_ids:
                seen_ids.add(paper_id)
                deduplicated.append(paper)
        
        return deduplicated
    
    def filter_by_keywords(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        根据关键词过滤论文
        Filter papers by keywords
        
        检查论文的标题和摘要（content）是否包含任意一个关键词（不区分大小写）。
        Checks if paper title or abstract (content) contains any keyword (case-insensitive).
        
        Args:
            papers: 论文列表
        
        Returns:
            过滤后的论文列表，每篇论文的标题或摘要中至少包含一个关键词
        
        Examples:
            >>> fetcher = ArxivFetcher({
            ...     'categories': [],
            ...     'keywords': ['llm', 'security']
            ... })
            >>> papers = [
            ...     {'title': 'LLM Safety', 'content': 'Abstract about AI'},
            ...     {'title': 'Database Design', 'content': 'SQL optimization'}
            ... ]
            >>> filtered = fetcher.filter_by_keywords(papers)
            >>> len(filtered)
            1
            >>> filtered[0]['title']
            'LLM Safety'
        """
        if not self.keywords:
            # 没有配置关键词，返回所有论文
            # No keywords configured, return all papers
            return papers
        
        filtered: list[dict[str, Any]] = []
        
        # 将关键词转换为小写以进行不区分大小写的匹配
        # Convert keywords to lowercase for case-insensitive matching
        keywords_lower = [kw.lower() for kw in self.keywords]
        
        for paper in papers:
            title = paper.get('title', '').lower()
            content = paper.get('content', '').lower()
            
            # 检查标题或摘要是否包含任意关键词
            # Check if title or abstract contains any keyword
            for keyword in keywords_lower:
                if keyword in title or keyword in content:
                    filtered.append(paper)
                    break  # 找到一个匹配就够了
        
        logger.info(f"关键词过滤后剩余 {len(filtered)} 篇论文（原始 {len(papers)} 篇）")
        return filtered
    
    def filter_by_llm(self, papers: list[dict[str, Any]], paper_to_hunt: str) -> list[dict[str, Any]]:
        """
        使用LLM筛选论文
        Filter papers using LLM
        
        根据用户描述的研究兴趣，使用LLM判断论文是否相关。
        Uses LLM to determine if papers are relevant based on user's research interests.
        
        Args:
            papers: 论文列表
            paper_to_hunt: 用户描述的研究兴趣/要寻找的论文类型
        
        Returns:
            LLM筛选后的论文列表
        
        Note:
            此方法为存根实现，实际LLM筛选逻辑需要在后续任务中实现。
            This is a stub implementation. Actual LLM filtering logic will be implemented later.
        """
        if not self.use_llm_filter:
            return papers
        
        # TODO: 实现LLM筛选逻辑
        # TODO: Implement LLM filtering logic
        logger.warning("LLM筛选功能尚未实现，返回原始论文列表")
        return papers


def deduplicate_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    独立的论文去重函数（用于属性测试）
    Standalone paper deduplication function (for property testing)
    
    根据论文的'id'字段进行去重，保留每个唯一ID的第一次出现。
    Deduplicates papers by 'id' field, keeping the first occurrence of each unique ID.
    
    Args:
        papers: 论文列表，每个论文应包含'id'字段
    
    Returns:
        去重后的论文列表，保证：
        1. 所有ID唯一
        2. 不丢失任何唯一ID
    
    Examples:
        >>> papers = [
        ...     {'id': 'a', 'title': 'Paper A'},
        ...     {'id': 'a', 'title': 'Paper A Copy'},
        ...     {'id': 'b', 'title': 'Paper B'}
        ... ]
        >>> result = deduplicate_papers(papers)
        >>> len(result)
        2
        >>> set(p['id'] for p in result)
        {'a', 'b'}
    """
    seen_ids: set[str] = set()
    deduplicated: list[dict[str, Any]] = []
    
    for paper in papers:
        paper_id = paper.get('id', '')
        if paper_id and paper_id not in seen_ids:
            seen_ids.add(paper_id)
            deduplicated.append(paper)
    
    return deduplicated


def filter_papers_by_keywords(
    papers: list[dict[str, Any]], 
    keywords: list[str]
) -> list[dict[str, Any]]:
    """
    独立的关键词过滤函数（用于属性测试）
    Standalone keyword filtering function (for property testing)
    
    根据关键词过滤论文，检查标题和摘要（不区分大小写）。
    Filters papers by keywords, checking title and abstract (case-insensitive).
    
    Args:
        papers: 论文列表，每个论文应包含'title'和'abstract'字段
        keywords: 关键词列表
    
    Returns:
        过滤后的论文列表，每篇论文的标题或摘要中至少包含一个关键词
    
    Examples:
        >>> papers = [
        ...     {'title': 'LLM Safety', 'abstract': 'About AI'},
        ...     {'title': 'Database', 'abstract': 'SQL'}
        ... ]
        >>> filter_papers_by_keywords(papers, ['llm'])
        [{'title': 'LLM Safety', 'abstract': 'About AI'}]
    """
    if not keywords:
        return papers
    
    keywords_lower = [kw.lower() for kw in keywords]
    filtered: list[dict[str, Any]] = []
    
    for paper in papers:
        title = paper.get('title', '').lower()
        abstract = paper.get('abstract', '').lower()
        
        for keyword in keywords_lower:
            if keyword in title or keyword in abstract:
                filtered.append(paper)
                break
    
    return filtered
