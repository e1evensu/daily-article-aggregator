"""
PriorityScorer - 文章优先级评分器
PriorityScorer - Article Priority Scorer

基于多维度指标对文章进行优先级评分。
Scores articles based on multiple dimensions.

需求 Requirements:
- 8.1: 对文章进行优先级评分 (0-100)
- 8.2: 考虑来源权威性、相关性、时效性
- 8.3: 返回评分和评分理由
- 8.4: 按优先级降序排序
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ScoredArticle:
    """
    带评分的文章数据类
    Scored Article Data Class
    
    封装文章及其优先级评分信息。
    Encapsulates article and its priority score information.
    
    Attributes:
        article: 原始文章数据
        score: 优先级评分 (0-100)
        score_reasons: 评分依据列表
    """
    article: dict[str, Any] = field(default_factory=dict)
    score: int = 0
    score_reasons: list[str] = field(default_factory=list)


class PriorityScorer:
    """
    文章优先级评分器
    Article Priority Scorer
    
    基于多维度指标对文章进行优先级评分：
    1. 来源权威性（source weight）
    2. 内容相关性（AI 评估）
    3. 时效性（发布时间）
    
    Attributes:
        ai_analyzer: AI 分析器实例（可选）
        source_weights: 数据源权重配置
        enable_ai_scoring: 是否启用 AI 评分
    """
    
    # 默认数据源权重
    DEFAULT_SOURCE_WEIGHTS = {
        'kev': 1.5,        # KEV 漏洞权重更高
        'nvd': 1.2,        # NVD 漏洞
        'dblp': 1.3,       # 顶会论文权重更高
        'huggingface': 1.1,
        'pwc': 1.1,
        'blog': 1.0,
        'arxiv': 1.0,
        'rss': 0.8,
    }
    
    def __init__(self, config: dict[str, Any], ai_analyzer: Any = None):
        """
        初始化优先级评分器
        Initialize Priority Scorer
        
        Args:
            config: 配置字典，包含以下键：
                   - source_weights: 数据源权重 (dict, optional)
                   - enable_ai_scoring: 是否启用 AI 评分 (bool, default=True)
            ai_analyzer: AI 分析器实例（可选）
        """
        self.ai_analyzer = ai_analyzer
        self.source_weights: dict[str, float] = {
            **self.DEFAULT_SOURCE_WEIGHTS,
            **config.get('source_weights', {})
        }
        self.enable_ai_scoring: bool = config.get('enable_ai_scoring', True)
        
        logger.info(f"PriorityScorer initialized with {len(self.source_weights)} source weights")
    
    def score_articles(
        self, 
        articles: list[dict[str, Any]]
    ) -> list[ScoredArticle]:
        """
        批量评分文章
        Score articles in batch
        
        Args:
            articles: 文章列表
        
        Returns:
            带评分的文章列表
        """
        results: list[ScoredArticle] = []
        
        for article in articles:
            scored = self.score_single(article)
            results.append(scored)
        
        # 统计
        if results:
            avg_score = sum(r.score for r in results) / len(results)
            logger.info(
                f"PriorityScorer: scored {len(results)} articles, "
                f"avg score: {avg_score:.1f}"
            )
        
        return results
    
    def score_single(self, article: dict[str, Any]) -> ScoredArticle:
        """
        评分单篇文章
        Score a single article
        
        Args:
            article: 文章数据
        
        Returns:
            带评分的文章
        """
        score = 50  # 基础分
        reasons: list[str] = []
        
        # 1. 来源权重评分
        source_score, source_reason = self._score_by_source(article)
        score = int(score * source_score)
        if source_reason:
            reasons.append(source_reason)
        
        # 2. AI 评分（如果启用且有 AI 分析器）
        if self.enable_ai_scoring and self.ai_analyzer:
            ai_score, ai_reasons = self._score_by_ai(article)
            if ai_score is not None:
                # 加权平均：基础分 60%，AI 分 40%
                score = int(score * 0.6 + ai_score * 0.4)
                reasons.extend(ai_reasons)
        
        # 3. 确保分数在 0-100 范围内
        score = max(0, min(100, score))
        
        return ScoredArticle(
            article=article,
            score=score,
            score_reasons=reasons
        )
    
    def _score_by_source(
        self, 
        article: dict[str, Any]
    ) -> tuple[float, str]:
        """
        根据来源评分
        Score by source
        
        Args:
            article: 文章数据
        
        Returns:
            (权重乘数, 评分原因) 元组
        """
        source_type = article.get('source_type', '').lower()
        source = article.get('source', '').lower()
        
        # 优先使用 source_type，其次使用 source
        weight = self.source_weights.get(
            source_type, 
            self.source_weights.get(source, 1.0)
        )
        
        if weight != 1.0:
            reason = f"Source weight: {weight:.1f}x ({source_type or source})"
        else:
            reason = ""
        
        return weight, reason
    
    def _score_by_ai(
        self, 
        article: dict[str, Any]
    ) -> tuple[int | None, list[str]]:
        """
        使用 AI 评分
        Score using AI
        
        Args:
            article: 文章数据
        
        Returns:
            (AI 评分, 评分原因列表) 元组
        """
        if not self.ai_analyzer:
            return None, []
        
        try:
            result = self.ai_analyzer.score_article_priority(article)
            
            if result is None:
                return None, []
            
            score = result.get('score', 50)
            reasons = result.get('reasons', [])
            
            # 确保分数在 0-100 范围内
            score = max(0, min(100, int(score)))
            
            return score, reasons
            
        except Exception as e:
            logger.warning(f"AI scoring failed: {e}")
            return None, []
    
    def sort_by_priority(
        self, 
        scored_articles: list[ScoredArticle]
    ) -> list[ScoredArticle]:
        """
        按优先级降序排序
        Sort by priority descending
        
        Args:
            scored_articles: 带评分的文章列表
        
        Returns:
            排序后的文章列表
        """
        return sorted(scored_articles, key=lambda x: x.score, reverse=True)
    
    def get_top_articles(
        self, 
        scored_articles: list[ScoredArticle],
        n: int = 10
    ) -> list[ScoredArticle]:
        """
        获取前 N 篇高优先级文章
        Get top N high priority articles
        
        Args:
            scored_articles: 带评分的文章列表
            n: 返回数量
        
        Returns:
            前 N 篇文章
        """
        sorted_articles = self.sort_by_priority(scored_articles)
        return sorted_articles[:n]


def score_article(
    article: dict[str, Any],
    source_weights: dict[str, float] | None = None,
) -> ScoredArticle:
    """
    评分单篇文章（独立函数，用于属性测试）
    Score a single article (standalone function for property testing)
    
    Args:
        article: 文章数据
        source_weights: 数据源权重（可选）
    
    Returns:
        带评分的文章
    
    Examples:
        >>> article = {'title': 'Test', 'source_type': 'kev'}
        >>> result = score_article(article)
        >>> 0 <= result.score <= 100
        True
    """
    scorer = PriorityScorer({
        'source_weights': source_weights or {},
        'enable_ai_scoring': False
    })
    return scorer.score_single(article)
