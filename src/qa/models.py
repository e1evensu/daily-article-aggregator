"""
知识库问答系统数据模型模块

定义知识库文档、对话上下文、检索结果和问答响应的数据模型。

Requirements:
    - 1.1: 支持将文章内容转换为向量嵌入
    - 1.2: 使用向量数据库存储嵌入
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class KnowledgeDocument:
    """
    知识库文档模型
    
    表示存储在向量数据库中的文档片段。
    
    Attributes:
        doc_id: 文档唯一 ID（article_id + chunk_index）
        article_id: 原文章 ID
        chunk_index: 分块索引
        content: 文本内容
        embedding: 向量嵌入
        metadata: 元数据字典，包含:
            - title: 文章标题
            - url: 原文链接
            - source_type: 来源类型
            - published_date: 发布日期
            - category: 分类
    
    Requirements: 1.1, 1.2
    """
    doc_id: str
    article_id: int
    chunk_index: int
    content: str
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 KnowledgeDocument 对象转换为字典
        
        Returns:
            包含所有字段的字典
        """
        return {
            "doc_id": self.doc_id,
            "article_id": self.article_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "embedding": self.embedding,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeDocument":
        """
        从字典创建 KnowledgeDocument 对象
        
        Args:
            data: 包含文档数据的字典
            
        Returns:
            KnowledgeDocument 对象
        """
        return cls(
            doc_id=data.get("doc_id", ""),
            article_id=data.get("article_id", 0),
            chunk_index=data.get("chunk_index", 0),
            content=data.get("content", ""),
            embedding=data.get("embedding", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConversationTurn:
    """
    对话轮次模型
    
    表示一轮用户问答交互。
    
    Attributes:
        query: 用户问题
        answer: 机器人回答
        timestamp: 时间戳
        sources: 引用来源 URL 列表
    
    Requirements: 2.4
    """
    query: str
    answer: str
    timestamp: datetime = field(default_factory=datetime.now)
    sources: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 ConversationTurn 对象转换为字典
        
        Returns:
            包含所有字段的字典
        """
        return {
            "query": self.query,
            "answer": self.answer,
            "timestamp": self.timestamp.isoformat(),
            "sources": self.sources,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationTurn":
        """
        从字典创建 ConversationTurn 对象
        
        Args:
            data: 包含对话轮次数据的字典
            
        Returns:
            ConversationTurn 对象
        """
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()
        
        return cls(
            query=data.get("query", ""),
            answer=data.get("answer", ""),
            timestamp=timestamp,
            sources=data.get("sources", []),
        )


@dataclass
class ConversationContext:
    """
    对话上下文模型
    
    表示用户的对话历史上下文。
    
    Attributes:
        user_id: 用户 ID
        turns: 对话轮次列表
        last_active: 最后活跃时间
    
    Requirements: 2.4
    """
    user_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    last_active: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 ConversationContext 对象转换为字典
        
        Returns:
            包含所有字段的字典
        """
        return {
            "user_id": self.user_id,
            "turns": [turn.to_dict() for turn in self.turns],
            "last_active": self.last_active.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationContext":
        """
        从字典创建 ConversationContext 对象
        
        Args:
            data: 包含对话上下文数据的字典
            
        Returns:
            ConversationContext 对象
        """
        last_active = data.get("last_active")
        if isinstance(last_active, str):
            last_active = datetime.fromisoformat(last_active)
        elif last_active is None:
            last_active = datetime.now()
        
        turns_data = data.get("turns", [])
        turns = [
            ConversationTurn.from_dict(t) if isinstance(t, dict) else t
            for t in turns_data
        ]
        
        return cls(
            user_id=data.get("user_id", ""),
            turns=turns,
            last_active=last_active,
        )


@dataclass
class RetrievalResult:
    """
    检索结果模型
    
    表示从知识库检索到的文档结果。
    
    Attributes:
        doc_id: 文档 ID
        content: 文档内容
        score: 相似度分数 (0-1)
        metadata: 文档元数据
    
    Requirements: 3.2, 3.4
    """
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 RetrievalResult 对象转换为字典
        
        Returns:
            包含所有字段的字典
        """
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RetrievalResult":
        """
        从字典创建 RetrievalResult 对象
        
        Args:
            data: 包含检索结果数据的字典
            
        Returns:
            RetrievalResult 对象
        """
        return cls(
            doc_id=data.get("doc_id", ""),
            content=data.get("content", ""),
            score=data.get("score", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class QAResponse:
    """
    问答响应模型
    
    表示问答引擎生成的回答。
    
    Attributes:
        answer: 回答内容
        sources: 来源列表，每个来源包含 title, url 等
        confidence: 置信度 (0-1)
        query_type: 查询类型 (general/vulnerability/topic/source/time_range)
    
    Requirements: 2.5, 3.3, 3.4
    """
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    query_type: str = "general"
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 QAResponse 对象转换为字典
        
        Returns:
            包含所有字段的字典
        """
        return {
            "answer": self.answer,
            "sources": self.sources,
            "confidence": self.confidence,
            "query_type": self.query_type,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QAResponse":
        """
        从字典创建 QAResponse 对象
        
        Args:
            data: 包含问答响应数据的字典
            
        Returns:
            QAResponse 对象
        """
        return cls(
            answer=data.get("answer", ""),
            sources=data.get("sources", []),
            confidence=data.get("confidence", 0.0),
            query_type=data.get("query_type", "general"),
        )


# 错误代码定义
ERROR_CODES = {
    "RATE_LIMITED": "请求过于频繁，请稍后再试",
    "NO_RESULTS": "抱歉，知识库中没有找到相关内容",
    "SERVICE_ERROR": "服务暂时不可用，请稍后再试",
    "INVALID_QUERY": "无法理解您的问题，请换个方式提问",
}


@dataclass
class ErrorResponse:
    """
    错误响应模型
    
    表示问答系统的错误响应。
    
    Attributes:
        error_code: 错误代码
        message: 用户友好消息
        retry_after: 重试等待时间（秒），可选
    
    Requirements: 5.4
    """
    error_code: str
    message: str
    retry_after: int | None = None
    
    def __post_init__(self):
        """初始化后处理，如果 message 为空则从 ERROR_CODES 获取"""
        if not self.message and self.error_code in ERROR_CODES:
            self.message = ERROR_CODES[self.error_code]
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 ErrorResponse 对象转换为字典
        
        Returns:
            包含所有字段的字典
        """
        result = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorResponse":
        """
        从字典创建 ErrorResponse 对象
        
        Args:
            data: 包含错误响应数据的字典
            
        Returns:
            ErrorResponse 对象
        """
        return cls(
            error_code=data.get("error_code", ""),
            message=data.get("message", ""),
            retry_after=data.get("retry_after"),
        )
