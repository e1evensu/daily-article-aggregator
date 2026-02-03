"""
知识库问答机器人模块

基于 RAG（检索增强生成）架构的问答系统，通过飞书应用机器人提供交互式问答服务。
将现有文章数据库扩展为知识库，支持语义搜索和智能问答。

核心功能:
    - 知识库构建：将文章内容向量化存储到 ChromaDB
    - 语义搜索：基于向量相似度检索相关文章
    - RAG 问答：结合检索结果和 LLM 生成回答
    - 飞书交互：支持群聊 @机器人 和私聊问答
    - 多轮对话：支持上下文记忆的连续对话

公共接口:
    数据模型 (models.py):
        - KnowledgeDocument: 知识库文档模型
        - ConversationTurn: 对话轮次模型
        - ConversationContext: 对话上下文模型
        - RetrievalResult: 检索结果模型
        - QAResponse: 问答响应模型
        - ErrorResponse: 错误响应模型

    配置 (config.py):
        - QAConfig: 问答系统配置类
        - load_qa_config: 加载问答配置函数

    服务组件:
        - EmbeddingService: 向量化服务 (已实现)
        - create_embedding_service: 创建向量化服务的工厂函数

    组件 (将在后续任务中实现):
        - KnowledgeBase: 知识库管理器 (Task 3.1)
        - ContextManager: 上下文管理器 (Task 5.1)
        - QueryProcessor: 查询处理器 (Task 6.1)
        - QAEngine: 问答引擎 (Task 7.1)
        - RateLimiter: 频率限制器 (Task 9.1)
        - FeishuEventServer: 飞书事件服务器 (Task 10.1)

Requirements:
    - 1.1: 支持将文章内容转换为向量嵌入
    - 1.2: 使用向量数据库存储嵌入
"""

# =============================================================================
# 数据模型导出
# =============================================================================
from src.qa.models import (
    KnowledgeDocument,
    ConversationTurn,
    ConversationContext,
    RetrievalResult,
    QAResponse,
    ErrorResponse,
    ERROR_CODES,
)

# =============================================================================
# 配置导出
# =============================================================================
from src.qa.config import (
    QAConfig,
    ChromaConfig,
    EmbeddingConfig,
    EventServerConfig,
    QAEngineConfig,
    ChunkingConfig,
    RateLimitConfig,
    load_qa_config,
)

# =============================================================================
# 服务组件导出
# =============================================================================
from src.qa.embedding_service import (
    EmbeddingService,
    create_embedding_service,
)

from src.qa.knowledge_base import (
    KnowledgeBase,
)

from src.qa.context_manager import (
    ContextManager,
)

from src.qa.query_processor import (
    QueryProcessor,
    ParsedQuery,
)

from src.qa.qa_engine import (
    QAEngine,
)

from src.qa.rate_limiter import (
    RateLimiter,
    RateLimitResult,
)

from src.qa.event_server import (
    FeishuEventServer,
    create_event_server,
)

# =============================================================================
# 公共接口列表
# =============================================================================
__all__ = [
    # 数据模型
    "KnowledgeDocument",
    "ConversationTurn",
    "ConversationContext",
    "RetrievalResult",
    "QAResponse",
    "ErrorResponse",
    "ERROR_CODES",
    # 配置
    "QAConfig",
    "ChromaConfig",
    "EmbeddingConfig",
    "EventServerConfig",
    "QAEngineConfig",
    "ChunkingConfig",
    "RateLimitConfig",
    "load_qa_config",
    # 服务组件
    "EmbeddingService",
    "create_embedding_service",
    "KnowledgeBase",
    "ContextManager",
    "QueryProcessor",
    "ParsedQuery",
    "QAEngine",
    "RateLimiter",
    "RateLimitResult",
    # Event Server
    "FeishuEventServer",
    "create_event_server",
]
