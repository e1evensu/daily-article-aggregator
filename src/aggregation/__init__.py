"""
话题聚合系统模块

智能内容聚合与自动化知识沉淀系统，用于自动识别多源文章中的热点话题，
通过 AI 整合生成结构化综述文档，并发布到飞书文档形成自建知识库 RSS。

公共接口:
    数据模型:
        - TopicCluster: 话题聚类数据模型
        - Synthesis: 综述数据模型
        - FilterResult: 过滤结果数据模型
        - PublishResult: 发布结果数据模型
        - RSSItem: RSS 条目数据模型
        - DEFAULT_AGGREGATION_THRESHOLD: 默认聚合阈值常量

    组件 (将在后续任务中实现):
        - QualityFilter: 质量过滤器 (Task 2.1)
        - AggregationEngine: 聚合引擎 (Task 3.1)
        - SynthesisGenerator: 综述生成器 (Task 5.1)
        - FeishuDocPublisher: 飞书文档发布器 (Task 6.1)
        - KnowledgeRSSGenerator: 知识 RSS 生成器 (Task 8.1)
        - TopicAggregationSystem: 话题聚合系统主类 (Task 11.1)
"""

# =============================================================================
# 数据模型导出
# =============================================================================
from src.aggregation.models import (
    TopicCluster,
    Synthesis,
    FilterResult,
    PublishResult,
    RSSItem,
    DEFAULT_AGGREGATION_THRESHOLD,
)

# =============================================================================
# 质量过滤器 (Task 2.1)
# =============================================================================
from src.aggregation.quality_filter import QualityFilter, DEFAULT_BLACKLIST_DOMAINS

# =============================================================================
# 聚合引擎 (Task 3.1)
# =============================================================================
from src.aggregation.aggregation_engine import (
    AggregationEngine,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TITLE_WEIGHT,
    DEFAULT_KEYWORD_WEIGHT,
)

# =============================================================================
# 综述生成器 (Task 5.1)
# =============================================================================
from src.aggregation.synthesis_generator import SynthesisGenerator

# =============================================================================
# 飞书文档发布器 (Task 6.1)
# =============================================================================
from src.aggregation.feishu_doc_publisher import FeishuDocPublisher

# =============================================================================
# 知识 RSS 生成器 (Task 8.1)
# =============================================================================
from src.aggregation.knowledge_rss_generator import KnowledgeRSSGenerator

# =============================================================================
# 话题聚合系统主类 (Task 11.1)
# =============================================================================
from src.aggregation.topic_aggregation_system import TopicAggregationSystem

# =============================================================================
# 公共接口列表
# =============================================================================
__all__ = [
    # 数据模型
    "TopicCluster",
    "Synthesis",
    "FilterResult",
    "PublishResult",
    "RSSItem",
    "DEFAULT_AGGREGATION_THRESHOLD",
    # 质量过滤器 (Task 2.1)
    "QualityFilter",
    "DEFAULT_BLACKLIST_DOMAINS",
    # 聚合引擎 (Task 3.1)
    "AggregationEngine",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_TITLE_WEIGHT",
    "DEFAULT_KEYWORD_WEIGHT",
    # 综述生成器 (Task 5.1)
    "SynthesisGenerator",
    # 飞书文档发布器 (Task 6.1)
    "FeishuDocPublisher",
    # 知识 RSS 生成器 (Task 8.1)
    "KnowledgeRSSGenerator",
    # 话题聚合系统主类 (Task 11.1)
    "TopicAggregationSystem",
]
