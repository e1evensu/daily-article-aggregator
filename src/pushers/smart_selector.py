"""
SmartSelector - 智能推送筛选器
SmartSelector - Smart Push Selector

使用 AI 综合评估所有待推送文章，生成每日精选。
Uses AI to comprehensively evaluate articles and generate daily picks.

功能：
1. 综合评估文章质量和相关性
2. 按主题聚类，避免重复内容
3. 平衡不同来源的文章
4. 生成每日精选摘要
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SmartSelector:
    """
    智能推送筛选器
    
    综合考虑文章质量、相关性、来源多样性，生成每日精选。
    """
    
    def __init__(self, config: dict[str, Any], ai_analyzer: Any = None):
        """
        初始化智能筛选器
        
        Args:
            config: 配置字典
            ai_analyzer: AI 分析器实例
        """
        self.ai_analyzer = ai_analyzer
        self.max_articles = config.get('max_articles', 30)  # 每日最多推送数
        self.min_quality_score = config.get('min_quality_score', 60)  # 最低质量分
        self.source_balance = config.get('source_balance', True)  # 是否平衡来源
        
        logger.info(f"SmartSelector initialized: max={self.max_articles}, min_score={self.min_quality_score}")
    
    def select_articles(
        self, 
        articles: list[dict[str, Any]],
        scored_articles: list[Any] = None
    ) -> list[dict[str, Any]]:
        """
        智能筛选文章
        
        Args:
            articles: 待筛选的文章列表
            scored_articles: 已评分的文章列表（可选）
        
        Returns:
            筛选后的精选文章列表
        """
        if not articles:
            return []
        
        # 如果有评分，使用评分
        if scored_articles:
            article_scores = {
                self._get_article_url(sa): getattr(sa, 'score', 50)
                for sa in scored_articles
            }
        else:
            article_scores = {}
        
        # 第一步：基础质量过滤
        filtered = self._filter_by_quality(articles, article_scores)
        logger.info(f"质量过滤后: {len(filtered)}/{len(articles)} 篇")
        
        # 第二步：来源平衡
        if self.source_balance:
            filtered = self._balance_sources(filtered)
            logger.info(f"来源平衡后: {len(filtered)} 篇")
        
        # 第三步：去除重复/相似内容
        filtered = self._remove_duplicates(filtered)
        logger.info(f"去重后: {len(filtered)} 篇")
        
        # 第四步：限制数量
        if len(filtered) > self.max_articles:
            filtered = filtered[:self.max_articles]
        
        logger.info(f"SmartSelector: 最终选择 {len(filtered)} 篇文章")
        return filtered
    
    def _get_article_url(self, article: Any) -> str:
        """获取文章 URL"""
        if hasattr(article, 'article'):
            return article.article.get('url', '')
        elif isinstance(article, dict):
            return article.get('url', '')
        return ''
    
    def _filter_by_quality(
        self, 
        articles: list[dict[str, Any]],
        scores: dict[str, int]
    ) -> list[dict[str, Any]]:
        """按质量过滤"""
        result = []
        
        for article in articles:
            url = article.get('url', '')
            score = scores.get(url, 50)  # 默认50分
            
            # 检查是否有有效内容
            has_summary = bool(
                article.get('zh_summary') or 
                article.get('summary')
            )
            has_content = bool(
                article.get('content') or
                article.get('description') or
                article.get('short_description')
            )
            
            source_type = article.get('source_type', '')
            
            # KEV 漏洞始终保留（在野利用）
            if source_type == 'kev':
                result.append(article)
                continue
            
            # NVD 漏洞需要高 CVSS
            if source_type == 'nvd':
                cvss = article.get('cvss_score', 0) or 0
                if cvss >= 9.0:  # 严重漏洞
                    result.append(article)
                elif cvss >= 7.0:  # 高危漏洞
                    result.append(article)
                continue
            
            # arXiv 论文：有摘要就保留
            if source_type == 'arxiv':
                if has_summary or has_content:
                    result.append(article)
                continue
            
            # DBLP 顶会论文：始终保留
            if source_type == 'dblp':
                result.append(article)
                continue
            
            # HuggingFace/PWC：有内容就保留
            if source_type in ('huggingface', 'pwc'):
                if has_summary or has_content:
                    result.append(article)
                continue
            
            # Blog：始终保留
            if source_type == 'blog':
                result.append(article)
                continue
            
            # RSS 和其他：有摘要或评分达标
            if has_summary or score >= self.min_quality_score:
                result.append(article)
        
        return result
    
    def _balance_sources(
        self, 
        articles: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """平衡不同来源的文章"""
        # 按来源分组
        by_source: dict[str, list[dict]] = {}
        for article in articles:
            source_type = article.get('source_type', 'other')
            if source_type not in by_source:
                by_source[source_type] = []
            by_source[source_type].append(article)
        
        # 每个来源的配额
        source_quotas = {
            'kev': 10,      # KEV 漏洞（重要）
            'nvd': 5,       # NVD 高危漏洞
            'dblp': 10,     # 顶会论文
            'arxiv': 10,    # arXiv 论文
            'rss': 15,      # RSS 订阅
            'huggingface': 5,
            'pwc': 5,
            'blog': 5,
        }
        
        result = []
        for source_type, source_articles in by_source.items():
            quota = source_quotas.get(source_type, 5)
            result.extend(source_articles[:quota])
        
        return result
    
    def _remove_duplicates(
        self, 
        articles: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """去除重复/相似内容"""
        seen_titles = set()
        result = []
        
        for article in articles:
            title = article.get('title', '').lower().strip()
            
            # 简单的标题去重
            # 提取标题的关键部分（去除 CVE 编号等）
            title_key = title
            if title.startswith('cve-'):
                # CVE 标题：取描述部分
                parts = title.split(':', 1)
                if len(parts) > 1:
                    title_key = parts[1].strip()[:50]
            else:
                title_key = title[:50]
            
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                result.append(article)
        
        return result
    
    def generate_daily_summary(
        self, 
        selected_articles: list[dict[str, Any]]
    ) -> str:
        """
        生成每日精选摘要
        
        Args:
            selected_articles: 精选文章列表
        
        Returns:
            摘要文本
        """
        if not selected_articles:
            return "今日暂无精选内容"
        
        # 按来源统计
        by_source: dict[str, int] = {}
        for article in selected_articles:
            source_type = article.get('source_type', 'other')
            by_source[source_type] = by_source.get(source_type, 0) + 1
        
        # 生成摘要
        parts = [f"📊 今日精选 ({len(selected_articles)} 篇)"]
        
        source_names = {
            'kev': '🔴 在野漏洞',
            'nvd': '🟠 高危CVE',
            'dblp': '📚 顶会论文',
            'arxiv': '📄 arXiv',
            'rss': '📰 订阅文章',
            'huggingface': '🤗 HuggingFace',
            'pwc': '💻 Papers With Code',
            'blog': '📝 大厂博客',
        }
        
        for source_type, count in sorted(by_source.items(), key=lambda x: -x[1]):
            name = source_names.get(source_type, source_type)
            parts.append(f"  {name}: {count} 篇")
        
        return '\n'.join(parts)
