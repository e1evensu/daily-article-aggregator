"""
飞书反馈交互测试
"""

import os
import tempfile
import pytest

from src.feedback.feedback_handler import FeedbackHandler
from src.feedback.feishu_feedback import FeishuFeedbackHandler
from src.feedback.models import QuickRating


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def feishu_handler(temp_db):
    """创建飞书反馈处理器"""
    feedback_handler = FeedbackHandler(db_path=temp_db)
    return FeishuFeedbackHandler(feedback_handler)


class TestFeishuFeedbackHandler:
    """飞书反馈处理器测试"""
    
    def test_is_feedback_command_useful(self, feishu_handler):
        """测试识别有用命令"""
        assert feishu_handler.is_feedback_command('有用')
        assert feishu_handler.is_feedback_command('👍')
        assert feishu_handler.is_feedback_command('useful')
        assert feishu_handler.is_feedback_command('好')
    
    def test_is_feedback_command_not_useful(self, feishu_handler):
        """测试识别没用命令"""
        assert feishu_handler.is_feedback_command('没用')
        assert feishu_handler.is_feedback_command('👎')
        assert feishu_handler.is_feedback_command('not useful')
    
    def test_is_feedback_command_bookmark(self, feishu_handler):
        """测试识别收藏命令"""
        assert feishu_handler.is_feedback_command('收藏')
        assert feishu_handler.is_feedback_command('⭐')
        assert feishu_handler.is_feedback_command('bookmark')
    
    def test_is_feedback_command_more(self, feishu_handler):
        """测试识别更多类似命令"""
        assert feishu_handler.is_feedback_command('更多')
        assert feishu_handler.is_feedback_command('类似')
        assert feishu_handler.is_feedback_command('more')
    
    def test_is_feedback_command_profile(self, feishu_handler):
        """测试识别画像命令"""
        assert feishu_handler.is_feedback_command('我的画像')
        assert feishu_handler.is_feedback_command('用户画像')
        assert feishu_handler.is_feedback_command('my profile')
    
    def test_is_feedback_command_negative(self, feishu_handler):
        """测试非反馈命令"""
        assert not feishu_handler.is_feedback_command('你好')
        assert not feishu_handler.is_feedback_command('什么是AI')
        assert not feishu_handler.is_feedback_command('帮我查一下')
    
    def test_process_feedback_useful_with_context(self, feishu_handler):
        """测试处理有用反馈（有上下文）"""
        article_context = {
            'id': 'art_123',
            'title': 'Test Article',
            'topics': ['AI'],
        }
        
        response = feishu_handler.process_feedback(
            user_id='user_1',
            text='有用',
            article_context=article_context
        )
        
        assert '感谢反馈' in response or '✅' in response
    
    def test_process_feedback_useful_without_context(self, feishu_handler):
        """测试处理有用反馈（无上下文）"""
        response = feishu_handler.process_feedback(
            user_id='user_1',
            text='有用',
            article_context=None
        )
        
        assert '先查看' in response or '文章' in response
    
    def test_process_feedback_not_useful_triggers_followup(self, feishu_handler):
        """测试没用反馈触发追问"""
        article_context = {
            'id': 'art_456',
            'title': 'Bad Article',
            'topics': ['Spam'],
        }
        
        response = feishu_handler.process_feedback(
            user_id='user_2',
            text='没用',
            article_context=article_context
        )
        
        # 应该询问原因
        assert '哪里不好' in response or '太基础' in response or '📝' in response
        
        # 应该进入待处理状态
        assert 'user_2' in feishu_handler._pending_feedback
    
    def test_process_feedback_detailed_reason(self, feishu_handler):
        """测试详细反馈原因"""
        article_context = {
            'id': 'art_789',
            'title': 'Hard Article',
            'topics': ['Quantum'],
        }
        
        # 先触发没用反馈
        feishu_handler.process_feedback(
            user_id='user_3',
            text='没用',
            article_context=article_context
        )
        
        # 然后回复原因
        response = feishu_handler.process_feedback(
            user_id='user_3',
            text='太深了，看不懂',
            article_context=None
        )
        
        assert '基础' in response or '偏好已更新' in response
        
        # 应该清除待处理状态
        assert 'user_3' not in feishu_handler._pending_feedback
    
    def test_process_feedback_profile_empty(self, feishu_handler):
        """测试查看空画像"""
        response = feishu_handler.process_feedback(
            user_id='new_user',
            text='我的画像',
            article_context=None
        )
        
        assert '没有反馈记录' in response or '暂无' in response
    
    def test_process_feedback_profile_with_data(self, feishu_handler):
        """测试查看有数据的画像"""
        article_context = {
            'id': 'art_profile',
            'title': 'AI Article',
            'topics': ['AI', 'Security'],
        }
        
        # 先记录一些反馈
        feishu_handler.process_feedback('profile_user', '有用', article_context)
        
        # 查看画像
        response = feishu_handler.process_feedback(
            user_id='profile_user',
            text='我的画像',
            article_context=None
        )
        
        assert '画像' in response or 'AI' in response or '感兴趣' in response
    
    def test_process_feedback_stats(self, feishu_handler):
        """测试反馈统计"""
        # 先记录一些反馈
        ctx = {'id': 'stat_art', 'topics': ['Test']}
        feishu_handler.process_feedback('stat_user', '有用', ctx)
        feishu_handler.process_feedback('stat_user', '收藏', ctx)
        
        response = feishu_handler.process_feedback(
            user_id='stat_user',
            text='反馈统计',
            article_context=None
        )
        
        assert '统计' in response or '总' in response
    
    def test_build_feedback_card(self, feishu_handler):
        """测试构建反馈卡片"""
        article = {
            'id': 'card_art',
            'title': 'Test Article for Card',
            'summary': 'This is a test summary.',
        }
        
        card = feishu_handler.build_feedback_card(article)
        
        assert 'header' in card
        assert 'elements' in card
        assert card['header']['title']['content'] == 'Test Article for Card'
        
        # 检查按钮
        actions = None
        for elem in card['elements']:
            if elem.get('tag') == 'action':
                actions = elem.get('actions', [])
                break
        
        assert actions is not None
        assert len(actions) == 4  # 有用、没用、收藏、更多类似
    
    def test_parse_rating(self, feishu_handler):
        """测试评分解析"""
        assert feishu_handler._parse_rating('有用') == 'useful'
        assert feishu_handler._parse_rating('没用') == 'not_useful'
        assert feishu_handler._parse_rating('收藏') == 'bookmark'
        assert feishu_handler._parse_rating('更多') == 'more'
        assert feishu_handler._parse_rating('good') == 'useful'
        assert feishu_handler._parse_rating('bad') == 'not_useful'
