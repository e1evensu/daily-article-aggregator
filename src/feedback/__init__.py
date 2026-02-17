"""
反馈系统模块

实现人工反馈校准系统，让 AI 推荐越来越精准。

主要组件：
- models: 反馈数据模型
- feedback_handler: 反馈处理器
- feedback_analyzer: 反馈分析引擎
- preference_updater: 偏好更新引擎
"""

from .models import (
    FeedbackType,
    QuickRating,
    NotMatchReason,
    ArticleFeedback,
    DetailedFeedback,
    FeedbackInsight,
    TopicAdjustment,
)
from .feedback_handler import FeedbackHandler
from .feishu_feedback import FeishuFeedbackHandler

__all__ = [
    "FeedbackType",
    "QuickRating",
    "NotMatchReason",
    "ArticleFeedback",
    "DetailedFeedback",
    "FeedbackInsight",
    "TopicAdjustment",
    "FeedbackHandler",
    "FeishuFeedbackHandler",
]
