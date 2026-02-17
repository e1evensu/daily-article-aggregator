"""
质量过滤器模块

根据域名黑名单和质量规则过滤低质量文章来源。

Requirements:
- 2.1: 维护域名黑名单，包含 csdn.net, zhihu.com, jianshu.com, blog.51cto.com
- 2.2: 当文章来源域名在黑名单中时，标记为低质量并排除在聚合之外
- 2.3: 支持通过配置动态添加或移除黑名单域名
- 2.5: 记录每篇被过滤文章的过滤原因
- 2.6: 当文章来源为已评估通过的高质量 RSS 源时，自动标记为可信来源
"""

from urllib.parse import urlparse
from typing import Set

from src.models import Article
from src.aggregation.models import FilterResult


# 默认黑名单域名
# Validates: Requirements 2.1
DEFAULT_BLACKLIST_DOMAINS: Set[str] = {
    "csdn.net",
    "zhihu.com",
    "jianshu.com",
    "blog.51cto.com",
}


class QualityFilter:
    """
    质量过滤器
    
    根据域名黑名单和可信来源列表过滤文章。
    
    Attributes:
        blacklist_domains: 黑名单域名集合
        trusted_sources: 可信来源集合（RSS 源名称或域名）
    
    Validates: Requirements 2.1, 2.2, 2.3, 2.5, 2.6
    """
    
    def __init__(self, config: dict | None = None):
        """
        初始化过滤器
        
        Args:
            config: 配置字典，包含：
                - blacklist_domains: 黑名单域名列表
                - trusted_sources: 可信来源列表
        
        Validates: Requirements 2.1, 2.3
        """
        config = config or {}
        
        # 初始化黑名单域名
        # 如果配置中提供了黑名单，使用配置的值；否则使用默认值
        blacklist_from_config = config.get("blacklist_domains")
        if blacklist_from_config is not None:
            self._blacklist_domains: Set[str] = set(blacklist_from_config)
        else:
            self._blacklist_domains = DEFAULT_BLACKLIST_DOMAINS.copy()
        
        # 初始化可信来源列表
        trusted_from_config = config.get("trusted_sources", [])
        self._trusted_sources: Set[str] = set(trusted_from_config)
    
    @property
    def blacklist_domains(self) -> Set[str]:
        """返回当前黑名单域名集合的副本"""
        return self._blacklist_domains.copy()
    
    @property
    def trusted_sources(self) -> Set[str]:
        """返回当前可信来源集合的副本"""
        return self._trusted_sources.copy()
    
    def _extract_domain(self, url: str) -> str:
        """
        从 URL 中提取域名
        
        Args:
            url: 文章 URL
        
        Returns:
            域名字符串，如果无法解析则返回空字符串
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            # 移除 www. 前缀以便匹配
            if hostname.startswith("www."):
                hostname = hostname[4:]
            return hostname.lower()
        except Exception:
            return ""
    
    def _domain_matches_blacklist(self, domain: str) -> str | None:
        """
        检查域名是否匹配黑名单中的任何域名
        
        支持子域名匹配，例如 blog.csdn.net 会匹配 csdn.net
        
        Args:
            domain: 要检查的域名
        
        Returns:
            匹配的黑名单域名，如果不匹配则返回 None
        """
        if not domain:
            return None
        
        # 精确匹配
        if domain in self._blacklist_domains:
            return domain
        
        # 子域名匹配：检查域名是否以 .blacklist_domain 结尾
        for blacklist_domain in self._blacklist_domains:
            if domain.endswith(f".{blacklist_domain}"):
                return blacklist_domain
        
        return None
    
    def is_blacklisted(self, url: str) -> bool:
        """
        检查 URL 是否在黑名单中
        
        Args:
            url: 文章 URL
        
        Returns:
            是否被黑名单
        
        Validates: Requirements 2.2
        """
        domain = self._extract_domain(url)
        return self._domain_matches_blacklist(domain) is not None
    
    def is_trusted(self, article: Article) -> bool:
        """
        检查文章是否来自可信来源
        
        可信来源可以是：
        1. 文章的 source 字段在可信来源列表中
        2. 文章 URL 的域名在可信来源列表中
        
        Args:
            article: 文章对象
        
        Returns:
            是否为可信来源
        
        Validates: Requirements 2.6
        """
        # 检查 source 字段
        if article.source and article.source in self._trusted_sources:
            return True
        
        # 检查 URL 域名
        domain = self._extract_domain(article.url)
        if domain and domain in self._trusted_sources:
            return True
        
        return False
    
    def filter_articles(self, articles: list[Article]) -> FilterResult:
        """
        过滤文章列表
        
        过滤逻辑：
        1. 如果文章来自可信来源，直接通过（不检查黑名单）
        2. 如果文章 URL 域名在黑名单中，过滤并记录原因
        3. 其他文章通过
        
        Args:
            articles: 待过滤的文章列表
        
        Returns:
            FilterResult 包含通过和被过滤的文章，以及过滤原因
        
        Validates: Requirements 2.2, 2.5, 2.6
        """
        passed: list[Article] = []
        filtered: list[Article] = []
        filter_reasons: dict[str, str] = {}
        
        for article in articles:
            # 检查是否为可信来源 - 可信来源直接通过
            # Validates: Requirements 2.6
            if self.is_trusted(article):
                passed.append(article)
                continue
            
            # 检查是否在黑名单中
            domain = self._extract_domain(article.url)
            matched_blacklist = self._domain_matches_blacklist(domain)
            
            if matched_blacklist:
                # 文章被过滤
                # Validates: Requirements 2.2, 2.5
                filtered.append(article)
                filter_reasons[article.url] = f"域名 {domain} 在黑名单中（匹配 {matched_blacklist}）"
            else:
                # 文章通过
                passed.append(article)
        
        return FilterResult(
            passed=passed,
            filtered=filtered,
            filter_reasons=filter_reasons,
        )
    
    def add_to_blacklist(self, domain: str) -> None:
        """
        动态添加域名到黑名单
        
        Args:
            domain: 要添加的域名
        
        Validates: Requirements 2.3
        """
        if domain:
            # 标准化域名：移除 www. 前缀，转为小写
            normalized = domain.lower()
            if normalized.startswith("www."):
                normalized = normalized[4:]
            self._blacklist_domains.add(normalized)
    
    def remove_from_blacklist(self, domain: str) -> None:
        """
        从黑名单移除域名
        
        Args:
            domain: 要移除的域名
        
        Validates: Requirements 2.3
        """
        if domain:
            # 标准化域名：移除 www. 前缀，转为小写
            normalized = domain.lower()
            if normalized.startswith("www."):
                normalized = normalized[4:]
            self._blacklist_domains.discard(normalized)
    
    def add_trusted_source(self, source: str) -> None:
        """
        添加可信来源
        
        Args:
            source: 可信来源（RSS 源名称或域名）
        
        Validates: Requirements 2.6
        """
        if source:
            self._trusted_sources.add(source)
    
    def remove_trusted_source(self, source: str) -> None:
        """
        移除可信来源
        
        Args:
            source: 要移除的可信来源
        
        Validates: Requirements 2.6
        """
        if source:
            self._trusted_sources.discard(source)
