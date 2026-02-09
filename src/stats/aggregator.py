"""
统计聚合器
Statistics Aggregator

聚合和分析统计数据，生成报告和排名。
Aggregates and analyzes statistics data, generates reports and rankings.

Requirements:
- 9.2, 9.3, 9.4: 热门文章统计
- 10.2, 10.3, 10.4, 10.5: 问答统计
- 11.1, 11.2, 11.3, 11.4, 11.5: 来源质量评估
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from src.stats.models import (
    HotArticle,
    HotQuery,
    QAStats,
    SourceQuality,
)
from src.stats.store import StatsStore

logger = logging.getLogger(__name__)


class StatsAggregator:
    """
    统计聚合器
    Statistics Aggregator
    
    提供统计数据的聚合、分析和报告功能。
    Provides aggregation, analysis, and reporting of statistics data.
    
    Attributes:
        store: 统计数据存储
               Statistics data store
    
    Examples:
        >>> aggregator = StatsAggregator()
        >>> hot_articles = aggregator.get_hot_articles(days=7, limit=10)
        >>> qa_stats = aggregator.get_qa_stats(days=30)
    
    Requirements: 9.2-9.4, 10.2-10.5, 11.1-11.5
    """
    
    # 来源质量评估阈值
    LOW_QUALITY_RESPONSE_RATE = 0.5  # 响应率低于 50% 为低质量
    LOW_QUALITY_AVG_ARTICLES = 1.0   # 平均文章数低于 1 为低质量
    
    def __init__(
        self,
        store: StatsStore | None = None,
        db_path: str = 'data/stats.db'
    ):
        """
        初始化统计聚合器
        Initialize Statistics Aggregator
        
        Args:
            store: 统计数据存储（可选，用于依赖注入）
                   Statistics data store (optional, for dependency injection)
            db_path: 数据库路径（当 store 为 None 时使用）
                     Database path (used when store is None)
        """
        self.store = store or StatsStore(db_path)
    
    # =========================================================================
    # Hot Articles
    # =========================================================================
    
    def get_hot_articles(
        self,
        days: int = 7,
        limit: int = 20,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[HotArticle]:
        """
        获取热门文章
        Get hot articles
        
        根据浏览量排名返回热门文章列表。
        Returns hot articles ranked by view count.
        
        Args:
            days: 统计天数（当 start_time/end_time 未指定时使用）
                  Number of days (used when start_time/end_time not specified)
            limit: 返回数量限制
                   Return count limit
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
        
        Returns:
            热门文章列表
            List of hot articles
        
        Examples:
            >>> articles = aggregator.get_hot_articles(days=7, limit=10)
            >>> for article in articles:
            ...     print(f"{article.rank}. {article.title}: {article.view_count} views")
        
        Requirements: 9.2, 9.3, 9.4
        """
        # 计算时间范围
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(days=days)
        
        # 获取浏览计数
        view_counts = self.store.get_page_view_counts(
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        # 构建热门文章列表
        hot_articles = []
        for rank, (article_id, view_count, unique_viewers) in enumerate(view_counts, 1):
            hot_articles.append(HotArticle(
                article_id=article_id,
                view_count=view_count,
                unique_viewers=unique_viewers,
                rank=rank
            ))
        
        return hot_articles
    
    # =========================================================================
    # QA Statistics
    # =========================================================================
    
    def get_qa_stats(
        self,
        days: int = 30,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> QAStats:
        """
        获取问答统计
        Get QA statistics
        
        聚合问答系统的各项指标。
        Aggregates various metrics of the QA system.
        
        Args:
            days: 统计天数（当 start_time/end_time 未指定时使用）
                  Number of days (used when start_time/end_time not specified)
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
        
        Returns:
            问答统计数据
            QA statistics data
        
        Examples:
            >>> stats = aggregator.get_qa_stats(days=30)
            >>> print(f"Total queries: {stats.total_queries}")
            >>> print(f"Avg relevance: {stats.avg_relevance_score:.2f}")
        
        Requirements: 10.4, 10.5
        """
        # 计算时间范围
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(days=days)
        
        # 获取问答事件
        events = self.store.get_qa_events(
            start_time=start_time,
            end_time=end_time,
            limit=100000  # 获取所有事件用于聚合
        )
        
        if not events:
            return QAStats(
                period_start=start_time,
                period_end=end_time
            )
        
        # 计算统计指标
        total_queries = len(events)
        total_relevance = sum(e.relevance_score for e in events)
        total_response_time = sum(e.response_time_ms for e in events)
        queries_with_sources = sum(1 for e in events if e.sources_used > 0)
        total_sources = sum(e.sources_used for e in events)
        
        # 计算反馈率
        feedback_events = [e for e in events if e.feedback]
        positive_feedback = sum(1 for e in feedback_events if e.feedback == 'positive')
        positive_rate = positive_feedback / len(feedback_events) if feedback_events else 0.0
        
        return QAStats(
            total_queries=total_queries,
            avg_relevance_score=total_relevance / total_queries if total_queries else 0.0,
            avg_response_time_ms=total_response_time / total_queries if total_queries else 0.0,
            positive_feedback_rate=positive_rate,
            queries_with_sources=queries_with_sources,
            avg_sources_per_query=total_sources / total_queries if total_queries else 0.0,
            period_start=start_time,
            period_end=end_time
        )
    
    def get_hot_queries(
        self,
        days: int = 7,
        limit: int = 20,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[HotQuery]:
        """
        获取热门查询
        Get hot queries
        
        根据查询频率排名返回热门查询列表。
        Returns hot queries ranked by frequency.
        
        Args:
            days: 统计天数（当 start_time/end_time 未指定时使用）
                  Number of days (used when start_time/end_time not specified)
            limit: 返回数量限制
                   Return count limit
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
        
        Returns:
            热门查询列表
            List of hot queries
        
        Examples:
            >>> queries = aggregator.get_hot_queries(days=7, limit=10)
            >>> for q in queries:
            ...     print(f"{q.rank}. '{q.query}': {q.count} times")
        
        Requirements: 10.2, 10.3
        """
        # 计算时间范围
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(days=days)
        
        # 获取热门查询
        query_counts = self.store.get_hot_queries(
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        # 构建热门查询列表
        hot_queries = []
        for rank, (query, count, avg_relevance) in enumerate(query_counts, 1):
            hot_queries.append(HotQuery(
                query=query,
                count=count,
                avg_relevance=avg_relevance,
                rank=rank
            ))
        
        return hot_queries
    
    # =========================================================================
    # Source Quality
    # =========================================================================
    
    def get_source_ranking(
        self,
        days: int = 30,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[SourceQuality]:
        """
        获取来源质量排名
        Get source quality ranking
        
        根据可靠性评分排名返回来源质量列表。
        Returns source quality list ranked by reliability score.
        
        Args:
            days: 统计天数（当 start_time/end_time 未指定时使用）
                  Number of days (used when start_time/end_time not specified)
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
        
        Returns:
            来源质量列表（按可靠性评分降序）
            List of source quality (sorted by reliability score descending)
        
        Examples:
            >>> sources = aggregator.get_source_ranking(days=30)
            >>> for s in sources:
            ...     print(f"{s.source_type}: {s.reliability_score:.1f}")
        
        Requirements: 11.1, 11.2, 11.3, 11.4
        """
        # 计算时间范围
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(days=days)
        
        # 获取来源统计
        stats = self.store.get_source_quality_stats(
            start_time=start_time,
            end_time=end_time
        )
        
        # 计算质量指标
        source_qualities = []
        for stat in stats:
            total = stat['total_fetches']
            successful = stat['successful_fetches']
            
            # 计算响应率
            response_rate = successful / total if total > 0 else 0.0
            
            # 计算可靠性评分 (0-100)
            # 基于响应率、平均文章数、平均响应时间
            reliability = self._calculate_reliability_score(
                response_rate=response_rate,
                avg_articles=stat['avg_articles'] or 0,
                avg_response_time=stat['avg_response_time'] or 0
            )
            
            # 判断是否为低质量来源
            is_low_quality = self._is_low_quality_source(
                response_rate=response_rate,
                avg_articles=stat['avg_articles'] or 0
            )
            
            source_qualities.append(SourceQuality(
                source_type=stat['source_type'],
                total_fetches=total,
                successful_fetches=successful,
                response_rate=response_rate,
                avg_articles_per_fetch=stat['avg_articles'] or 0,
                avg_content_length=stat['avg_content_length'] or 0,
                avg_response_time_ms=stat['avg_response_time'] or 0,
                reliability_score=reliability,
                is_low_quality=is_low_quality,
                last_fetch=datetime.fromisoformat(stat['last_fetch']) 
                    if stat['last_fetch'] else None
            ))
        
        # 按可靠性评分降序排序
        source_qualities.sort(key=lambda x: x.reliability_score, reverse=True)
        
        return source_qualities
    
    def _calculate_reliability_score(
        self,
        response_rate: float,
        avg_articles: float,
        avg_response_time: float
    ) -> float:
        """
        计算可靠性评分
        Calculate reliability score
        
        Args:
            response_rate: 响应成功率（0-1）
                           Response success rate (0-1)
            avg_articles: 平均文章数
                          Average articles count
            avg_response_time: 平均响应时间（毫秒）
                               Average response time (ms)
        
        Returns:
            可靠性评分（0-100）
            Reliability score (0-100)
        
        Requirements: 11.2
        """
        # 响应率权重：50%
        response_score = response_rate * 50
        
        # 文章数权重：30%（最高 10 篇得满分）
        article_score = min(avg_articles / 10, 1.0) * 30
        
        # 响应时间权重：20%（5秒以内得满分，超过 30 秒得 0 分）
        if avg_response_time <= 5000:
            time_score = 20
        elif avg_response_time >= 30000:
            time_score = 0
        else:
            time_score = (30000 - avg_response_time) / 25000 * 20
        
        return response_score + article_score + time_score
    
    def _is_low_quality_source(
        self,
        response_rate: float,
        avg_articles: float
    ) -> bool:
        """
        判断是否为低质量来源
        Determine if it's a low quality source
        
        Args:
            response_rate: 响应成功率（0-1）
                           Response success rate (0-1)
            avg_articles: 平均文章数
                          Average articles count
        
        Returns:
            True 如果是低质量来源
            True if it's a low quality source
        
        Requirements: 11.5
        """
        return (
            response_rate < self.LOW_QUALITY_RESPONSE_RATE or
            avg_articles < self.LOW_QUALITY_AVG_ARTICLES
        )
    
    def get_low_quality_sources(
        self,
        days: int = 30
    ) -> list[SourceQuality]:
        """
        获取低质量来源列表
        Get low quality sources list
        
        Args:
            days: 统计天数
                  Number of days
        
        Returns:
            低质量来源列表
            List of low quality sources
        
        Requirements: 11.5
        """
        all_sources = self.get_source_ranking(days=days)
        return [s for s in all_sources if s.is_low_quality]
    
    # =========================================================================
    # Time Series Data
    # =========================================================================
    
    def get_daily_page_views(
        self,
        days: int = 30,
        article_id: str | None = None
    ) -> list[tuple[str, int]]:
        """
        获取每日页面浏览量
        Get daily page views
        
        Args:
            days: 统计天数
                  Number of days
            article_id: 文章 ID（可选，用于特定文章）
                        Article ID (optional, for specific article)
        
        Returns:
            (日期, 浏览量) 元组列表
            List of (date, view_count) tuples
        
        Requirements: 13.2
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # 获取所有浏览事件
        events = self.store.get_page_views(
            article_id=article_id,
            start_time=start_time,
            end_time=end_time,
            limit=100000
        )
        
        # 按日期聚合
        daily_counts: dict[str, int] = {}
        for event in events:
            date_str = event.timestamp.strftime('%Y-%m-%d')
            daily_counts[date_str] = daily_counts.get(date_str, 0) + 1
        
        # 填充缺失日期
        result = []
        current = start_time
        while current <= end_time:
            date_str = current.strftime('%Y-%m-%d')
            result.append((date_str, daily_counts.get(date_str, 0)))
            current += timedelta(days=1)
        
        return result
    
    def get_daily_qa_counts(
        self,
        days: int = 30
    ) -> list[tuple[str, int]]:
        """
        获取每日问答数量
        Get daily QA counts
        
        Args:
            days: 统计天数
                  Number of days
        
        Returns:
            (日期, 问答数) 元组列表
            List of (date, qa_count) tuples
        
        Requirements: 13.2
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # 获取所有问答事件
        events = self.store.get_qa_events(
            start_time=start_time,
            end_time=end_time,
            limit=100000
        )
        
        # 按日期聚合
        daily_counts: dict[str, int] = {}
        for event in events:
            date_str = event.timestamp.strftime('%Y-%m-%d')
            daily_counts[date_str] = daily_counts.get(date_str, 0) + 1
        
        # 填充缺失日期
        result = []
        current = start_time
        while current <= end_time:
            date_str = current.strftime('%Y-%m-%d')
            result.append((date_str, daily_counts.get(date_str, 0)))
            current += timedelta(days=1)
        
        return result
