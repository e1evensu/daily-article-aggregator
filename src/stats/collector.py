"""
统计收集器
Statistics Collector

收集和记录各类统计事件。
Collects and records various statistics events.

Requirements:
- 9.1: 页面浏览事件收集
- 9.5: 页面浏览去重
- 10.1: 问答事件收集
- 11.1: 来源抓取事件收集
"""

import logging
from datetime import datetime
from typing import Optional

from src.stats.models import (
    PageViewEvent,
    QAEvent,
    SourceFetchEvent,
)
from src.stats.store import StatsStore

logger = logging.getLogger(__name__)


class StatsCollector:
    """
    统计收集器
    Statistics Collector
    
    提供统一的接口收集各类统计事件，支持去重和批量操作。
    Provides a unified interface for collecting various statistics events,
    with support for deduplication and batch operations.
    
    Attributes:
        store: 统计数据存储
               Statistics data store
        dedup_window_minutes: 去重时间窗口（分钟）
                              Deduplication time window (minutes)
    
    Examples:
        >>> collector = StatsCollector()
        >>> collector.record_page_view('article_123', user_id='user_456')
        >>> collector.record_qa_event('什么是 RAG？', '...', relevance_score=0.85)
    
    Requirements: 9.1, 9.5, 10.1, 11.1
    """
    
    def __init__(
        self,
        store: StatsStore | None = None,
        db_path: str = 'data/stats.db',
        dedup_window_minutes: int = 30
    ):
        """
        初始化统计收集器
        Initialize Statistics Collector
        
        Args:
            store: 统计数据存储（可选，用于依赖注入）
                   Statistics data store (optional, for dependency injection)
            db_path: 数据库路径（当 store 为 None 时使用）
                     Database path (used when store is None)
            dedup_window_minutes: 去重时间窗口（分钟）
                                  Deduplication time window (minutes)
        """
        self.store = store or StatsStore(db_path)
        self.dedup_window_minutes = dedup_window_minutes
    
    def record_page_view(
        self,
        article_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        source: str = 'unknown',
        skip_dedup: bool = False
    ) -> bool:
        """
        记录页面浏览事件
        Record page view event
        
        支持基于用户/会话的去重，避免短时间内重复计数。
        Supports user/session-based deduplication to avoid duplicate counting
        within a short time window.
        
        Args:
            article_id: 文章 ID
                        Article ID
            user_id: 用户 ID（可选）
                     User ID (optional)
            session_id: 会话 ID（可选）
                        Session ID (optional)
            source: 来源（如 'web', 'api', 'feishu'）
                    Source (e.g., 'web', 'api', 'feishu')
            skip_dedup: 是否跳过去重检查
                        Whether to skip deduplication check
        
        Returns:
            True 如果成功记录，False 如果被去重跳过
            True if recorded successfully, False if skipped due to deduplication
        
        Examples:
            >>> collector.record_page_view('article_123', user_id='user_456')
            True
            >>> # 短时间内再次访问同一文章
            >>> collector.record_page_view('article_123', user_id='user_456')
            False  # 被去重跳过
        
        Requirements: 9.1, 9.5
        """
        # 去重检查
        if not skip_dedup:
            is_duplicate = self.store.check_duplicate_view(
                article_id=article_id,
                user_id=user_id,
                session_id=session_id,
                window_minutes=self.dedup_window_minutes
            )
            if is_duplicate:
                logger.debug(
                    f"Duplicate page view skipped: article={article_id}, "
                    f"user={user_id}, session={session_id}"
                )
                return False
        
        # 创建并存储事件
        event = PageViewEvent(
            article_id=article_id,
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.now(),
            source=source
        )
        
        try:
            self.store.insert_page_view(event)
            logger.debug(f"Page view recorded: article={article_id}, source={source}")
            return True
        except Exception as e:
            logger.error(f"Failed to record page view: {e}")
            return False
    
    def record_qa_event(
        self,
        query: str,
        answer: str = '',
        user_id: str | None = None,
        relevance_score: float = 0.0,
        sources_used: int = 0,
        response_time_ms: int = 0,
        feedback: str | None = None
    ) -> bool:
        """
        记录问答事件
        Record QA event
        
        Args:
            query: 用户查询
                   User query
            answer: 系统回答
                    System answer
            user_id: 用户 ID（可选）
                     User ID (optional)
            relevance_score: 相关性分数（0-1）
                             Relevance score (0-1)
            sources_used: 使用的来源数量
                          Number of sources used
            response_time_ms: 响应时间（毫秒）
                              Response time in milliseconds
            feedback: 用户反馈（可选）
                      User feedback (optional)
        
        Returns:
            True 如果成功记录
            True if recorded successfully
        
        Examples:
            >>> collector.record_qa_event(
            ...     query='什么是 RAG？',
            ...     answer='RAG 是检索增强生成...',
            ...     relevance_score=0.85,
            ...     sources_used=3,
            ...     response_time_ms=1200
            ... )
            True
        
        Requirements: 10.1
        """
        event = QAEvent(
            query=query,
            answer=answer,
            user_id=user_id,
            timestamp=datetime.now(),
            relevance_score=relevance_score,
            sources_used=sources_used,
            response_time_ms=response_time_ms,
            feedback=feedback
        )
        
        try:
            self.store.insert_qa_event(event)
            logger.debug(
                f"QA event recorded: query='{query[:50]}...', "
                f"relevance={relevance_score:.2f}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to record QA event: {e}")
            return False
    
    def record_source_fetch(
        self,
        source_type: str,
        source_url: str,
        success: bool = True,
        articles_count: int = 0,
        content_length: int = 0,
        response_time_ms: int = 0,
        error_message: str | None = None
    ) -> bool:
        """
        记录来源抓取事件
        Record source fetch event
        
        Args:
            source_type: 来源类型（如 'rss', 'arxiv', 'github'）
                         Source type (e.g., 'rss', 'arxiv', 'github')
            source_url: 来源 URL
                        Source URL
            success: 是否成功
                     Whether successful
            articles_count: 抓取的文章数量
                            Number of articles fetched
            content_length: 内容总长度（字符）
                            Total content length (characters)
            response_time_ms: 响应时间（毫秒）
                              Response time in milliseconds
            error_message: 错误信息（如果失败）
                           Error message (if failed)
        
        Returns:
            True 如果成功记录
            True if recorded successfully
        
        Examples:
            >>> collector.record_source_fetch(
            ...     source_type='rss',
            ...     source_url='https://example.com/feed.xml',
            ...     success=True,
            ...     articles_count=10,
            ...     content_length=50000,
            ...     response_time_ms=500
            ... )
            True
        
        Requirements: 11.1
        """
        event = SourceFetchEvent(
            source_type=source_type,
            source_url=source_url,
            timestamp=datetime.now(),
            success=success,
            articles_count=articles_count,
            content_length=content_length,
            response_time_ms=response_time_ms,
            error_message=error_message
        )
        
        try:
            self.store.insert_source_fetch(event)
            status = 'success' if success else 'failed'
            logger.debug(
                f"Source fetch recorded: type={source_type}, "
                f"url={source_url[:50]}..., status={status}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to record source fetch: {e}")
            return False
    
    def update_qa_feedback(
        self,
        query: str,
        timestamp: datetime,
        feedback: str
    ) -> bool:
        """
        更新问答反馈
        Update QA feedback
        
        Args:
            query: 查询文本
                   Query text
            timestamp: 问答时间戳
                       QA timestamp
            feedback: 反馈（'positive' 或 'negative'）
                      Feedback ('positive' or 'negative')
        
        Returns:
            是否更新成功
            Whether update was successful
        """
        if feedback not in ('positive', 'negative'):
            logger.warning(f"Invalid feedback value: {feedback}")
            return False
        
        try:
            return self.store.update_qa_feedback(query, timestamp, feedback)
        except Exception as e:
            logger.error(f"Failed to update QA feedback: {e}")
            return False
    
    def get_summary(self) -> dict:
        """
        获取统计摘要
        Get statistics summary
        
        Returns:
            统计摘要字典
            Statistics summary dictionary
        """
        return self.store.get_stats_summary()
