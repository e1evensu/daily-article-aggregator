"""
RAG 问答引擎模块

集成 KnowledgeBase, ContextManager, QueryProcessor 和 AIAnalyzer，
实现基于检索增强生成（RAG）的问答功能。

Requirements:
    - 3.1: 使用 RAG（检索增强生成）架构
    - 3.3: 使用 LLM 生成综合回答
    - 2.5: 回答中包含来源链接
    - 3.5: 无相关内容时明确告知用户
    
RAG Enhancement Requirements:
    - 3.1: 接受可选的对话历史作为输入
    - 3.2: 使用对话历史增强查询理解和检索
    - 3.4: 历史超过 max_history_turns 时只使用最近的轮次
    - 3.5: 历史为空或未提供时，不使用历史上下文处理查询

Statistics Integration Requirements:
    - 10.1: 记录问答事件
"""

import logging
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.stats.collector import StatsCollector

from src.qa.knowledge_base import KnowledgeBase
from src.qa.context_manager import ContextManager
from src.qa.query_processor import QueryProcessor, ParsedQuery
from src.qa.config import QAConfig, QAEngineConfig, RetrievalConfig
from src.qa.models import QAResponse, RetrievalResult, ConversationTurn, ERROR_CODES
from src.qa.history_aware_query_builder import HistoryAwareQueryBuilder
from src.analyzers.ai_analyzer import AIAnalyzer

# 配置日志
logger = logging.getLogger(__name__)


# RAG 提示词模板
DEFAULT_RAG_SYSTEM_PROMPT = """你是一个专业的技术问答助手，拥有丰富的知识。你可以访问一个知识库作为额外的参考资料。

回答要求：
1. 综合使用你自己的知识和提供的参考资料来回答问题
2. 如果参考资料中有相关内容，优先引用并在末尾列出来源
3. 如果参考资料不够或不相关，直接用你自己的知识回答即可
4. 回答要简洁、准确、有条理
5. 使用中文回答"""

DEFAULT_RAG_USER_PROMPT = """请回答用户的问题。以下是从知识库检索到的可能相关的参考资料，你可以选择性地使用。

## 知识库参考资料
{context}

## 对话历史
{history}

## 用户问题
{query}

请综合你的知识和参考资料回答问题。如果引用了参考资料，请在末尾列出来源链接。"""

# 无知识库内容时的提示词
DEFAULT_NO_CONTEXT_SYSTEM_PROMPT = """你是一个专业的技术问答助手，拥有丰富的知识。

回答要求：
1. 使用你的知识回答用户问题
2. 回答要简洁、准确、有条理
3. 如果问题超出你的能力范围，请诚实告知
4. 使用中文回答"""

DEFAULT_NO_CONTEXT_USER_PROMPT = """用户问题：{query}

请回答这个问题。"""

DEFAULT_NO_CONTEXT_PROMPT = """用户问题：{query}

抱歉，我暂时无法回答这个问题。请稍后再试。"""


class QAEngine:
    """
    RAG 问答引擎
    
    集成知识库、上下文管理器、查询处理器和 AI 分析器，
    实现基于检索增强生成的问答功能。
    
    Attributes:
        knowledge_base: 知识库实例
        context_manager: 上下文管理器实例
        query_processor: 查询处理器实例
        ai_analyzer: AI 分析器实例（用于生成回答）
        config: 问答引擎配置
        stats_collector: 统计收集器实例（可选）
    
    Requirements: 3.1, 3.3, 10.1
    """
    
    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        context_manager: ContextManager,
        query_processor: QueryProcessor,
        ai_analyzer: AIAnalyzer,
        config: QAEngineConfig | dict[str, Any] | None = None,
        retrieval_config: RetrievalConfig | dict[str, Any] | None = None,
        stats_collector: 'StatsCollector | None' = None
    ):
        """
        初始化问答引擎
        
        Args:
            knowledge_base: 知识库实例
            context_manager: 上下文管理器实例
            query_processor: 查询处理器实例
            ai_analyzer: AI 分析器实例（复用现有）
            config: 问答引擎配置（可选）
            retrieval_config: RAG 检索增强配置（可选）
            stats_collector: 统计收集器实例（可选，用于记录问答事件）
        
        Examples:
            >>> from src.qa.knowledge_base import KnowledgeBase
            >>> from src.qa.context_manager import ContextManager
            >>> from src.qa.query_processor import QueryProcessor
            >>> from src.analyzers.ai_analyzer import AIAnalyzer
            >>> from src.stats.collector import StatsCollector
            >>> 
            >>> kb = KnowledgeBase({'chroma_path': 'data/chroma_db'})
            >>> cm = ContextManager(max_history=5)
            >>> qp = QueryProcessor()
            >>> ai = AIAnalyzer({'api_key': 'xxx', 'model': 'gpt-4'})
            >>> stats = StatsCollector()
            >>> 
            >>> engine = QAEngine(kb, cm, qp, ai, stats_collector=stats)
        
        Requirements: 3.1, 3.3, 10.1
        """
        self.knowledge_base = knowledge_base
        self.context_manager = context_manager
        self.query_processor = query_processor
        self.ai_analyzer = ai_analyzer
        self._stats_collector = stats_collector
        
        # 解析配置
        if config is None:
            self._config = QAEngineConfig()
        elif isinstance(config, QAEngineConfig):
            self._config = config
        else:
            self._config = QAEngineConfig.from_dict(config)
        
        # 解析 RAG 检索增强配置
        if retrieval_config is None:
            self._retrieval_config = RetrievalConfig()
        elif isinstance(retrieval_config, RetrievalConfig):
            self._retrieval_config = retrieval_config
        else:
            self._retrieval_config = RetrievalConfig.from_dict(retrieval_config)
        
        # 初始化历史感知查询构建器
        self._query_builder = HistoryAwareQueryBuilder(
            default_max_turns=self._retrieval_config.max_history_turns
        )
        
        logger.info(
            f"QAEngine initialized: max_retrieved_docs={self._config.max_retrieved_docs}, "
            f"min_relevance_score={self._config.min_relevance_score}, "
            f"answer_max_length={self._config.answer_max_length}, "
            f"max_history_turns={self._retrieval_config.max_history_turns}, "
            f"stats_enabled={self._stats_collector is not None}"
        )
    
    @property
    def config(self) -> QAEngineConfig:
        """获取问答引擎配置"""
        return self._config
    
    @property
    def retrieval_config(self) -> RetrievalConfig:
        """获取 RAG 检索增强配置"""
        return self._retrieval_config
    
    @property
    def query_builder(self) -> HistoryAwareQueryBuilder:
        """获取历史感知查询构建器"""
        return self._query_builder
    
    @property
    def stats_collector(self) -> 'StatsCollector | None':
        """获取统计收集器"""
        return self._stats_collector
    
    def set_stats_collector(self, collector: 'StatsCollector') -> None:
        """
        设置统计收集器
        
        Args:
            collector: 统计收集器实例
        """
        self._stats_collector = collector
        logger.info("Stats collector set for QAEngine")
    
    def process_query(
        self,
        query: str,
        user_id: str,
        chat_id: str | None = None,
        history: list[ConversationTurn] | None = None
    ) -> QAResponse:
        """
        处理用户查询
        
        完整的 RAG 问答流程：
        1. 解析查询，检测查询类型
        2. 使用历史感知查询构建器构建增强查询（如果提供了历史）
        3. 从知识库检索相关文档
        4. 构建对话上下文
        5. 使用 LLM 生成回答
        6. 保存对话历史
        
        Args:
            query: 用户问题
            user_id: 用户 ID
            chat_id: 群聊 ID（私聊时为 None）
            history: 对话历史（可选，用于增强查询理解和检索）
        
        Returns:
            QAResponse 对象，包含回答、来源和置信度
        
        Examples:
            >>> response = engine.process_query(
            ...     "什么是RAG?",
            ...     user_id="user123",
            ...     chat_id="group456"
            ... )
            >>> print(response.answer)
            "RAG（检索增强生成）是一种..."
            >>> print(response.sources)
            [{'title': '...', 'url': '...'}]
            
            >>> # 使用对话历史
            >>> from src.qa.models import ConversationTurn
            >>> history = [ConversationTurn(query="什么是向量数据库?", answer="向量数据库是...")]
            >>> response = engine.process_query(
            ...     "它有什么优点?",
            ...     user_id="user123",
            ...     history=history
            ... )
        
        Requirements: 
            - 3.1: 使用 RAG 架构，接受可选的对话历史作为输入
            - 3.2: 使用对话历史增强查询理解和检索
            - 3.3: 使用 LLM 生成综合回答
            - 3.4: 历史超过 max_history_turns 时只使用最近的轮次
            - 3.5: 历史为空或未提供时，不使用历史上下文处理查询
            - 2.5: 回答中包含来源链接
        """
        if not query or not query.strip():
            return QAResponse(
                answer=ERROR_CODES["INVALID_QUERY"],
                sources=[],
                confidence=0.0,
                query_type="general"
            )
        
        query = query.strip()
        logger.info(f"Processing query from user {user_id}: {query[:50]}...")
        
        # 记录开始时间（用于统计响应时间）
        start_time = time.time()
        
        try:
            # 1. 解析查询
            parsed_query = self.query_processor.parse_query(query)
            logger.debug(
                f"Parsed query: type={parsed_query.query_type}, "
                f"keywords={parsed_query.keywords[:3]}"
            )
            
            # 2. 使用历史感知查询构建器构建增强查询
            # Requirement 3.1: 接受可选的对话历史作为输入
            # Requirement 3.2: 使用对话历史增强查询理解和检索
            # Requirement 3.4: 历史超过 max_history_turns 时只使用最近的轮次
            # Requirement 3.5: 历史为空或未提供时，不使用历史上下文处理查询
            enhanced_query = self._query_builder.build_query(
                current_query=query,
                history=history,
                max_turns=self._retrieval_config.max_history_turns
            )
            
            logger.debug(
                f"Enhanced query: original='{query[:30]}...', "
                f"history_turns={len(history) if history else 0}, "
                f"enhanced='{enhanced_query[:50]}...'"
            )
            
            # 3. 构建搜索过滤器并检索文档（使用增强查询）
            search_filters = self.query_processor.build_search_filters(parsed_query)
            retrieved_docs = self._retrieve_documents(enhanced_query, search_filters)
            
            # 4. 过滤低相关性文档
            filtered_docs = self._filter_by_relevance(retrieved_docs)
            
            # 5. 获取对话上下文（用于 LLM 生成回答）
            context = self.context_manager.get_context(user_id)
            
            # 6. 生成回答
            if filtered_docs:
                response = self._generate_answer(
                    query=query,
                    retrieved_docs=filtered_docs,
                    context=context,
                    query_type=parsed_query.query_type
                )
            else:
                # 无相关内容
                response = self._generate_no_result_response(query, parsed_query.query_type)
            
            # 7. 保存对话历史
            source_urls = [s.get('url', '') for s in response.sources if s.get('url')]
            self.context_manager.add_turn(
                user_id=user_id,
                query=query,
                answer=response.answer,
                sources=source_urls
            )
            
            logger.info(
                f"Generated response for user {user_id}: "
                f"confidence={response.confidence:.2f}, "
                f"sources={len(response.sources)}"
            )
            
            # 记录问答事件到统计系统
            # Requirement 10.1: 记录问答事件
            if self._stats_collector:
                response_time_ms = int((time.time() - start_time) * 1000)
                try:
                    self._stats_collector.record_qa_event(
                        query=query,
                        answer=response.answer[:500] if response.answer else '',  # 截断长回答
                        user_id=user_id,
                        relevance_score=response.confidence,
                        sources_used=len(response.sources),
                        response_time_ms=response_time_ms
                    )
                except Exception as stats_error:
                    logger.warning(f"Failed to record QA stats: {stats_error}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            return QAResponse(
                answer=ERROR_CODES["SERVICE_ERROR"],
                sources=[],
                confidence=0.0,
                query_type="general"
            )
    
    def _retrieve_documents(
        self,
        query: str,
        filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        从知识库检索相关文档
        
        Args:
            query: 查询文本
            filters: 搜索过滤器
        
        Returns:
            检索到的文档列表
        
        Requirements: 3.2
        """
        try:
            results = self.knowledge_base.search(
                query=query,
                n_results=self._config.max_retrieved_docs,
                filters=filters
            )
            logger.debug(f"Retrieved {len(results)} documents from knowledge base")
            return results
        except Exception as e:
            logger.error(f"Error retrieving documents: {e}")
            return []
    
    def _filter_by_relevance(
        self,
        docs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        过滤低相关性文档
        
        Args:
            docs: 检索到的文档列表
        
        Returns:
            过滤后的文档列表
        
        Requirements: 3.4
        """
        filtered = [
            doc for doc in docs
            if doc.get('score', 0) >= self._config.min_relevance_score
        ]
        logger.debug(
            f"Filtered documents: {len(docs)} -> {len(filtered)} "
            f"(min_score={self._config.min_relevance_score})"
        )
        return filtered
    
    def _generate_answer(
        self,
        query: str,
        retrieved_docs: list[dict[str, Any]],
        context: list[dict[str, Any]],
        query_type: str
    ) -> QAResponse:
        """
        使用 LLM 生成回答
        
        Args:
            query: 用户问题
            retrieved_docs: 检索到的相关文档
            context: 对话上下文
            query_type: 查询类型
        
        Returns:
            QAResponse 对象
        
        Requirements: 3.1, 3.3, 2.5
        """
        # 构建参考资料文本
        context_text = self._build_context_text(retrieved_docs)
        
        # 构建对话历史文本
        history_text = self._build_history_text(context)
        
        # 构建 RAG 提示词
        user_prompt = DEFAULT_RAG_USER_PROMPT.format(
            context=context_text,
            history=history_text,
            query=query
        )
        
        # 调用 AI 生成回答
        try:
            answer = self.ai_analyzer._call_api(
                user_prompt=user_prompt,
                system_prompt=DEFAULT_RAG_SYSTEM_PROMPT
            )
            
            if not answer:
                logger.warning("AI returned empty answer, using fallback")
                answer = self._generate_fallback_answer(retrieved_docs)
            
        except Exception as e:
            logger.error(f"Error calling AI API: {e}")
            answer = self._generate_fallback_answer(retrieved_docs)
        
        # 确保回答不超过最大长度
        answer = self._truncate_answer(answer)
        
        # 提取来源信息
        sources = self._extract_sources(retrieved_docs)
        
        # 计算置信度（基于检索文档的平均相关性分数）
        confidence = self._calculate_confidence(retrieved_docs)
        
        return QAResponse(
            answer=answer,
            sources=sources,
            confidence=confidence,
            query_type=query_type
        )
    
    def _build_context_text(self, docs: list[dict[str, Any]]) -> str:
        """
        构建参考资料文本
        
        Args:
            docs: 检索到的文档列表
        
        Returns:
            格式化的参考资料文本
        """
        if not docs:
            return "（无相关参考资料）"
        
        context_parts = []
        for i, doc in enumerate(docs, 1):
            metadata = doc.get('metadata', {})
            title = metadata.get('title', '未知标题')
            url = metadata.get('url', '')
            content = doc.get('content', '')
            score = doc.get('score', 0)
            
            part = f"### 参考资料 {i}\n"
            part += f"**标题**: {title}\n"
            if url:
                part += f"**来源**: {url}\n"
            part += f"**相关度**: {score:.2f}\n"
            part += f"**内容**:\n{content}\n"
            
            context_parts.append(part)
        
        return "\n---\n".join(context_parts)
    
    def _build_history_text(self, context: list[dict[str, Any]]) -> str:
        """
        构建对话历史文本
        
        Args:
            context: 对话上下文列表
        
        Returns:
            格式化的对话历史文本
        """
        if not context:
            return "（无历史对话）"
        
        history_parts = []
        for turn in context[-3:]:  # 只使用最近3轮对话
            query = turn.get('query', '')
            answer = turn.get('answer', '')
            # 截断过长的历史回答
            if len(answer) > 200:
                answer = answer[:200] + "..."
            history_parts.append(f"用户: {query}\n助手: {answer}")
        
        return "\n\n".join(history_parts)
    
    def _generate_fallback_answer(self, docs: list[dict[str, Any]]) -> str:
        """
        生成降级回答（当 LLM 调用失败时）
        
        Args:
            docs: 检索到的文档列表
        
        Returns:
            降级回答文本
        """
        if not docs:
            return ERROR_CODES["NO_RESULTS"]
        
        answer_parts = ["根据知识库检索，找到以下相关内容：\n"]
        
        for i, doc in enumerate(docs[:3], 1):
            metadata = doc.get('metadata', {})
            title = metadata.get('title', '未知标题')
            url = metadata.get('url', '')
            content = doc.get('content', '')[:200]
            
            part = f"{i}. **{title}**\n"
            part += f"   {content}...\n"
            if url:
                part += f"   来源: {url}\n"
            
            answer_parts.append(part)
        
        return "\n".join(answer_parts)
    
    def _generate_no_result_response(
        self,
        query: str,
        query_type: str
    ) -> QAResponse:
        """
        生成无结果响应（使用 AI 通用知识回答）
        
        Args:
            query: 用户问题
            query_type: 查询类型
        
        Returns:
            QAResponse 对象
        
        Requirements: 3.5
        """
        # 尝试使用 AI 的通用知识回答
        try:
            user_prompt = DEFAULT_NO_CONTEXT_USER_PROMPT.format(query=query)
            answer = self.ai_analyzer._call_api(
                user_prompt=user_prompt,
                system_prompt=DEFAULT_NO_CONTEXT_SYSTEM_PROMPT
            )
            
            if answer:
                # AI 成功回答，但置信度较低（因为没有知识库支撑）
                logger.info("Generated answer using AI general knowledge (no KB results)")
                return QAResponse(
                    answer=answer,
                    sources=[],
                    confidence=0.3,  # 较低置信度，表示非知识库内容
                    query_type=query_type
                )
        except Exception as e:
            logger.error(f"Error generating AI answer for no-result query: {e}")
        
        # AI 也失败了，返回固定提示
        answer = DEFAULT_NO_CONTEXT_PROMPT.format(query=query)
        
        return QAResponse(
            answer=answer,
            sources=[],
            confidence=0.0,
            query_type=query_type
        )
    
    def _truncate_answer(self, answer: str) -> str:
        """
        处理回答（不再截断）
        
        Args:
            answer: 原始回答
        
        Returns:
            原始回答
        """
        return answer if answer else ""
    
    def _extract_sources(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        从检索文档中提取来源信息
        
        Args:
            docs: 检索到的文档列表
        
        Returns:
            来源信息列表
        
        Requirements: 2.5
        """
        sources = []
        seen_urls = set()
        
        for doc in docs:
            metadata = doc.get('metadata', {})
            url = metadata.get('url', '')
            
            # 去重
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append({
                    'title': metadata.get('title', '未知标题'),
                    'url': url,
                    'source_type': metadata.get('source_type', ''),
                    'score': doc.get('score', 0)
                })
        
        return sources
    
    def _calculate_confidence(self, docs: list[dict[str, Any]]) -> float:
        """
        计算回答置信度
        
        基于检索文档的平均相关性分数计算。
        
        Args:
            docs: 检索到的文档列表
        
        Returns:
            置信度分数 (0-1)
        
        Requirements: 3.4
        """
        if not docs:
            return 0.0
        
        scores = [doc.get('score', 0) for doc in docs]
        avg_score = sum(scores) / len(scores)
        
        # 考虑文档数量的影响
        # 更多相关文档 = 更高置信度
        doc_factor = min(len(docs) / self._config.max_retrieved_docs, 1.0)
        
        confidence = avg_score * 0.7 + doc_factor * 0.3
        return min(max(confidence, 0.0), 1.0)
    
    def clear_user_context(self, user_id: str) -> None:
        """
        清除用户对话上下文
        
        Args:
            user_id: 用户 ID
        """
        self.context_manager.clear_context(user_id)
        logger.info(f"Cleared context for user {user_id}")
    
    def get_stats(self) -> dict[str, Any]:
        """
        获取问答引擎统计信息
        
        Returns:
            统计信息字典
        """
        kb_stats = self.knowledge_base.get_stats()
        cm_stats = self.context_manager.get_stats()
        
        return {
            'knowledge_base': kb_stats,
            'context_manager': cm_stats,
            'config': self._config.to_dict()
        }
