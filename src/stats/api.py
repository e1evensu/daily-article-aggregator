"""
统计 API
Statistics API

提供统计数据的 JSON API 和 CSV 导出功能。
Provides JSON API and CSV export for statistics data.

Requirements:
- 13.1: JSON API 端点
- 13.2: 时间序列数据
- 13.3: 数据导出
- 13.4: CSV 导出
- 13.5: 统计缓存
"""

import csv
import io
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable

from src.stats.aggregator import StatsAggregator
from src.stats.store import StatsStore
from src.stats.topic_tracker import TopicTracker

logger = logging.getLogger(__name__)


class StatsCache:
    """
    统计缓存
    Statistics Cache
    
    带 TTL 的简单内存缓存。
    Simple in-memory cache with TTL.
    
    Attributes:
        ttl_seconds: 缓存过期时间（秒）
                     Cache TTL in seconds
    
    Examples:
        >>> cache = StatsCache(ttl_seconds=300)
        >>> cache.set('hot_articles', data)
        >>> cached = cache.get('hot_articles')
    
    Requirements: 13.5
    """
    
    def __init__(self, ttl_seconds: int = 300):
        """
        初始化缓存
        Initialize cache
        
        Args:
            ttl_seconds: 缓存过期时间（秒）
                         Cache TTL in seconds
        """
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[Any, float]] = {}
    
    def get(self, key: str) -> Any | None:
        """
        获取缓存值
        Get cached value
        
        Args:
            key: 缓存键
                 Cache key
        
        Returns:
            缓存值，如果不存在或已过期则返回 None
            Cached value, or None if not exists or expired
        """
        if key not in self._cache:
            return None
        
        value, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl_seconds:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置缓存值
        Set cached value
        
        Args:
            key: 缓存键
                 Cache key
            value: 缓存值
                   Cache value
        """
        self._cache[key] = (value, time.time())
    
    def invalidate(self, key: str) -> None:
        """
        使缓存失效
        Invalidate cache
        
        Args:
            key: 缓存键
                 Cache key
        """
        if key in self._cache:
            del self._cache[key]
    
    def clear(self) -> None:
        """清除所有缓存"""
        self._cache.clear()


def cached(cache: StatsCache, key_func: Callable[..., str]):
    """
    缓存装饰器
    Cache decorator
    
    Args:
        cache: 缓存实例
               Cache instance
        key_func: 生成缓存键的函数
                  Function to generate cache key
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs)
            cached_value = cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_value
            
            result = func(*args, **kwargs)
            cache.set(key, result)
            logger.debug(f"Cache miss, stored: {key}")
            return result
        return wrapper
    return decorator


class StatsAPI:
    """
    统计 API
    Statistics API
    
    提供统计数据的 JSON API 和导出功能。
    Provides JSON API and export functionality for statistics data.
    
    Attributes:
        aggregator: 统计聚合器
                    Statistics aggregator
        topic_tracker: 话题追踪器
                       Topic tracker
        cache: 统计缓存
               Statistics cache
    
    Examples:
        >>> api = StatsAPI()
        >>> hot_articles = api.get_hot_articles_json(days=7)
        >>> csv_data = api.export_hot_articles_csv(days=7)
    
    Requirements: 13.1, 13.2, 13.3, 13.4, 13.5
    """
    
    def __init__(
        self,
        store: StatsStore | None = None,
        db_path: str = 'data/stats.db',
        cache_ttl_seconds: int = 300
    ):
        """
        初始化统计 API
        Initialize Statistics API
        
        Args:
            store: 统计数据存储（可选，用于依赖注入）
                   Statistics data store (optional, for dependency injection)
            db_path: 数据库路径（当 store 为 None 时使用）
                     Database path (used when store is None)
            cache_ttl_seconds: 缓存过期时间（秒）
                               Cache TTL in seconds
        """
        self.store = store or StatsStore(db_path)
        self.aggregator = StatsAggregator(store=self.store)
        self.topic_tracker = TopicTracker(store=self.store)
        self.cache = StatsCache(ttl_seconds=cache_ttl_seconds)
    
    # =========================================================================
    # JSON API
    # =========================================================================
    
    def get_hot_articles_json(
        self,
        days: int = 7,
        limit: int = 20
    ) -> dict:
        """
        获取热门文章 JSON
        Get hot articles JSON
        
        Args:
            days: 统计天数
                  Number of days
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            JSON 格式的热门文章数据
            Hot articles data in JSON format
        
        Requirements: 13.1
        """
        cache_key = f"hot_articles_{days}_{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        articles = self.aggregator.get_hot_articles(days=days, limit=limit)
        result = {
            'status': 'success',
            'data': {
                'period_days': days,
                'articles': [asdict(a) for a in articles]
            },
            'generated_at': datetime.now().isoformat()
        }
        
        self.cache.set(cache_key, result)
        return result
    
    def get_qa_stats_json(
        self,
        days: int = 30
    ) -> dict:
        """
        获取问答统计 JSON
        Get QA statistics JSON
        
        Args:
            days: 统计天数
                  Number of days
        
        Returns:
            JSON 格式的问答统计数据
            QA statistics data in JSON format
        
        Requirements: 13.1
        """
        cache_key = f"qa_stats_{days}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        stats = self.aggregator.get_qa_stats(days=days)
        result = {
            'status': 'success',
            'data': {
                'period_days': days,
                'stats': {
                    'total_queries': stats.total_queries,
                    'avg_relevance_score': round(stats.avg_relevance_score, 3),
                    'avg_response_time_ms': round(stats.avg_response_time_ms, 1),
                    'positive_feedback_rate': round(stats.positive_feedback_rate, 3),
                    'queries_with_sources': stats.queries_with_sources,
                    'avg_sources_per_query': round(stats.avg_sources_per_query, 2),
                    'period_start': stats.period_start.isoformat() if stats.period_start else None,
                    'period_end': stats.period_end.isoformat() if stats.period_end else None
                }
            },
            'generated_at': datetime.now().isoformat()
        }
        
        self.cache.set(cache_key, result)
        return result
    
    def get_hot_queries_json(
        self,
        days: int = 7,
        limit: int = 20
    ) -> dict:
        """
        获取热门查询 JSON
        Get hot queries JSON
        
        Args:
            days: 统计天数
                  Number of days
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            JSON 格式的热门查询数据
            Hot queries data in JSON format
        
        Requirements: 13.1
        """
        cache_key = f"hot_queries_{days}_{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        queries = self.aggregator.get_hot_queries(days=days, limit=limit)
        result = {
            'status': 'success',
            'data': {
                'period_days': days,
                'queries': [asdict(q) for q in queries]
            },
            'generated_at': datetime.now().isoformat()
        }
        
        self.cache.set(cache_key, result)
        return result
    
    def get_source_ranking_json(
        self,
        days: int = 30
    ) -> dict:
        """
        获取来源排名 JSON
        Get source ranking JSON
        
        Args:
            days: 统计天数
                  Number of days
        
        Returns:
            JSON 格式的来源排名数据
            Source ranking data in JSON format
        
        Requirements: 13.1
        """
        cache_key = f"source_ranking_{days}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        sources = self.aggregator.get_source_ranking(days=days)
        result = {
            'status': 'success',
            'data': {
                'period_days': days,
                'sources': [
                    {
                        'source_type': s.source_type,
                        'total_fetches': s.total_fetches,
                        'successful_fetches': s.successful_fetches,
                        'response_rate': round(s.response_rate, 3),
                        'avg_articles_per_fetch': round(s.avg_articles_per_fetch, 2),
                        'avg_content_length': round(s.avg_content_length, 0),
                        'avg_response_time_ms': round(s.avg_response_time_ms, 1),
                        'reliability_score': round(s.reliability_score, 1),
                        'is_low_quality': s.is_low_quality,
                        'last_fetch': s.last_fetch.isoformat() if s.last_fetch else None
                    }
                    for s in sources
                ]
            },
            'generated_at': datetime.now().isoformat()
        }
        
        self.cache.set(cache_key, result)
        return result
    
    def get_trending_topics_json(
        self,
        days: int = 7,
        limit: int = 20
    ) -> dict:
        """
        获取趋势话题 JSON
        Get trending topics JSON
        
        Args:
            days: 统计天数
                  Number of days
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            JSON 格式的趋势话题数据
            Trending topics data in JSON format
        
        Requirements: 13.1
        """
        cache_key = f"trending_topics_{days}_{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        topics = self.topic_tracker.get_trending_topics(days=days, limit=limit)
        result = {
            'status': 'success',
            'data': {
                'period_days': days,
                'topics': [
                    {
                        'topic': t.topic,
                        'frequency': t.frequency,
                        'trend': t.trend,
                        'change_rate': round(t.change_rate, 3),
                        'is_spike': t.is_spike,
                        'first_seen': t.first_seen.isoformat() if t.first_seen else None,
                        'last_seen': t.last_seen.isoformat() if t.last_seen else None
                    }
                    for t in topics
                ]
            },
            'generated_at': datetime.now().isoformat()
        }
        
        self.cache.set(cache_key, result)
        return result
    
    # =========================================================================
    # Time Series Data
    # =========================================================================
    
    def get_daily_page_views_json(
        self,
        days: int = 30,
        article_id: str | None = None
    ) -> dict:
        """
        获取每日页面浏览量 JSON
        Get daily page views JSON
        
        Args:
            days: 统计天数
                  Number of days
            article_id: 文章 ID（可选）
                        Article ID (optional)
        
        Returns:
            JSON 格式的时间序列数据
            Time series data in JSON format
        
        Requirements: 13.2
        """
        data = self.aggregator.get_daily_page_views(days=days, article_id=article_id)
        return {
            'status': 'success',
            'data': {
                'period_days': days,
                'article_id': article_id,
                'series': [{'date': d, 'count': c} for d, c in data]
            },
            'generated_at': datetime.now().isoformat()
        }
    
    def get_daily_qa_counts_json(
        self,
        days: int = 30
    ) -> dict:
        """
        获取每日问答数量 JSON
        Get daily QA counts JSON
        
        Args:
            days: 统计天数
                  Number of days
        
        Returns:
            JSON 格式的时间序列数据
            Time series data in JSON format
        
        Requirements: 13.2
        """
        data = self.aggregator.get_daily_qa_counts(days=days)
        return {
            'status': 'success',
            'data': {
                'period_days': days,
                'series': [{'date': d, 'count': c} for d, c in data]
            },
            'generated_at': datetime.now().isoformat()
        }
    
    # =========================================================================
    # CSV Export
    # =========================================================================
    
    def export_hot_articles_csv(
        self,
        days: int = 7,
        limit: int = 100
    ) -> str:
        """
        导出热门文章 CSV
        Export hot articles CSV
        
        Args:
            days: 统计天数
                  Number of days
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            CSV 格式的字符串
            CSV formatted string
        
        Requirements: 13.4
        """
        articles = self.aggregator.get_hot_articles(days=days, limit=limit)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow(['rank', 'article_id', 'title', 'view_count', 'unique_viewers', 'source_type'])
        
        # 写入数据
        for article in articles:
            writer.writerow([
                article.rank,
                article.article_id,
                article.title,
                article.view_count,
                article.unique_viewers,
                article.source_type
            ])
        
        return output.getvalue()
    
    def export_qa_events_csv(
        self,
        days: int = 30,
        limit: int = 1000
    ) -> str:
        """
        导出问答事件 CSV
        Export QA events CSV
        
        Args:
            days: 统计天数
                  Number of days
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            CSV 格式的字符串
            CSV formatted string
        
        Requirements: 13.4
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        events = self.store.get_qa_events(
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow([
            'timestamp', 'query', 'relevance_score', 'sources_used',
            'response_time_ms', 'feedback', 'user_id'
        ])
        
        # 写入数据
        for event in events:
            writer.writerow([
                event.timestamp.isoformat(),
                event.query,
                event.relevance_score,
                event.sources_used,
                event.response_time_ms,
                event.feedback or '',
                event.user_id or ''
            ])
        
        return output.getvalue()
    
    def export_source_quality_csv(
        self,
        days: int = 30
    ) -> str:
        """
        导出来源质量 CSV
        Export source quality CSV
        
        Args:
            days: 统计天数
                  Number of days
        
        Returns:
            CSV 格式的字符串
            CSV formatted string
        
        Requirements: 13.4
        """
        sources = self.aggregator.get_source_ranking(days=days)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow([
            'source_type', 'total_fetches', 'successful_fetches', 'response_rate',
            'avg_articles_per_fetch', 'avg_content_length', 'avg_response_time_ms',
            'reliability_score', 'is_low_quality', 'last_fetch'
        ])
        
        # 写入数据
        for source in sources:
            writer.writerow([
                source.source_type,
                source.total_fetches,
                source.successful_fetches,
                round(source.response_rate, 3),
                round(source.avg_articles_per_fetch, 2),
                round(source.avg_content_length, 0),
                round(source.avg_response_time_ms, 1),
                round(source.reliability_score, 1),
                source.is_low_quality,
                source.last_fetch.isoformat() if source.last_fetch else ''
            ])
        
        return output.getvalue()
    
    def export_trending_topics_csv(
        self,
        days: int = 7,
        limit: int = 100
    ) -> str:
        """
        导出趋势话题 CSV
        Export trending topics CSV
        
        Args:
            days: 统计天数
                  Number of days
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            CSV 格式的字符串
            CSV formatted string
        
        Requirements: 13.4
        """
        topics = self.topic_tracker.get_trending_topics(days=days, limit=limit)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow([
            'topic', 'frequency', 'trend', 'change_rate', 'is_spike',
            'first_seen', 'last_seen'
        ])
        
        # 写入数据
        for topic in topics:
            writer.writerow([
                topic.topic,
                topic.frequency,
                topic.trend,
                round(topic.change_rate, 3),
                topic.is_spike,
                topic.first_seen.isoformat() if topic.first_seen else '',
                topic.last_seen.isoformat() if topic.last_seen else ''
            ])
        
        return output.getvalue()
    
    # =========================================================================
    # Summary
    # =========================================================================
    
    def get_dashboard_json(self) -> dict:
        """
        获取仪表板数据 JSON
        Get dashboard data JSON
        
        返回综合的统计摘要数据。
        Returns comprehensive statistics summary data.
        
        Returns:
            JSON 格式的仪表板数据
            Dashboard data in JSON format
        
        Requirements: 13.1
        """
        cache_key = "dashboard"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # 获取各项统计
        summary = self.store.get_stats_summary()
        qa_stats = self.aggregator.get_qa_stats(days=7)
        hot_articles = self.aggregator.get_hot_articles(days=7, limit=5)
        hot_queries = self.aggregator.get_hot_queries(days=7, limit=5)
        trending_topics = self.topic_tracker.get_trending_topics(days=7, limit=5)
        
        result = {
            'status': 'success',
            'data': {
                'summary': {
                    'total_page_views': summary['page_views'],
                    'total_qa_events': summary['qa_events'],
                    'total_source_fetches': summary['source_fetches']
                },
                'qa_stats_7d': {
                    'total_queries': qa_stats.total_queries,
                    'avg_relevance': round(qa_stats.avg_relevance_score, 3),
                    'positive_feedback_rate': round(qa_stats.positive_feedback_rate, 3)
                },
                'top_articles': [
                    {'article_id': a.article_id, 'view_count': a.view_count}
                    for a in hot_articles
                ],
                'top_queries': [
                    {'query': q.query, 'count': q.count}
                    for q in hot_queries
                ],
                'trending_topics': [
                    {'topic': t.topic, 'trend': t.trend, 'is_spike': t.is_spike}
                    for t in trending_topics
                ]
            },
            'generated_at': datetime.now().isoformat()
        }
        
        self.cache.set(cache_key, result)
        return result
    
    def invalidate_cache(self) -> None:
        """使所有缓存失效"""
        self.cache.clear()
        logger.info("Stats API cache cleared")
