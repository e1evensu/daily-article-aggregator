"""
飞书反馈交互模块

在飞书中实现人工反馈功能，支持：
- 快速反馈按钮（有用/没用/收藏/更多类似）
- 对话式详细反馈
- 用户画像查询
"""

import json
import logging
import re
from typing import Any, Optional

from .models import QuickRating, NotMatchReason
from .feedback_handler import FeedbackHandler

logger = logging.getLogger(__name__)


class FeishuFeedbackHandler:
    """
    飞书反馈交互处理器
    
    处理来自飞书的反馈消息和交互卡片回调。
    """
    
    # 反馈命令模式
    FEEDBACK_PATTERNS = {
        'useful': re.compile(r'^(有用|👍|useful|好|不错)\s*$', re.IGNORECASE),
        'not_useful': re.compile(r'^(没用|👎|not useful|不好|差)\s*$', re.IGNORECASE),
        'bookmark': re.compile(r'^(收藏|⭐|bookmark|mark)\s*$', re.IGNORECASE),
        'more': re.compile(r'^(更多|more|类似|similar)\s*$', re.IGNORECASE),
    }
    
    # 详细反馈原因模式
    REASON_PATTERNS = {
        'too_basic': re.compile(r'(太基础|太简单|too basic|too simple)', re.IGNORECASE),
        'too_advanced': re.compile(r'(太深|太难|too advanced|too hard)', re.IGNORECASE),
        'not_interested': re.compile(r'(不感兴趣|不关心|not interested)', re.IGNORECASE),
        'low_quality': re.compile(r'(质量差|质量不高|low quality|poor)', re.IGNORECASE),
    }
    
    def __init__(self, feedback_handler: FeedbackHandler, feishu_bitable=None):
        """
        初始化

        Args:
            feedback_handler: 反馈处理器实例
            feishu_bitable: 飞书多维表格实例（可选，用于同步用户反馈）
        """
        self.feedback_handler = feedback_handler
        self.feishu_bitable = feishu_bitable
        self._pending_feedback: dict[str, dict] = {}  # user_id -> pending feedback context
        logger.info("FeishuFeedbackHandler initialized")
    
    def is_feedback_command(self, text: str) -> bool:
        """检查是否是反馈命令"""
        text = text.strip()
        
        # 检查快速反馈命令
        for pattern in self.FEEDBACK_PATTERNS.values():
            if pattern.match(text):
                return True
        
        # 检查是否是对文章的反馈（格式：反馈 文章ID 评价）
        if text.startswith('反馈') or text.startswith('feedback'):
            return True
        
        # 检查是否是查看画像命令
        if text in ['我的画像', '用户画像', 'my profile', 'profile']:
            return True
        
        return False
    
    def process_feedback(
        self,
        user_id: str,
        text: str,
        article_context: Optional[dict] = None
    ) -> str:
        """
        处理反馈消息
        
        Args:
            user_id: 用户 ID
            text: 消息文本
            article_context: 文章上下文（如果有）
        
        Returns:
            回复消息
        """
        text = text.strip()
        
        # 查看用户画像
        if text in ['我的画像', '用户画像', 'my profile', 'profile']:
            return self._get_profile_response(user_id)
        
        # 查看反馈统计
        if text in ['反馈统计', 'feedback stats', 'stats']:
            return self._get_stats_response(user_id)
        
        # 处理快速反馈
        for rating_name, pattern in self.FEEDBACK_PATTERNS.items():
            if pattern.match(text):
                return self._process_quick_feedback(user_id, rating_name, article_context)
        
        # 处理详细反馈命令
        if text.startswith('反馈') or text.startswith('feedback'):
            return self._process_detailed_feedback_command(user_id, text, article_context)
        
        # 检查是否在等待详细反馈
        if user_id in self._pending_feedback:
            return self._continue_detailed_feedback(user_id, text)
        
        return "抱歉，我没有理解您的反馈。您可以使用以下命令：\n" \
               "- 有用/没用/收藏/更多 - 快速反馈\n" \
               "- 我的画像 - 查看您的偏好画像\n" \
               "- 反馈统计 - 查看反馈统计"

    def _sync_feedback_to_bitable(self, article_context: dict, rating_name: str) -> None:
        """同步用户反馈到飞书多维表格"""
        if not self.feishu_bitable:
            return

        try:
            article_url = article_context.get('url', '')
            if not article_url:
                return

            # 映射反馈类型到显示文本
            rating_text_map = {
                'useful': '👍 有用',
                'not_useful': '👎 没用',
                'bookmark': '⭐ 收藏',
                'more': '🔍 更多类似',
            }
            rating_text = rating_text_map.get(rating_name, rating_name)

            # 构建更新数据
            update_data = {
                'url': article_url,
                'user_feedback': rating_text,
            }

            # 查找并更新记录
            record_id = self.feishu_bitable.search_by_url(article_url)
            if record_id:
                self.feishu_bitable.update_record(record_id, update_data)
                logger.info(f"已同步用户反馈到多维表格: {article_url} -> {rating_text}")
            else:
                logger.warning(f"未找到文章记录，无法同步反馈: {article_url}")

        except Exception as e:
            logger.error(f"同步反馈到多维表格失败: {e}")

    def _process_quick_feedback(
        self,
        user_id: str,
        rating_name: str,
        article_context: Optional[dict]
    ) -> str:
        """处理快速反馈"""
        rating_map = {
            'useful': QuickRating.USEFUL,
            'not_useful': QuickRating.NOT_USEFUL,
            'bookmark': QuickRating.BOOKMARK,
            'more': QuickRating.MORE_LIKE_THIS,
        }
        
        rating = rating_map.get(rating_name)
        if not rating:
            return "无效的反馈类型"
        
        # 如果没有文章上下文，提示用户
        if not article_context:
            return "请先查看一篇文章，然后再进行反馈。\n" \
                   "或者使用格式：反馈 [文章链接] [评价]"
        
        try:
            article_id = article_context.get('id', article_context.get('url', ''))
            self.feedback_handler.record_quick_feedback(
                article_id=article_id,
                user_id=user_id,
                rating=rating,
                article_info=article_context
            )

            # 同步到飞书多维表格
            self._sync_feedback_to_bitable(article_context, rating_name)

            response_map = {
                'useful': "✅ 感谢反馈！我会推荐更多类似的内容。",
                'not_useful': "📝 收到反馈。您觉得哪里不好？\n回复：太基础/太深/不感兴趣/质量差",
                'bookmark': "⭐ 已收藏！这篇文章会被标记为重要内容。",
                'more': "🔍 明白了！我会寻找更多类似的内容推荐给您。",
            }
            
            # 如果是负面反馈，进入详细反馈流程
            if rating_name == 'not_useful':
                self._pending_feedback[user_id] = {
                    'article_context': article_context,
                    'stage': 'reason',
                }
            
            return response_map.get(rating_name, "感谢您的反馈！")
            
        except Exception as e:
            logger.error(f"Error recording quick feedback: {e}")
            return "记录反馈时出错，请稍后重试。"
    
    def _continue_detailed_feedback(self, user_id: str, text: str) -> str:
        """继续详细反馈流程"""
        pending = self._pending_feedback.get(user_id)
        if not pending:
            return "没有待处理的反馈。"
        
        stage = pending.get('stage', '')
        article_context = pending.get('article_context', {})
        
        if stage == 'reason':
            # 解析原因
            reason = None
            for reason_name, pattern in self.REASON_PATTERNS.items():
                if pattern.search(text):
                    reason = NotMatchReason[reason_name.upper()]
                    break
            
            if not reason:
                reason = NotMatchReason.OTHER
            
            try:
                article_id = article_context.get('id', article_context.get('url', ''))
                self.feedback_handler.record_detailed_feedback(
                    article_id=article_id,
                    user_id=user_id,
                    reason=reason,
                    comment=text,
                    article_info=article_context
                )
                
                # 清除待处理状态
                del self._pending_feedback[user_id]
                
                reason_responses = {
                    NotMatchReason.TOO_BASIC: "明白了，我会推荐更深入的内容。",
                    NotMatchReason.TOO_ADVANCED: "了解，我会推荐更基础的内容。",
                    NotMatchReason.NOT_INTERESTED: "好的，我会减少这类话题的推荐。",
                    NotMatchReason.LOW_QUALITY: "感谢反馈，我会降低该来源的权重。",
                    NotMatchReason.OTHER: "感谢您的详细反馈！",
                }
                
                return f"📝 {reason_responses.get(reason, '感谢反馈！')}\n您的偏好已更新。"
                
            except Exception as e:
                logger.error(f"Error recording detailed feedback: {e}")
                del self._pending_feedback[user_id]
                return "记录反馈时出错，请稍后重试。"
        
        return "反馈流程出错，请重新开始。"
    
    def _process_detailed_feedback_command(
        self,
        user_id: str,
        text: str,
        article_context: Optional[dict]
    ) -> str:
        """处理详细反馈命令"""
        # 格式：反馈 [文章链接/ID] [评价]
        parts = text.split(maxsplit=2)
        
        if len(parts) < 2:
            return "请使用格式：反馈 [文章链接] [评价]\n" \
                   "评价可以是：有用/没用/太基础/太深/不感兴趣/质量差"
        
        # 如果有文章上下文，直接使用
        if article_context:
            if len(parts) >= 2:
                feedback_text = parts[1] if len(parts) == 2 else parts[2]
                return self._process_quick_feedback(
                    user_id,
                    self._parse_rating(feedback_text),
                    article_context
                )
        
        return "请先查看一篇文章，或提供文章链接。"
    
    def _parse_rating(self, text: str) -> str:
        """解析评价文本为评分类型"""
        text = text.lower().strip()
        
        if any(w in text for w in ['有用', '好', '不错', 'useful', 'good']):
            return 'useful'
        elif any(w in text for w in ['没用', '差', '不好', 'not useful', 'bad']):
            return 'not_useful'
        elif any(w in text for w in ['收藏', 'bookmark', 'mark']):
            return 'bookmark'
        elif any(w in text for w in ['更多', '类似', 'more', 'similar']):
            return 'more'
        
        return 'useful'  # 默认
    
    def _get_profile_response(self, user_id: str) -> str:
        """获取用户画像响应"""
        profile = self.feedback_handler.get_user_profile(user_id)
        
        if not profile:
            return "📊 您还没有反馈记录，暂无画像数据。\n" \
                   "开始对推送的文章进行反馈，我会逐渐了解您的偏好！"
        
        parts = ["📊 **您的偏好画像**\n"]
        
        preferred = profile.get('preferred_topics', [])
        if preferred:
            parts.append(f"✅ 感兴趣的话题：{', '.join(preferred[:5])}")
        
        disliked = profile.get('disliked_topics', [])
        if disliked:
            parts.append(f"❌ 不感兴趣的话题：{', '.join(disliked[:5])}")
        
        difficulty = profile.get('preferred_difficulty')
        if difficulty:
            diff_map = {'basic': '基础', 'advanced': '深入'}
            parts.append(f"📚 偏好难度：{diff_map.get(difficulty, difficulty)}")
        
        parts.append(f"\n📈 累计反馈：{profile.get('feedback_count', 0)} 次")
        
        return '\n'.join(parts)
    
    def _get_stats_response(self, user_id: str) -> str:
        """获取反馈统计响应"""
        stats = self.feedback_handler.get_feedback_stats(user_id)
        
        total = stats.get('total', 0)
        if total == 0:
            return "📊 您还没有反馈记录。"
        
        useful = stats.get('useful', 0)
        not_useful = stats.get('not_useful', 0)
        bookmarked = stats.get('bookmarked', 0)
        
        useful_rate = (useful / total * 100) if total > 0 else 0
        
        return f"📊 **您的反馈统计**\n\n" \
               f"总反馈数：{total}\n" \
               f"✅ 有用：{useful} ({useful_rate:.1f}%)\n" \
               f"❌ 没用：{not_useful}\n" \
               f"⭐ 收藏：{bookmarked}"
    
    def build_feedback_card(self, article: dict) -> dict:
        """
        构建带反馈按钮的飞书卡片
        
        Args:
            article: 文章信息
        
        Returns:
            飞书卡片 JSON
        """
        article_id = article.get('id', article.get('url', ''))
        title = article.get('title', '未知标题')
        
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title[:50]},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": article.get('summary', '')[:200]
                    }
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "👍 有用"},
                            "type": "primary",
                            "value": {"action": "feedback", "rating": "useful", "article_id": article_id}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "👎 没用"},
                            "type": "default",
                            "value": {"action": "feedback", "rating": "not_useful", "article_id": article_id}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "⭐ 收藏"},
                            "type": "default",
                            "value": {"action": "feedback", "rating": "bookmark", "article_id": article_id}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔍 更多类似"},
                            "type": "default",
                            "value": {"action": "feedback", "rating": "more", "article_id": article_id}
                        }
                    ]
                }
            ]
        }
