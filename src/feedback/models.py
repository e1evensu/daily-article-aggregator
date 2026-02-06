"""
反馈数据模型

定义反馈系统的数据结构。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class FeedbackType(Enum):
    """反馈类型"""
    QUICK = "quick"           # 快速反馈（一键）
    DETAILED = "detailed"     # 详细反馈（对话）
    CONVERSATION = "conversation"  # 对话式反馈


class QuickRating(Enum):
    """快速评分类型"""
    USEFUL = "useful"              # 有用
    NOT_USEFUL = "not_useful"      # 没用
    BOOKMARK = "bookmark"          # 收藏
    MORE_LIKE_THIS = "more_like_this"  # 想要更多类似


class NotMatchReason(Enum):
    """不匹配原因"""
    TOO_BASIC = "too_basic"           # 内容太基础
    TOO_ADVANCED = "too_advanced"     # 内容太深入
    NOT_INTERESTED = "not_interested" # 话题不感兴趣
    LOW_QUALITY = "low_quality"       # 质量不高
    OTHER = "other"                   # 其他


@dataclass
class DetailedFeedback:
    """详细反馈"""
    not_match_reason: Optional[NotMatchReason] = None
    comment: Optional[str] = None
    expected_content: Optional[str] = None
    relevance_score: int = 0      # 1-5
    difficulty_score: int = 0     # 1-5 (1太简单，5太难)
    quality_score: int = 0        # 1-5


@dataclass
class ArticleFeedback:
    """文章反馈记录"""
    feedback_id: str
    article_id: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.now)
    
    # 反馈类型
    feedback_type: FeedbackType = FeedbackType.QUICK
    
    # 快速反馈
    quick_rating: Optional[QuickRating] = None
    
    # 详细反馈
    detailed_feedback: Optional[DetailedFeedback] = None
    
    # 对话记录
    conversation_log: list[dict] = field(default_factory=list)
    
    # AI 分析快照
    ai_analysis_snapshot: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "feedback_id": self.feedback_id,
            "article_id": self.article_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "feedback_type": self.feedback_type.value,
            "quick_rating": self.quick_rating.value if self.quick_rating else None,
            "detailed_feedback": {
                "not_match_reason": self.detailed_feedback.not_match_reason.value if self.detailed_feedback and self.detailed_feedback.not_match_reason else None,
                "comment": self.detailed_feedback.comment if self.detailed_feedback else None,
                "relevance_score": self.detailed_feedback.relevance_score if self.detailed_feedback else 0,
                "difficulty_score": self.detailed_feedback.difficulty_score if self.detailed_feedback else 0,
                "quality_score": self.detailed_feedback.quality_score if self.detailed_feedback else 0,
            } if self.detailed_feedback else None,
            "conversation_log": self.conversation_log,
            "ai_analysis_snapshot": self.ai_analysis_snapshot,
        }


@dataclass
class TopicAdjustment:
    """话题权重调整"""
    topic: str
    action: str  # "increase_weight" or "reduce_weight"
    confidence: float
    evidence_count: int


@dataclass
class FeedbackInsight:
    """从反馈中提取的洞察"""
    insight_type: str  # topic / difficulty / keyword / source
    insight_key: str   # 如 "Kubernetes"
    insight_value: str # 如 "reduce_weight"
    confidence: float  # 置信度 0-1
    evidence_count: int = 1
    first_seen: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "insight_type": self.insight_type,
            "insight_key": self.insight_key,
            "insight_value": self.insight_value,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "first_seen": self.first_seen.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }
