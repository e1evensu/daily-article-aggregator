"""
知识库问答系统配置模块

定义问答系统的配置数据类和配置加载函数。

Requirements:
    - 1.2: 使用向量数据库存储嵌入
    - 5.3: 支持配置回答风格和长度
    - 5.4: 支持设置问答频率限制
    
RAG Enhancement Requirements:
    - 1.1, 1.5: 相似度阈值配置和验证
    - 2.1, 2.5: 每文档最大分块数配置和验证
    - 3.3: 最大历史对话轮数配置
"""

from dataclasses import dataclass, field
from typing import Any
import os


@dataclass
class RetrievalConfig:
    """
    RAG 检索配置
    
    用于配置 RAG 检索增强功能的参数，包括相似度阈值、每文档分块限制、
    历史对话轮数和去重阈值。
    
    Attributes:
        similarity_threshold: 相似度阈值 [0, 1]，低于此阈值的结果将被过滤
        max_chunks_per_doc: 每文档最大分块数，0 表示无限制
        max_history_turns: 最大历史对话轮数
        dedup_threshold: 去重相似度阈值，高于此阈值的内容将被去重
    
    Requirements:
        - 1.1, 1.5: 相似度阈值配置和验证
        - 2.1, 2.5: 每文档最大分块数配置和验证
        - 3.3: 最大历史对话轮数配置
    """
    similarity_threshold: float = 0.5  # 相似度阈值 [0, 1]
    max_chunks_per_doc: int = 3        # 每文档最大分块数，0 表示无限制
    max_history_turns: int = 5         # 最大历史对话轮数
    dedup_threshold: float = 0.95      # 去重相似度阈值
    
    def validate(self) -> None:
        """
        验证配置参数
        
        Raises:
            ValueError: 当参数值不在有效范围内时
            
        Requirements:
            - 1.5: similarity_threshold 必须在 [0, 1] 范围内
            - 2.5: max_chunks_per_doc 必须 >= 0
        """
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError(
                f"similarity_threshold must be in [0, 1], got {self.similarity_threshold}"
            )
        if self.max_chunks_per_doc < 0:
            raise ValueError(
                f"max_chunks_per_doc must be >= 0, got {self.max_chunks_per_doc}"
            )
        if self.max_history_turns < 0:
            raise ValueError(
                f"max_history_turns must be >= 0, got {self.max_history_turns}"
            )
        if not 0 <= self.dedup_threshold <= 1:
            raise ValueError(
                f"dedup_threshold must be in [0, 1], got {self.dedup_threshold}"
            )
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "similarity_threshold": self.similarity_threshold,
            "max_chunks_per_doc": self.max_chunks_per_doc,
            "max_history_turns": self.max_history_turns,
            "dedup_threshold": self.dedup_threshold,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RetrievalConfig":
        """从字典创建配置"""
        return cls(
            similarity_threshold=data.get("similarity_threshold", 0.5),
            max_chunks_per_doc=data.get("max_chunks_per_doc", 3),
            max_history_turns=data.get("max_history_turns", 5),
            dedup_threshold=data.get("dedup_threshold", 0.95),
        )


@dataclass
class ChromaConfig:
    """
    ChromaDB 配置
    
    Attributes:
        path: ChromaDB 持久化路径
        collection_name: 集合名称
    
    Requirements: 1.2
    """
    path: str = "data/chroma_db"
    collection_name: str = "knowledge_articles"
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "path": self.path,
            "collection_name": self.collection_name,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChromaConfig":
        """从字典创建配置"""
        return cls(
            path=data.get("path", "data/chroma_db"),
            collection_name=data.get("collection_name", "knowledge_articles"),
        )


@dataclass
class EmbeddingConfig:
    """
    Embedding 配置
    
    Attributes:
        model: Embedding 模型名称
        api_base: API 地址（可选，默认复用 AI 配置）
        api_key: API 密钥（可选，默认复用 AI 配置）
    
    Requirements: 1.1
    """
    model: str = "text-embedding-3-small"
    api_base: str | None = None
    api_key: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {"model": self.model}
        if self.api_base:
            result["api_base"] = self.api_base
        if self.api_key:
            result["api_key"] = self.api_key
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmbeddingConfig":
        """从字典创建配置"""
        return cls(
            model=data.get("model", "text-embedding-3-small"),
            api_base=data.get("api_base"),
            api_key=data.get("api_key"),
        )


@dataclass
class EventServerConfig:
    """
    飞书事件服务器配置
    
    Attributes:
        host: 监听地址
        port: 监听端口
        verification_token: 飞书验证 token
        encrypt_key: 加密密钥（可选）
    
    Requirements: 2.1
    """
    host: str = "0.0.0.0"
    port: int = 8080
    verification_token: str = ""
    encrypt_key: str = ""
    
    def __post_init__(self):
        """初始化后处理，从环境变量读取敏感配置"""
        if not self.verification_token:
            self.verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
        if not self.encrypt_key:
            self.encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "host": self.host,
            "port": self.port,
            "verification_token": self.verification_token,
            "encrypt_key": self.encrypt_key,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventServerConfig":
        """从字典创建配置"""
        return cls(
            host=data.get("host", "0.0.0.0"),
            port=data.get("port", 8080),
            verification_token=data.get("verification_token", ""),
            encrypt_key=data.get("encrypt_key", ""),
        )


@dataclass
class QAEngineConfig:
    """
    问答引擎配置
    
    Attributes:
        max_context_turns: 最大上下文轮数
        context_ttl_minutes: 上下文过期时间（分钟）
        max_retrieved_docs: 最大检索文档数
        min_relevance_score: 最小相关性分数
        answer_max_length: 回答最大长度
    
    Requirements: 2.4, 5.3
    """
    max_context_turns: int = 5
    context_ttl_minutes: int = 30
    max_retrieved_docs: int = 5
    min_relevance_score: float = 0.5
    answer_max_length: int = 4000
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "max_context_turns": self.max_context_turns,
            "context_ttl_minutes": self.context_ttl_minutes,
            "max_retrieved_docs": self.max_retrieved_docs,
            "min_relevance_score": self.min_relevance_score,
            "answer_max_length": self.answer_max_length,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QAEngineConfig":
        """从字典创建配置"""
        return cls(
            max_context_turns=data.get("max_context_turns", 5),
            context_ttl_minutes=data.get("context_ttl_minutes", 30),
            max_retrieved_docs=data.get("max_retrieved_docs", 5),
            min_relevance_score=data.get("min_relevance_score", 0.5),
            answer_max_length=data.get("answer_max_length", 4000),
        )


@dataclass
class ChunkingConfig:
    """
    文档分块配置
    
    Attributes:
        chunk_size: 分块大小（字符）
        chunk_overlap: 分块重叠（字符）
    
    Requirements: 1.2
    """
    chunk_size: int = 500
    chunk_overlap: int = 50
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkingConfig":
        """从字典创建配置"""
        return cls(
            chunk_size=data.get("chunk_size", 500),
            chunk_overlap=data.get("chunk_overlap", 50),
        )


@dataclass
class RateLimitConfig:
    """
    频率限制配置
    
    Attributes:
        requests_per_minute: 全局每分钟请求限制
        requests_per_user_minute: 每用户每分钟请求限制
    
    Requirements: 5.4
    """
    requests_per_minute: int = 20
    requests_per_user_minute: int = 5
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "requests_per_minute": self.requests_per_minute,
            "requests_per_user_minute": self.requests_per_user_minute,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RateLimitConfig":
        """从字典创建配置"""
        return cls(
            requests_per_minute=data.get("requests_per_minute", 20),
            requests_per_user_minute=data.get("requests_per_user_minute", 5),
        )


@dataclass
class QAConfig:
    """
    问答系统总配置
    
    Attributes:
        enabled: 是否启用问答功能
        chroma: ChromaDB 配置
        embedding: Embedding 配置
        event_server: 事件服务器配置
        qa: 问答引擎配置
        chunking: 分块配置
        rate_limit: 频率限制配置
    
    Requirements: 1.1, 1.2, 2.1, 5.3, 5.4
    """
    enabled: bool = True
    chroma: ChromaConfig = field(default_factory=ChromaConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    event_server: EventServerConfig = field(default_factory=EventServerConfig)
    qa: QAEngineConfig = field(default_factory=QAEngineConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "chroma": self.chroma.to_dict(),
            "embedding": self.embedding.to_dict(),
            "event_server": self.event_server.to_dict(),
            "qa": self.qa.to_dict(),
            "chunking": self.chunking.to_dict(),
            "rate_limit": self.rate_limit.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QAConfig":
        """从字典创建配置"""
        return cls(
            enabled=data.get("enabled", True),
            chroma=ChromaConfig.from_dict(data.get("chroma", {})),
            embedding=EmbeddingConfig.from_dict(data.get("embedding", {})),
            event_server=EventServerConfig.from_dict(data.get("event_server", {})),
            qa=QAEngineConfig.from_dict(data.get("qa", {})),
            chunking=ChunkingConfig.from_dict(data.get("chunking", {})),
            rate_limit=RateLimitConfig.from_dict(data.get("rate_limit", {})),
        )


def load_qa_config(config_dict: dict[str, Any] | None = None) -> QAConfig:
    """
    加载问答系统配置
    
    Args:
        config_dict: 配置字典，如果为 None 则返回默认配置
        
    Returns:
        QAConfig 配置对象
    
    Example:
        >>> config = load_qa_config({"enabled": True, "chroma": {"path": "data/kb"}})
        >>> config.enabled
        True
        >>> config.chroma.path
        'data/kb'
    
    Requirements: 1.2, 5.3, 5.4
    """
    if config_dict is None:
        return QAConfig()
    
    # 如果配置字典中有 knowledge_qa 键，则使用该键下的配置
    if "knowledge_qa" in config_dict:
        config_dict = config_dict["knowledge_qa"]
    
    return QAConfig.from_dict(config_dict)


def load_retrieval_config(
    config_dict: dict[str, Any] | None = None,
    validate: bool = True
) -> RetrievalConfig:
    """
    加载 RAG 检索增强配置
    
    Args:
        config_dict: 配置字典，如果为 None 则返回默认配置
        validate: 是否验证配置参数，默认为 True
        
    Returns:
        RetrievalConfig 配置对象
        
    Raises:
        ValueError: 当 validate=True 且配置参数无效时
    
    Example:
        >>> config = load_retrieval_config({"similarity_threshold": 0.7})
        >>> config.similarity_threshold
        0.7
        >>> config.max_chunks_per_doc
        3
    
    Requirements: 1.1, 1.5, 2.1, 2.5, 3.3
    """
    if config_dict is None:
        config = RetrievalConfig()
    else:
        # 如果配置字典中有 rag_enhancement 键，则使用该键下的配置
        if "rag_enhancement" in config_dict:
            config_dict = config_dict["rag_enhancement"]
        
        config = RetrievalConfig.from_dict(config_dict)
    
    if validate:
        config.validate()
    
    return config
