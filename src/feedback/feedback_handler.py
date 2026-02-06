"""
反馈处理器

处理用户反馈，存储到数据库，并更新偏好权重。
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Optional

from .models import (
    ArticleFeedback,
    DetailedFeedback,
    FeedbackInsight,
    FeedbackType,
    NotMatchReason,
    QuickRating,
)

logger = logging.getLogger(__name__)


class FeedbackHandler:
    """
    反馈处理器
    
    处理用户对文章的反馈，存储反馈记录，并更新推荐偏好。
    """
    
    def __init__(self, db_path: str = "data/articles.db"):
        self.db_path = db_path
        self._ensure_tables()
        logger.info(f"FeedbackHandler initialized: db_path={db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_tables(self) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS article_feedback (
                    id TEXT PRIMARY KEY,
                    article_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    quick_rating TEXT,
                    not_match_reason TEXT,
                    comment TEXT,
                    relevance_score INTEGER,
                    difficulty_score INTEGER,
                    quality_score INTEGER,
                    conversation_log TEXT,
                    ai_analysis_snapshot TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    insight_type TEXT NOT NULL,
                    insight_key TEXT NOT NULL,
                    insight_value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 1,
                    first_seen TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(insight_type, insight_key)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topic_weights (
                    topic TEXT PRIMARY KEY,
                    base_weight REAL DEFAULT 1.0,
                    adjusted_weight REAL DEFAULT 1.0,
                    adjustment_reason TEXT,
                    feedback_count INTEGER DEFAULT 0,
                    last_adjusted TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_preferences (
                    keyword TEXT PRIMARY KEY,
                    preference_type TEXT NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    first_seen TIMESTAMP,
                    last_seen TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    preferred_topics TEXT,
                    disliked_topics TEXT,
                    preferred_difficulty TEXT,
                    preferred_sources TEXT,
                    feedback_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
        finally:
            conn.close()
    
    def record_quick_feedback(
        self,
        article_id: str,
        user_id: str,
        rating: QuickRating,
        article_info: Optional[dict] = None
    ) -> ArticleFeedback:
        feedback = ArticleFeedback(
            feedback_id=str(uuid.uuid4()),
            article_id=article_id,
            user_id=user_id,
            feedback_type=FeedbackType.QUICK,
            quick_rating=rating,
            ai_analysis_snapshot=article_info or {},
        )
        
        self._save_feedback(feedback)
        self._update_weights_from_quick_feedback(feedback, article_info)
        self._update_user_profile(user_id, feedback, article_info)
        
        logger.info(f"Quick feedback recorded: article={article_id[:8]}..., rating={rating.value}")
        return feedback
    
    def record_detailed_feedback(
        self,
        article_id: str,
        user_id: str,
        reason: NotMatchReason,
        comment: Optional[str] = None,
        article_info: Optional[dict] = None
    ) -> ArticleFeedback:
        detailed = DetailedFeedback(
            not_match_reason=reason,
            comment=comment,
        )
        
        feedback = ArticleFeedback(
            feedback_id=str(uuid.uuid4()),
            article_id=article_id,
            user_id=user_id,
            feedback_type=FeedbackType.DETAILED,
            quick_rating=QuickRating.NOT_USEFUL,
            detailed_feedback=detailed,
            ai_analysis_snapshot=article_info or {},
        )
        
        self._save_feedback(feedback)
        self._update_weights_from_detailed_feedback(feedback, article_info)
        self._update_user_profile(user_id, feedback, article_info)
        
        logger.info(f"Detailed feedback recorded: article={article_id[:8]}..., reason={reason.value}")
        return feedback
    
    def _save_feedback(self, feedback: ArticleFeedback) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO article_feedback (
                    id, article_id, user_id, feedback_type, quick_rating,
                    not_match_reason, comment, relevance_score, difficulty_score,
                    quality_score, conversation_log, ai_analysis_snapshot, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                feedback.feedback_id,
                feedback.article_id,
                feedback.user_id,
                feedback.feedback_type.value,
                feedback.quick_rating.value if feedback.quick_rating else None,
                feedback.detailed_feedback.not_match_reason.value if feedback.detailed_feedback and feedback.detailed_feedback.not_match_reason else None,
                feedback.detailed_feedback.comment if feedback.detailed_feedback else None,
                feedback.detailed_feedback.relevance_score if feedback.detailed_feedback else None,
                feedback.detailed_feedback.difficulty_score if feedback.detailed_feedback else None,
                feedback.detailed_feedback.quality_score if feedback.detailed_feedback else None,
                json.dumps(feedback.conversation_log),
                json.dumps(feedback.ai_analysis_snapshot),
                feedback.created_at.isoformat(),
            ))
            conn.commit()
        finally:
            conn.close()
    
    def _update_weights_from_quick_feedback(self, feedback: ArticleFeedback, article_info: Optional[dict]) -> None:
        if not article_info:
            return
        
        topics = article_info.get('topics', []) or article_info.get('category', '').split(',')
        keywords = article_info.get('keywords', [])
        
        if feedback.quick_rating == QuickRating.USEFUL:
            self._adjust_topic_weights(topics, 0.1)
            self._adjust_keyword_preferences(keywords, 'positive')
        elif feedback.quick_rating == QuickRating.NOT_USEFUL:
            self._adjust_topic_weights(topics, -0.1)
            self._adjust_keyword_preferences(keywords, 'negative')
        elif feedback.quick_rating == QuickRating.MORE_LIKE_THIS:
            self._adjust_topic_weights(topics, 0.2)
            self._adjust_keyword_preferences(keywords, 'strong_positive')
        elif feedback.quick_rating == QuickRating.BOOKMARK:
            self._adjust_topic_weights(topics, 0.15)
    
    def _update_weights_from_detailed_feedback(self, feedback: ArticleFeedback, article_info: Optional[dict]) -> None:
        if not article_info or not feedback.detailed_feedback:
            return
        
        topics = article_info.get('topics', []) or article_info.get('category', '').split(',')
        reason = feedback.detailed_feedback.not_match_reason
        
        if reason == NotMatchReason.NOT_INTERESTED:
            self._adjust_topic_weights(topics, -0.3)
        elif reason == NotMatchReason.TOO_BASIC:
            self._record_difficulty_preference(feedback.user_id, 'advanced')
        elif reason == NotMatchReason.TOO_ADVANCED:
            self._record_difficulty_preference(feedback.user_id, 'basic')
        elif reason == NotMatchReason.LOW_QUALITY:
            source = article_info.get('source', '')
            if source:
                self._adjust_source_weight(source, -0.2)
    
    def _adjust_topic_weights(self, topics: list, adjustment: float) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for topic in topics:
                topic = topic.strip()
                if not topic:
                    continue
                cursor.execute("""
                    INSERT INTO topic_weights (topic, adjusted_weight, feedback_count, last_adjusted)
                    VALUES (?, 1.0 + ?, 1, ?)
                    ON CONFLICT(topic) DO UPDATE SET
                        adjusted_weight = MIN(2.0, MAX(0.1, adjusted_weight + ?)),
                        feedback_count = feedback_count + 1,
                        last_adjusted = ?
                """, (topic, adjustment, datetime.now(), adjustment, datetime.now()))
            conn.commit()
        finally:
            conn.close()
    
    def _adjust_keyword_preferences(self, keywords: list, preference_type: str) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for keyword in keywords:
                keyword = keyword.strip().lower()
                if not keyword:
                    continue
                cursor.execute("""
                    INSERT INTO keyword_preferences (keyword, preference_type, first_seen, last_seen)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(keyword) DO UPDATE SET
                        preference_type = ?,
                        last_seen = ?
                """, (keyword, preference_type, datetime.now(), datetime.now(), preference_type, datetime.now()))
            conn.commit()
        finally:
            conn.close()
    
    def _record_difficulty_preference(self, user_id: str, difficulty: str) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_profiles (user_id, preferred_difficulty, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_difficulty = ?,
                    updated_at = ?
            """, (user_id, difficulty, datetime.now(), difficulty, datetime.now()))
            conn.commit()
        finally:
            conn.close()
    
    def _adjust_source_weight(self, source: str, adjustment: float) -> None:
        self._update_insight('source', source, 'weight_adjustment', adjustment)
    
    def _update_insight(self, insight_type: str, insight_key: str, insight_value: str, confidence: float = 0.5) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO feedback_insights (insight_type, insight_key, insight_value, confidence, first_seen, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(insight_type, insight_key) DO UPDATE SET
                    insight_value = ?,
                    confidence = MIN(1.0, confidence + 0.1),
                    evidence_count = evidence_count + 1,
                    last_updated = ?
            """, (insight_type, insight_key, str(insight_value), confidence, datetime.now(), datetime.now(), str(insight_value), datetime.now()))
            conn.commit()
        finally:
            conn.close()
    
    def _update_user_profile(self, user_id: str, feedback: ArticleFeedback, article_info: Optional[dict]) -> None:
        if not article_info:
            return
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            preferred_topics = json.loads(row['preferred_topics']) if row and row['preferred_topics'] else []
            disliked_topics = json.loads(row['disliked_topics']) if row and row['disliked_topics'] else []
            
            topics = article_info.get('topics', []) or article_info.get('category', '').split(',')
            topics = [t.strip() for t in topics if t.strip()]
            
            if feedback.quick_rating in [QuickRating.USEFUL, QuickRating.MORE_LIKE_THIS, QuickRating.BOOKMARK]:
                for topic in topics:
                    if topic not in preferred_topics:
                        preferred_topics.append(topic)
                    if topic in disliked_topics:
                        disliked_topics.remove(topic)
            elif feedback.quick_rating == QuickRating.NOT_USEFUL:
                for topic in topics:
                    if topic not in disliked_topics:
                        disliked_topics.append(topic)
            
            cursor.execute("""
                INSERT INTO user_profiles (user_id, preferred_topics, disliked_topics, feedback_count, updated_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_topics = ?,
                    disliked_topics = ?,
                    feedback_count = feedback_count + 1,
                    updated_at = ?
            """, (
                user_id,
                json.dumps(preferred_topics),
                json.dumps(disliked_topics),
                datetime.now(),
                json.dumps(preferred_topics),
                json.dumps(disliked_topics),
                datetime.now()
            ))
            conn.commit()
        finally:
            conn.close()
    
    def get_user_profile(self, user_id: str) -> dict:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'user_id': row['user_id'],
                    'preferred_topics': json.loads(row['preferred_topics']) if row['preferred_topics'] else [],
                    'disliked_topics': json.loads(row['disliked_topics']) if row['disliked_topics'] else [],
                    'preferred_difficulty': row['preferred_difficulty'],
                    'preferred_sources': json.loads(row['preferred_sources']) if row['preferred_sources'] else [],
                    'feedback_count': row['feedback_count'],
                }
            return {}
        finally:
            conn.close()
    
    def get_topic_weights(self) -> dict:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT topic, adjusted_weight FROM topic_weights")
            return {row['topic']: row['adjusted_weight'] for row in cursor.fetchall()}
        finally:
            conn.close()
    
    def get_feedback_stats(self, user_id: Optional[str] = None) -> dict:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN quick_rating = 'useful' THEN 1 ELSE 0 END) as useful,
                        SUM(CASE WHEN quick_rating = 'not_useful' THEN 1 ELSE 0 END) as not_useful,
                        SUM(CASE WHEN quick_rating = 'bookmark' THEN 1 ELSE 0 END) as bookmarked
                    FROM article_feedback WHERE user_id = ?
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN quick_rating = 'useful' THEN 1 ELSE 0 END) as useful,
                        SUM(CASE WHEN quick_rating = 'not_useful' THEN 1 ELSE 0 END) as not_useful,
                        SUM(CASE WHEN quick_rating = 'bookmark' THEN 1 ELSE 0 END) as bookmarked
                    FROM article_feedback
                """)
            
            row = cursor.fetchone()
            return {
                'total': row['total'] or 0,
                'useful': row['useful'] or 0,
                'not_useful': row['not_useful'] or 0,
                'bookmarked': row['bookmarked'] or 0,
            }
        finally:
            conn.close()
