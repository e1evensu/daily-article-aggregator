"""
反馈处理器测试
"""

import os
import tempfile
import pytest
from datetime import datetime

from src.feedback.models import (
    QuickRating,
    NotMatchReason,
    FeedbackType,
)
from src.feedback.feedback_handler import FeedbackHandler


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def handler(temp_db):
    """创建反馈处理器"""
    return FeedbackHandler(db_path=temp_db)


class TestFeedbackHandler:
    """反馈处理器测试"""
    
    def test_init_creates_tables(self, handler):
        """测试初始化创建表"""
        conn = handler._get_connection()
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row['name'] for row in cursor.fetchall()}
        
        assert 'article_feedback' in tables
        assert 'feedback_insights' in tables
        assert 'topic_weights' in tables
        assert 'keyword_preferences' in tables
        assert 'user_profiles' in tables
        
        conn.close()
    
    def test_record_quick_feedback_useful(self, handler):
        """测试记录有用反馈"""
        article_info = {
            'id': 'article_123',
            'title': 'Test Article',
            'topics': ['AI', 'Security'],
            'keywords': ['llm', 'vulnerability'],
        }
        
        feedback = handler.record_quick_feedback(
            article_id='article_123',
            user_id='user_456',
            rating=QuickRating.USEFUL,
            article_info=article_info
        )
        
        assert feedback.feedback_id is not None
        assert feedback.article_id == 'article_123'
        assert feedback.user_id == 'user_456'
        assert feedback.quick_rating == QuickRating.USEFUL
        assert feedback.feedback_type == FeedbackType.QUICK
    
    def test_record_quick_feedback_not_useful(self, handler):
        """测试记录没用反馈"""
        feedback = handler.record_quick_feedback(
            article_id='article_123',
            user_id='user_456',
            rating=QuickRating.NOT_USEFUL,
            article_info={'topics': ['Kubernetes']}
        )
        
        assert feedback.quick_rating == QuickRating.NOT_USEFUL
    
    def test_record_detailed_feedback(self, handler):
        """测试记录详细反馈"""
        article_info = {
            'id': 'article_789',
            'title': 'Advanced Topic',
            'topics': ['Quantum Computing'],
        }
        
        feedback = handler.record_detailed_feedback(
            article_id='article_789',
            user_id='user_456',
            reason=NotMatchReason.TOO_ADVANCED,
            comment='内容太深了，看不懂',
            article_info=article_info
        )
        
        assert feedback.feedback_type == FeedbackType.DETAILED
        assert feedback.detailed_feedback is not None
        assert feedback.detailed_feedback.not_match_reason == NotMatchReason.TOO_ADVANCED
        assert feedback.detailed_feedback.comment == '内容太深了，看不懂'
    
    def test_topic_weight_adjustment_positive(self, handler):
        """测试正向反馈增加话题权重"""
        article_info = {'topics': ['AI', 'LLM']}
        
        # 记录有用反馈
        handler.record_quick_feedback(
            article_id='art1',
            user_id='user1',
            rating=QuickRating.USEFUL,
            article_info=article_info
        )
        
        weights = handler.get_topic_weights()
        
        # 权重应该增加
        assert 'AI' in weights
        assert weights['AI'] > 1.0
    
    def test_topic_weight_adjustment_negative(self, handler):
        """测试负向反馈降低话题权重"""
        article_info = {'topics': ['Boring Topic']}
        
        # 记录没用反馈
        handler.record_quick_feedback(
            article_id='art2',
            user_id='user1',
            rating=QuickRating.NOT_USEFUL,
            article_info=article_info
        )
        
        weights = handler.get_topic_weights()
        
        # 权重应该降低
        assert 'Boring Topic' in weights
        assert weights['Boring Topic'] < 1.0
    
    def test_user_profile_creation(self, handler):
        """测试用户画像创建"""
        article_info = {'topics': ['Security', 'AI']}
        
        handler.record_quick_feedback(
            article_id='art3',
            user_id='user_new',
            rating=QuickRating.USEFUL,
            article_info=article_info
        )
        
        profile = handler.get_user_profile('user_new')
        
        assert profile is not None
        assert 'Security' in profile.get('preferred_topics', [])
        assert 'AI' in profile.get('preferred_topics', [])
        assert profile.get('feedback_count', 0) == 1
    
    def test_user_profile_update_disliked(self, handler):
        """测试用户画像更新不喜欢的话题"""
        article_info = {'topics': ['Spam Topic']}
        
        handler.record_quick_feedback(
            article_id='art4',
            user_id='user_picky',
            rating=QuickRating.NOT_USEFUL,
            article_info=article_info
        )
        
        profile = handler.get_user_profile('user_picky')
        
        assert 'Spam Topic' in profile.get('disliked_topics', [])
    
    def test_feedback_stats(self, handler):
        """测试反馈统计"""
        user_id = 'stats_user'
        
        # 记录多个反馈
        handler.record_quick_feedback('a1', user_id, QuickRating.USEFUL, {})
        handler.record_quick_feedback('a2', user_id, QuickRating.USEFUL, {})
        handler.record_quick_feedback('a3', user_id, QuickRating.NOT_USEFUL, {})
        handler.record_quick_feedback('a4', user_id, QuickRating.BOOKMARK, {})
        
        stats = handler.get_feedback_stats(user_id)
        
        assert stats['total'] == 4
        assert stats['useful'] == 2
        assert stats['not_useful'] == 1
        assert stats['bookmarked'] == 1
    
    def test_feedback_stats_global(self, handler):
        """测试全局反馈统计"""
        handler.record_quick_feedback('a1', 'u1', QuickRating.USEFUL, {})
        handler.record_quick_feedback('a2', 'u2', QuickRating.USEFUL, {})
        handler.record_quick_feedback('a3', 'u1', QuickRating.NOT_USEFUL, {})
        
        stats = handler.get_feedback_stats()  # 不传 user_id
        
        assert stats['total'] == 3
        assert stats['useful'] == 2
        assert stats['not_useful'] == 1
    
    def test_difficulty_preference_too_basic(self, handler):
        """测试难度偏好 - 太基础"""
        handler.record_detailed_feedback(
            article_id='basic_art',
            user_id='advanced_user',
            reason=NotMatchReason.TOO_BASIC,
            article_info={'topics': ['Intro']}
        )
        
        profile = handler.get_user_profile('advanced_user')
        assert profile.get('preferred_difficulty') == 'advanced'
    
    def test_difficulty_preference_too_advanced(self, handler):
        """测试难度偏好 - 太深"""
        handler.record_detailed_feedback(
            article_id='hard_art',
            user_id='beginner_user',
            reason=NotMatchReason.TOO_ADVANCED,
            article_info={'topics': ['Advanced']}
        )
        
        profile = handler.get_user_profile('beginner_user')
        assert profile.get('preferred_difficulty') == 'basic'
