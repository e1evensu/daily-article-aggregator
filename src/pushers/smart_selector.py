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
5. 实时 AI 评分（三维评分: relevance, quality, timeliness）
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Union, List, Dict

from ..scoring.ai_scorer import AIScorer, AIScoreResult

logger = logging.getLogger(__name__)


class SmartSelector:
    """
    智能推送筛选器

    综合考虑文章质量、相关性、来源多样性，生成每日精选。

    新增功能：
    - 实时 AI 评分（三维评分: relevance, quality, timeliness）
    - 对当天新抓取的文章进行评分
    - 按总分排序筛选
    """

    def __init__(self, config: Dict[str, Any], ai_analyzer: Any = None, ai_scorer: AIScorer = None):
        """
        初始化智能筛选器

        Args:
            config: 配置字典
            ai_analyzer: AI 分析器实例
            ai_scorer: AI 评分器实例（可选，用于实时评分）
        """
        self.ai_analyzer = ai_analyzer
        self.ai_scorer = ai_scorer
        self.max_articles = config.get('max_articles', 30)  # 每日最多推送数
        self.min_quality_score = config.get('min_quality_score', 60)  # 最低质量分
        self.source_balance = config.get('source_balance', True)  # 是否平衡来源

        # AI 评分配置
        self.enable_realtime_scoring = config.get('enable_realtime_scoring', True)  # 是否启用实时评分
        self.scoring_threshold = config.get('scoring_threshold', 40)  # 评分阈值，低于此分数直接过滤

        logger.info(f"SmartSelector initialized: max={self.max_articles}, min_score={self.min_quality_score}, realtime_scoring={self.enable_realtime_scoring}")
    
    def select_articles(
        self, 
        articles: List[Dict[str, Any]],
        scored_articles: List[Any] = None
    ) -> List[Dict[str, Any]]:
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
        
        # 第二步：来源平衡（按分数排序后取每个来源的高分文章）
        if self.source_balance:
            filtered = self._balance_sources(filtered, article_scores)
            logger.info(f"来源平衡后: {len(filtered)} 篇")
        
        # 第三步：去除重复/相似内容
        filtered = self._remove_duplicates(filtered)
        logger.info(f"去重后: {len(filtered)} 篇")
        
        # 第四步：不限制数量，全部传给分级推送器按百分比筛选
        # 0-10%: 重点推荐, 10-30%: 推荐, 30-60%: 其他, 后40%不推送
        logger.info(f"SmartSelector: 选出 {len(filtered)} 篇文章，按百分比分级推送")
        return filtered

    def _filter_by_quality(
        self, 
        articles: List[Dict[str, Any]],
        scores: Dict[str, int]
    ) -> List[Dict[str, Any]]:
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
        articles: List[Dict[str, Any]],
        scores: Dict[str, int] = None
    ) -> List[Dict[str, Any]]:
        """平衡不同来源的文章（按分数排序）"""
        if scores is None:
            scores = {}

        # 按来源分组
        by_source: Dict[str, List[dict]] = {}
        for article in articles:
            source_type = article.get('source_type', 'other')
            if source_type not in by_source:
                by_source[source_type] = []
            by_source[source_type].append(article)

        # 每个来源的配额
        source_quotas = {
            'kev': 15,      # KEV 漏洞（重要）
            'nvd': 10,      # NVD 高危漏洞
            'dblp': 15,     # 顶会论文
            'arxiv': 15,    # arXiv 论文
            'rss': 30,      # RSS 订阅
            'huggingface': 10,
            'pwc': 10,
            'blog': 10,
            'github': 10,
            'anthropic_red': 5,
            'atum_blog': 5,
        }

        result = []
        for source_type, source_articles in by_source.items():
            # 按分数排序
            sorted_articles = sorted(
                source_articles,
                key=lambda a: scores.get(a.get('url', ''), a.get('score', 50)),
                reverse=True
            )
            quota = source_quotas.get(source_type, 10)
            result.extend(sorted_articles[:quota])

        return result
    
    def _remove_duplicates(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """去除重复/相似内容 - 按内容相似度"""
        if len(articles) <= 1:
            return articles

        result = []
        # 使用摘要或内容进行相似度比较
        for article in articles:
            content = article.get('zh_summary') or article.get('summary') or article.get('title', '')
            content_lower = content.lower()

            is_duplicate = False
            for existing in result:
                existing_content = existing.get('zh_summary') or existing.get('summary') or existing.get('title', '')
                # 简单比较：如果内容有50%以上相同则认为是重复
                if existing_content and content_lower:
                    # 计算公共字符数
                    common_chars = sum(1 for c in content_lower if c in existing_content.lower())
                    similarity = common_chars / max(len(content_lower), len(existing_content.lower()))
                    if similarity > 0.5:
                        is_duplicate = True
                        break

            if not is_duplicate:
                result.append(article)

        return result

    def generate_daily_summary(
        self, 
        selected_articles: List[Dict[str, Any]]
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
        by_source: Dict[str, int] = {}
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

    # ============== 实时 AI 评分相关方法 ==============

    def score_articles_realtime(
        self,
        articles: List[Dict[str, Any]],
        existing_scores: Dict[str, AIScoreResult] | None = None
    ) -> tuple[List[Dict[str, Any]], Dict[str, AIScoreResult]]:
        """
        对当天新抓取的文章进行实时 AI 评分

        Args:
            articles: 待评分的文章列表
            existing_scores: 已有的评分结果字典 {url: AIScoreResult}

        Returns:
            (带评分的文章列表, 所有评分结果字典)
        """
        if not self.ai_scorer or not self.enable_realtime_scoring:
            logger.info("Real-time AI scoring is disabled or no scorer available")
            return articles, existing_scores or {}

        existing_scores = existing_scores or {}

        # 找出需要新评分的文章（当天新抓取的）
        today = datetime.now().date()
        articles_to_score = []

        for article in articles:
            url = article.get('url', '')

            # 如果已有评分，跳过
            if url and url in existing_scores:
                # 将已有评分添加到文章中
                score_result = existing_scores[url]
                article['ai_relevance'] = score_result.relevance
                article['ai_quality'] = score_result.quality
                article['ai_timeliness'] = score_result.timeliness
                article['ai_total_score'] = score_result.total_score
                article['ai_category'] = score_result.category
                article['ai_keywords'] = score_result.keywords
                continue

            # 检查是否是当天新抓取的文章
            fetched_at = article.get('fetched_at', '')
            if fetched_at:
                try:
                    # 尝试解析抓取时间
                    if 'T' in fetched_at:
                        fetched_date = datetime.fromisoformat(fetched_at.replace('Z', '+00:00')).date()
                    else:
                        fetched_date = datetime.strptime(fetched_at, '%Y-%m-%d').date()

                    if fetched_date == today:
                        articles_to_score.append(article)
                    else:
                        # 非当天文章使用默认分数
                        article['ai_relevance'] = 50
                        article['ai_quality'] = 50
                        article['ai_timeliness'] = 50
                        article['ai_total_score'] = 50
                        article['ai_category'] = 'other'
                        article['ai_keywords'] = []
                except Exception:
                    # 无法解析时间，默认评分
                    article['ai_relevance'] = 50
                    article['ai_quality'] = 50
                    article['ai_timeliness'] = 50
                    article['ai_total_score'] = 50
                    article['ai_category'] = 'other'
                    article['ai_keywords'] = []
            else:
                # 没有抓取时间，默认评分
                article['ai_relevance'] = 50
                article['ai_quality'] = 50
                article['ai_timeliness'] = 50
                article['ai_total_score'] = 50
                article['ai_category'] = 'other'
                article['ai_keywords'] = []

        # 对当天新文章进行批量评分
        if articles_to_score:
            logger.info(f"Scoring {len(articles_to_score)} new articles in real-time")

            # 批量评分
            new_scores = self.ai_scorer.score_batch(articles_to_score)

            # 将评分结果添加到文章中
            for article, score_result in zip(articles_to_score, new_scores):
                url = article.get('url', '')
                existing_scores[url] = score_result

                article['ai_relevance'] = score_result.relevance
                article['ai_quality'] = score_result.quality
                article['ai_timeliness'] = score_result.timeliness
                article['ai_total_score'] = score_result.total_score
                article['ai_category'] = score_result.category
                article['ai_keywords'] = score_result.keywords

            logger.info(f"Real-time scoring completed for {len(new_scores)} articles")

        return articles, existing_scores

    def filter_by_ai_score(
        self,
        articles: List[Dict[str, Any]],
        min_score: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        按 AI 总分过滤文章

        Args:
            articles: 文章列表（需要包含 ai_total_score 字段）
            min_score: 最低分数阈值，默认使用配置中的阈值

        Returns:
            过滤后的文章列表
        """
        if min_score is None:
            min_score = self.scoring_threshold

        filtered = [
            article for article in articles
            if article.get('ai_total_score', 50) >= min_score
        ]

        logger.info(f"AI score filtering: {len(filtered)}/{len(articles)} articles passed (min_score={min_score})")
        return filtered

    def sort_by_ai_score(
        self,
        articles: List[Dict[str, Any]],
        descending: bool = True
    ) -> List[Dict[str, Any]]:
        """
        按 AI 总分排序文章

        Args:
            articles: 文章列表（需要包含 ai_total_score 字段）
            descending: 是否降序排列

        Returns:
            排序后的文章列表
        """
        return sorted(
            articles,
            key=lambda x: x.get('ai_total_score', 0),
            reverse=descending
        )

    def select_articles_with_ai_scoring(
        self,
        articles: List[Dict[str, Any]],
        existing_scores: Dict[str, AIScoreResult] | None = None
    ) -> List[Dict[str, Any]]:
        """
        使用 AI 评分智能筛选文章

        完整流程：
        1. 实时 AI 评分（对当天新文章）
        2. 按 AI 总分过滤
        3. 按总分排序
        4. 来源平衡
        5. 去重
        6. 限制数量

        Args:
            articles: 待筛选的文章列表
            existing_scores: 已有的评分结果

        Returns:
            筛选后的精选文章列表
        """
        if not articles:
            return []

        logger.info(f"Starting AI scoring selection for {len(articles)} articles")

        # Step 1: 实时 AI 评分
        scored_articles, all_scores = self.score_articles_realtime(articles, existing_scores)

        # Step 2: 按 AI 总分过滤
        if self.enable_realtime_scoring:
            filtered = self.filter_by_ai_score(scored_articles)
            logger.info(f"After AI score filtering: {len(filtered)} articles")
        else:
            filtered = scored_articles

        # Step 3: 按总分排序
        filtered = self.sort_by_ai_score(filtered)
        logger.info(f"After AI score sorting: top score = {filtered[0].get('ai_total_score', 0) if filtered else 0}")

        # Step 4: 来源平衡
        if self.source_balance:
            filtered = self._balance_sources(filtered)
            logger.info(f"After source balancing: {len(filtered)} articles")

        # Step 5: 去重
        filtered = self._remove_duplicates(filtered)
        logger.info(f"After deduplication: {len(filtered)} articles")

        # Step 6: 限制数量
        if len(filtered) > self.max_articles:
            filtered = filtered[:self.max_articles]

        logger.info(f"AI scoring selection completed: {len(filtered)} articles selected")

        return filtered
