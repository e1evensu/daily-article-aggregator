"""
统计数据存储
Statistics Data Store

使用 SQLite 作为后端存储统计数据。
Uses SQLite as backend for storing statistics data.

Requirements:
- 9.1: 页面浏览事件存储
- 10.1: 问答事件存储
- 11.1: 来源抓取事件存储
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from src.stats.models import (
    PageViewEvent,
    QAEvent,
    SourceFetchEvent,
)

logger = logging.getLogger(__name__)


# 数据库 Schema
SCHEMA = """
-- 页面浏览事件表
CREATE TABLE IF NOT EXISTS page_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id TEXT NOT NULL,
    user_id TEXT,
    session_id TEXT,
    timestamp DATETIME NOT NULL,
    source TEXT DEFAULT 'unknown',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 页面浏览索引
CREATE INDEX IF NOT EXISTS idx_page_views_article_id ON page_views(article_id);
CREATE INDEX IF NOT EXISTS idx_page_views_timestamp ON page_views(timestamp);
CREATE INDEX IF NOT EXISTS idx_page_views_user_id ON page_views(user_id);

-- 问答事件表
CREATE TABLE IF NOT EXISTS qa_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    answer TEXT,
    user_id TEXT,
    timestamp DATETIME NOT NULL,
    relevance_score REAL DEFAULT 0.0,
    sources_used INTEGER DEFAULT 0,
    response_time_ms INTEGER DEFAULT 0,
    feedback TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 问答事件索引
CREATE INDEX IF NOT EXISTS idx_qa_events_timestamp ON qa_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_qa_events_user_id ON qa_events(user_id);
CREATE INDEX IF NOT EXISTS idx_qa_events_query ON qa_events(query);

-- 来源抓取事件表
CREATE TABLE IF NOT EXISTS source_fetches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    success INTEGER DEFAULT 1,
    articles_count INTEGER DEFAULT 0,
    content_length INTEGER DEFAULT 0,
    response_time_ms INTEGER DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 来源抓取索引
CREATE INDEX IF NOT EXISTS idx_source_fetches_source_type ON source_fetches(source_type);
CREATE INDEX IF NOT EXISTS idx_source_fetches_timestamp ON source_fetches(timestamp);
CREATE INDEX IF NOT EXISTS idx_source_fetches_source_url ON source_fetches(source_url);

-- 话题频率表（用于缓存聚合结果）
CREATE TABLE IF NOT EXISTS topic_frequencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    frequency INTEGER DEFAULT 0,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    trend TEXT DEFAULT 'stable',
    change_rate REAL DEFAULT 0.0,
    is_spike INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic, period_start, period_end)
);

-- 话题频率索引
CREATE INDEX IF NOT EXISTS idx_topic_frequencies_topic ON topic_frequencies(topic);
CREATE INDEX IF NOT EXISTS idx_topic_frequencies_period ON topic_frequencies(period_start, period_end);
"""


class StatsStore:
    """
    统计数据存储
    Statistics Data Store
    
    使用 SQLite 存储和查询统计数据。
    Uses SQLite to store and query statistics data.
    
    Attributes:
        db_path: 数据库文件路径
                 Database file path
    
    Examples:
        >>> store = StatsStore('data/stats.db')
        >>> store.insert_page_view(PageViewEvent(article_id='123'))
        >>> views = store.get_page_views(article_id='123')
    
    Requirements: 9.1, 10.1, 11.1
    """
    
    def __init__(self, db_path: str = 'data/stats.db'):
        """
        初始化统计存储
        Initialize Statistics Store
        
        Args:
            db_path: 数据库文件路径
                     Database file path
        """
        self.db_path = db_path
        self._ensure_directory()
        self._init_database()
    
    def _ensure_directory(self) -> None:
        """确保数据库目录存在"""
        dir_path = os.path.dirname(self.db_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
    
    def _init_database(self) -> None:
        """初始化数据库 schema"""
        with self._get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()
        logger.info(f"Stats database initialized: {self.db_path}")
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        获取数据库连接
        Get database connection
        
        Yields:
            SQLite 连接对象
            SQLite connection object
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    # =========================================================================
    # Page View Operations
    # =========================================================================
    
    def insert_page_view(self, event: PageViewEvent) -> int:
        """
        插入页面浏览事件
        Insert page view event
        
        Args:
            event: 页面浏览事件
                   Page view event
        
        Returns:
            插入的记录 ID
            Inserted record ID
        
        Requirements: 9.1
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO page_views (article_id, user_id, session_id, timestamp, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.article_id,
                    event.user_id,
                    event.session_id,
                    event.timestamp.isoformat(),
                    event.source
                )
            )
            conn.commit()
            return cursor.lastrowid or 0
    
    def get_page_views(
        self,
        article_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000
    ) -> list[PageViewEvent]:
        """
        查询页面浏览事件
        Query page view events
        
        Args:
            article_id: 文章 ID（可选）
                        Article ID (optional)
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
            limit: 最大返回数量
                   Maximum return count
        
        Returns:
            页面浏览事件列表
            List of page view events
        
        Requirements: 9.1
        """
        query = "SELECT * FROM page_views WHERE 1=1"
        params: list = []
        
        if article_id:
            query += " AND article_id = ?"
            params.append(article_id)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
        
        return [
            PageViewEvent(
                article_id=row['article_id'],
                user_id=row['user_id'],
                session_id=row['session_id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                source=row['source']
            )
            for row in rows
        ]
    
    def get_page_view_counts(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100
    ) -> list[tuple[str, int, int]]:
        """
        获取页面浏览计数（按文章聚合）
        Get page view counts (aggregated by article)
        
        Args:
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
            limit: 最大返回数量
                   Maximum return count
        
        Returns:
            (article_id, view_count, unique_viewers) 元组列表
            List of (article_id, view_count, unique_viewers) tuples
        
        Requirements: 9.2, 9.3
        """
        query = """
            SELECT 
                article_id,
                COUNT(*) as view_count,
                COUNT(DISTINCT COALESCE(user_id, session_id, id)) as unique_viewers
            FROM page_views
            WHERE 1=1
        """
        params: list = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " GROUP BY article_id ORDER BY view_count DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [(row['article_id'], row['view_count'], row['unique_viewers']) 
                    for row in cursor.fetchall()]
    
    def check_duplicate_view(
        self,
        article_id: str,
        user_id: str | None,
        session_id: str | None,
        window_minutes: int = 30
    ) -> bool:
        """
        检查是否为重复浏览
        Check if it's a duplicate view
        
        Args:
            article_id: 文章 ID
                        Article ID
            user_id: 用户 ID
                     User ID
            session_id: 会话 ID
                        Session ID
            window_minutes: 去重时间窗口（分钟）
                            Deduplication time window (minutes)
        
        Returns:
            True 如果是重复浏览
            True if it's a duplicate view
        
        Requirements: 9.5
        """
        if not user_id and not session_id:
            return False
        
        query = """
            SELECT COUNT(*) as count FROM page_views
            WHERE article_id = ?
            AND timestamp >= datetime('now', ?)
        """
        params: list = [article_id, f'-{window_minutes} minutes']
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        elif session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return row['count'] > 0 if row else False
    
    # =========================================================================
    # QA Event Operations
    # =========================================================================
    
    def insert_qa_event(self, event: QAEvent) -> int:
        """
        插入问答事件
        Insert QA event
        
        Args:
            event: 问答事件
                   QA event
        
        Returns:
            插入的记录 ID
            Inserted record ID
        
        Requirements: 10.1
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO qa_events 
                (query, answer, user_id, timestamp, relevance_score, 
                 sources_used, response_time_ms, feedback)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.query,
                    event.answer,
                    event.user_id,
                    event.timestamp.isoformat(),
                    event.relevance_score,
                    event.sources_used,
                    event.response_time_ms,
                    event.feedback
                )
            )
            conn.commit()
            return cursor.lastrowid or 0
    
    def get_qa_events(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        user_id: str | None = None,
        limit: int = 1000
    ) -> list[QAEvent]:
        """
        查询问答事件
        Query QA events
        
        Args:
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
            user_id: 用户 ID（可选）
                     User ID (optional)
            limit: 最大返回数量
                   Maximum return count
        
        Returns:
            问答事件列表
            List of QA events
        
        Requirements: 10.1
        """
        query = "SELECT * FROM qa_events WHERE 1=1"
        params: list = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
        
        return [
            QAEvent(
                query=row['query'],
                answer=row['answer'] or '',
                user_id=row['user_id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                relevance_score=row['relevance_score'],
                sources_used=row['sources_used'],
                response_time_ms=row['response_time_ms'],
                feedback=row['feedback']
            )
            for row in rows
        ]
    
    def get_hot_queries(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 20
    ) -> list[tuple[str, int, float]]:
        """
        获取热门查询
        Get hot queries
        
        Args:
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
            limit: 最大返回数量
                   Maximum return count
        
        Returns:
            (query, count, avg_relevance) 元组列表
            List of (query, count, avg_relevance) tuples
        
        Requirements: 10.2, 10.3
        """
        query = """
            SELECT 
                query,
                COUNT(*) as count,
                AVG(relevance_score) as avg_relevance
            FROM qa_events
            WHERE 1=1
        """
        params: list = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " GROUP BY query ORDER BY count DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [(row['query'], row['count'], row['avg_relevance']) 
                    for row in cursor.fetchall()]
    
    def update_qa_feedback(self, query: str, timestamp: datetime, feedback: str) -> bool:
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
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE qa_events SET feedback = ?
                WHERE query = ? AND timestamp = ?
                """,
                (feedback, query, timestamp.isoformat())
            )
            conn.commit()
            return cursor.rowcount > 0
    
    # =========================================================================
    # Source Fetch Operations
    # =========================================================================
    
    def insert_source_fetch(self, event: SourceFetchEvent) -> int:
        """
        插入来源抓取事件
        Insert source fetch event
        
        Args:
            event: 来源抓取事件
                   Source fetch event
        
        Returns:
            插入的记录 ID
            Inserted record ID
        
        Requirements: 11.1
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO source_fetches 
                (source_type, source_url, timestamp, success, articles_count,
                 content_length, response_time_ms, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.source_type,
                    event.source_url,
                    event.timestamp.isoformat(),
                    1 if event.success else 0,
                    event.articles_count,
                    event.content_length,
                    event.response_time_ms,
                    event.error_message
                )
            )
            conn.commit()
            return cursor.lastrowid or 0
    
    def get_source_fetches(
        self,
        source_type: str | None = None,
        source_url: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000
    ) -> list[SourceFetchEvent]:
        """
        查询来源抓取事件
        Query source fetch events
        
        Args:
            source_type: 来源类型（可选）
                         Source type (optional)
            source_url: 来源 URL（可选）
                        Source URL (optional)
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
            limit: 最大返回数量
                   Maximum return count
        
        Returns:
            来源抓取事件列表
            List of source fetch events
        
        Requirements: 11.1
        """
        query = "SELECT * FROM source_fetches WHERE 1=1"
        params: list = []
        
        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)
        
        if source_url:
            query += " AND source_url = ?"
            params.append(source_url)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
        
        return [
            SourceFetchEvent(
                source_type=row['source_type'],
                source_url=row['source_url'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                success=bool(row['success']),
                articles_count=row['articles_count'],
                content_length=row['content_length'],
                response_time_ms=row['response_time_ms'],
                error_message=row['error_message']
            )
            for row in rows
        ]
    
    def get_source_quality_stats(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[dict]:
        """
        获取来源质量统计
        Get source quality statistics
        
        Args:
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
        
        Returns:
            来源质量统计列表
            List of source quality statistics
        
        Requirements: 11.1, 11.2, 11.3
        """
        query = """
            SELECT 
                source_type,
                COUNT(*) as total_fetches,
                SUM(success) as successful_fetches,
                AVG(CASE WHEN success = 1 THEN articles_count ELSE 0 END) as avg_articles,
                AVG(CASE WHEN success = 1 THEN content_length ELSE 0 END) as avg_content_length,
                AVG(response_time_ms) as avg_response_time,
                MAX(timestamp) as last_fetch
            FROM source_fetches
            WHERE 1=1
        """
        params: list = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " GROUP BY source_type ORDER BY total_fetches DESC"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_stats_summary(self) -> dict:
        """
        获取统计摘要
        Get statistics summary
        
        Returns:
            统计摘要字典
            Statistics summary dictionary
        """
        with self._get_connection() as conn:
            page_views = conn.execute(
                "SELECT COUNT(*) as count FROM page_views"
            ).fetchone()['count']
            
            qa_events = conn.execute(
                "SELECT COUNT(*) as count FROM qa_events"
            ).fetchone()['count']
            
            source_fetches = conn.execute(
                "SELECT COUNT(*) as count FROM source_fetches"
            ).fetchone()['count']
        
        return {
            'page_views': page_views,
            'qa_events': qa_events,
            'source_fetches': source_fetches,
            'db_path': self.db_path
        }
    
    def clear_old_data(self, days: int = 90) -> dict:
        """
        清理旧数据
        Clear old data
        
        Args:
            days: 保留天数
                  Days to keep
        
        Returns:
            删除的记录数
            Number of deleted records
        """
        cutoff = f'-{days} days'
        deleted = {}
        
        with self._get_connection() as conn:
            for table in ['page_views', 'qa_events', 'source_fetches']:
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE timestamp < datetime('now', ?)",
                    (cutoff,)
                )
                deleted[table] = cursor.rowcount
            conn.commit()
        
        logger.info(f"Cleared old stats data: {deleted}")
        return deleted
