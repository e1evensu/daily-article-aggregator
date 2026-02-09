"""
增强的 RAG 检索器模块

实现相似度阈值过滤、每文档分块限制、内容去重和结果排序等增强功能。

Requirements:
    - 1.2: 按相似度阈值过滤检索结果
    - 1.3: 阈值为 0 时返回所有结果
    - 1.4: 阈值为 1 时只返回精确匹配
    - 2.2, 2.3, 2.4: 每文档分块数限制
    - 3.1, 3.2, 3.4, 3.5: 历史对话上下文支持
    - 4.1, 4.2: 内容去重
    - 4.3, 4.4, 4.5: 结果排序优化
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from src.qa.config import RetrievalConfig
from src.qa.models import ConversationTurn, RetrievalResult
from src.qa.history_aware_query_builder import HistoryAwareQueryBuilder

if TYPE_CHECKING:
    from src.qa.knowledge_base import KnowledgeBase

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    """
    检索分块结果
    
    表示从知识库检索到的单个文档分块。
    
    Attributes:
        doc_id: 文档分块 ID（格式：article_id_chunk_index）
        content: 分块内容
        score: 相似度分数 (0-1)
        metadata: 元数据字典
    """
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def article_id(self) -> str:
        """
        从 doc_id 提取文章 ID
        
        doc_id 格式为 "article_id_chunk_index"，例如 "123_0"
        """
        if '_' in self.doc_id:
            return self.doc_id.rsplit('_', 1)[0]
        return self.doc_id
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkResult":
        """从字典创建 ChunkResult"""
        return cls(
            doc_id=data.get("doc_id", ""),
            content=data.get("content", ""),
            score=data.get("score", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class EnhancedRetrievalResult:
    """
    增强检索结果
    
    包含过滤、去重、排序后的检索结果及元数据。
    
    Attributes:
        chunks: 检索到的分块列表
        total_before_filter: 过滤前的总数
        total_after_filter: 过滤后的总数
        deduplicated_count: 去重移除的数量
    """
    chunks: list[ChunkResult] = field(default_factory=list)
    total_before_filter: int = 0
    total_after_filter: int = 0
    deduplicated_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "chunks": [c.to_dict() for c in self.chunks],
            "total_before_filter": self.total_before_filter,
            "total_after_filter": self.total_after_filter,
            "deduplicated_count": self.deduplicated_count,
        }


class EnhancedRetriever:
    """
    增强的 RAG 检索器
    
    提供相似度阈值过滤、每文档分块限制、内容去重和结果排序等增强功能。
    
    Attributes:
        kb: 知识库实例
        config: 检索配置
    
    Requirements:
        - 1.2, 1.3, 1.4: 相似度阈值过滤
        - 2.2, 2.3, 2.4: 每文档分块限制
        - 4.1, 4.2: 内容去重
        - 4.3, 4.4, 4.5: 结果排序
    """
    
    def __init__(self, knowledge_base: "KnowledgeBase", config: RetrievalConfig):
        """
        初始化增强检索器
        
        Args:
            knowledge_base: 知识库实例
            config: 检索配置
            
        Raises:
            ValueError: 配置参数无效时
        """
        self.kb = knowledge_base
        self.config = config
        
        # 验证配置
        self.config.validate()
        
        # 初始化历史感知查询构建器
        self.query_builder = HistoryAwareQueryBuilder(
            default_max_turns=config.max_history_turns
        )
        
        logger.info(
            f"EnhancedRetriever initialized with config: "
            f"similarity_threshold={config.similarity_threshold}, "
            f"max_chunks_per_doc={config.max_chunks_per_doc}, "
            f"max_history_turns={config.max_history_turns}"
        )
    
    def retrieve(
        self,
        query: str,
        history: list[ConversationTurn] | None = None,
        n_results: int = 10,
        filters: dict[str, Any] | None = None
    ) -> EnhancedRetrievalResult:
        """
        执行增强检索
        
        执行流程：
        1. 使用历史感知查询构建器构建增强查询（Requirement 3.1, 3.2, 3.4, 3.5）
        2. 调用知识库搜索获取原始结果
        3. 按相似度阈值过滤
        4. 限制每文档分块数
        5. 去重相似内容
        6. 排序结果
        
        Args:
            query: 用户查询
            history: 对话历史（可选，用于上下文增强）
            n_results: 期望返回结果数
            filters: 过滤条件（传递给知识库搜索）
            
        Returns:
            EnhancedRetrievalResult 包含过滤、去重、排序后的结果
        
        Requirements:
            - 1.2, 1.3, 1.4: 相似度阈值过滤
            - 2.2, 2.3, 2.4: 每文档分块限制
            - 3.1, 3.2, 3.4, 3.5: 历史对话上下文支持
            - 4.1, 4.2: 内容去重
            - 4.3, 4.4, 4.5: 结果排序
        """
        if not query or not query.strip():
            return EnhancedRetrievalResult()
        
        # 1. 使用历史感知查询构建器构建增强查询
        # Requirement 3.1: 接受可选的对话历史作为输入
        # Requirement 3.2: 使用对话历史增强查询理解和检索
        # Requirement 3.4: 历史超过 max_history_turns 时只使用最近的轮次
        # Requirement 3.5: 历史为空或未提供时，不使用历史上下文处理查询
        enhanced_query = self.query_builder.build_query(
            current_query=query,
            history=history,
            max_turns=self.config.max_history_turns
        )
        
        # 2. 从知识库获取原始结果
        # 请求更多结果以便过滤后仍有足够数量
        raw_results = self.kb.search(
            query=enhanced_query,
            n_results=n_results * 3,  # 请求更多以便过滤
            filters=filters
        )
        
        # 转换为 ChunkResult 列表
        chunks = [
            ChunkResult(
                doc_id=r.get("doc_id", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                metadata=r.get("metadata", {})
            )
            for r in raw_results
        ]
        
        total_before_filter = len(chunks)
        
        # 3. 按相似度阈值过滤
        chunks = self._filter_by_threshold(chunks)
        total_after_filter = len(chunks)
        
        # 4. 限制每文档分块数
        chunks = self._limit_per_document(chunks)
        
        # 5. 去重相似内容（将在后续任务实现）
        chunks_before_dedup = len(chunks)
        chunks = self._deduplicate(chunks)
        deduplicated_count = chunks_before_dedup - len(chunks)
        
        # 6. 排序结果（将在后续任务实现）
        chunks = self._sort_results(chunks)
        
        # 7. 限制返回数量
        chunks = chunks[:n_results]
        
        logger.debug(
            f"Enhanced retrieval: query='{query[:50]}...', "
            f"enhanced_query='{enhanced_query[:50]}...', "
            f"history_turns={len(history) if history else 0}, "
            f"before_filter={total_before_filter}, "
            f"after_filter={total_after_filter}, "
            f"deduplicated={deduplicated_count}, "
            f"final={len(chunks)}"
        )
        
        return EnhancedRetrievalResult(
            chunks=chunks,
            total_before_filter=total_before_filter,
            total_after_filter=total_after_filter,
            deduplicated_count=deduplicated_count
        )
    
    def _filter_by_threshold(self, results: list[ChunkResult]) -> list[ChunkResult]:
        """
        按相似度阈值过滤
        
        根据配置的 similarity_threshold 过滤检索结果：
        - 当 threshold = 0 时，返回所有结果（不过滤）
        - 当 threshold = 1 时，只返回精确匹配（score = 1.0）
        - 其他情况，返回 score >= threshold 的结果
        
        Args:
            results: 原始检索结果列表
            
        Returns:
            过滤后的结果列表
        
        Requirements:
            - 1.2: 过滤低于阈值的结果
            - 1.3: 阈值为 0 时返回所有结果
            - 1.4: 阈值为 1 时只返回精确匹配
        """
        threshold = self.config.similarity_threshold
        
        # 阈值为 0 时，返回所有结果
        if threshold == 0:
            return results
        
        # 阈值为 1 时，只返回精确匹配（score = 1.0）
        if threshold == 1:
            return [r for r in results if r.score == 1.0]
        
        # 其他情况，返回 score >= threshold 的结果
        return [r for r in results if r.score >= threshold]
    
    def _limit_per_document(self, results: list[ChunkResult]) -> list[ChunkResult]:
        """
        限制每文档分块数
        
        按文档 ID (article_id) 分组，每个文档只保留最高分的 N 个分块。
        当 max_chunks_per_doc = 0 时，不限制（返回所有分块）。
        
        算法：
        1. 按 article_id 分组所有分块
        2. 对每个文档的分块按分数降序排序
        3. 保留每个文档的前 N 个分块（N = max_chunks_per_doc）
        4. 合并所有保留的分块，保持原始相对顺序
        
        Args:
            results: 检索结果列表
            
        Returns:
            限制后的结果列表，保持原始相对顺序
        
        Requirements:
            - 2.2: 限制每文档分块数
            - 2.3: max_chunks_per_doc = 0 时不限制
            - 2.4: 保留最高分的分块
        
        Property 3: Per-Document Chunk Limiting
            *For any* retrieval operation with max_chunks_per_doc > 0, 
            *for each* unique source document in the results, 
            the count of chunks from that document SHALL be <= max_chunks_per_doc, 
            AND the kept chunks SHALL be those with the highest scores from that document.
        """
        # 如果 max_chunks_per_doc = 0，不限制（Requirement 2.3）
        if self.config.max_chunks_per_doc == 0:
            return results
        
        # 如果结果为空，直接返回
        if not results:
            return results
        
        max_per_doc = self.config.max_chunks_per_doc
        
        # 按 article_id 分组
        doc_chunks: dict[str, list[ChunkResult]] = {}
        for chunk in results:
            article_id = chunk.article_id
            if article_id not in doc_chunks:
                doc_chunks[article_id] = []
            doc_chunks[article_id].append(chunk)
        
        # 对每个文档的分块按分数降序排序，保留前 N 个
        # 使用集合记录每个文档保留的分块
        kept_chunks: set[str] = set()  # 使用 doc_id 作为标识
        
        for article_id, chunks in doc_chunks.items():
            # 按分数降序排序（Requirement 2.4: 优先保留高分块）
            sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)
            # 保留前 max_per_doc 个
            for chunk in sorted_chunks[:max_per_doc]:
                kept_chunks.add(chunk.doc_id)
        
        # 过滤结果，保持原始顺序
        limited_results = [
            chunk for chunk in results
            if chunk.doc_id in kept_chunks
        ]
        
        logger.debug(
            f"Per-document limit: max_per_doc={max_per_doc}, "
            f"documents={len(doc_chunks)}, "
            f"before={len(results)}, after={len(limited_results)}"
        )
        
        return limited_results
    
    def _deduplicate(self, results: list[ChunkResult]) -> list[ChunkResult]:
        """
        去重相似内容
        
        移除内容相似度高于 dedup_threshold 的重复分块，
        保留分数较高的分块。
        
        算法：
        1. 按相关性分数降序排序结果
        2. 遍历排序后的结果，对于每个分块：
           - 计算与已保留分块的内容相似度
           - 如果与任何已保留分块的相似度 > dedup_threshold，则跳过
           - 否则将该分块加入保留列表
        3. 返回保留的分块列表
        
        Args:
            results: 检索结果列表
            
        Returns:
            去重后的结果列表
        
        Requirements:
            - 4.1: 基于内容相似度去重
            - 4.2: 保留高分块
        
        Property 6: Content Deduplication
            *For any* set of retrieval results after deduplication, 
            *no two* chunks SHALL have content similarity > 0.95. 
            When similar chunks exist, the one with the higher relevance score SHALL be retained.
        """
        # 如果结果为空或只有一个，无需去重
        if len(results) <= 1:
            return results
        
        threshold = self.config.dedup_threshold
        
        # 按分数降序排序，确保高分块优先被保留
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        
        # 保留的分块列表
        kept_chunks: list[ChunkResult] = []
        # 保留分块的内容列表（用于相似度计算）
        kept_contents: list[str] = []
        
        for chunk in sorted_results:
            # 检查与已保留分块的相似度
            is_duplicate = False
            
            for kept_content in kept_contents:
                similarity = self._compute_content_similarity(chunk.content, kept_content)
                if similarity > threshold:
                    is_duplicate = True
                    logger.debug(
                        f"Dedup: chunk '{chunk.doc_id}' (score={chunk.score:.3f}) "
                        f"is similar to kept chunk (similarity={similarity:.3f})"
                    )
                    break
            
            if not is_duplicate:
                kept_chunks.append(chunk)
                kept_contents.append(chunk.content)
        
        logger.debug(
            f"Deduplication: threshold={threshold}, "
            f"before={len(results)}, after={len(kept_chunks)}, "
            f"removed={len(results) - len(kept_chunks)}"
        )
        
        return kept_chunks
    
    def _compute_content_similarity(self, content1: str, content2: str) -> float:
        """
        计算两个内容之间的相似度
        
        使用余弦相似度计算两个文本的语义相似度。
        为了效率，首先使用简单的字符级 Jaccard 相似度进行快速筛选，
        如果 Jaccard 相似度较高，再使用 embedding 进行精确计算。
        
        Args:
            content1: 第一个内容
            content2: 第二个内容
            
        Returns:
            相似度分数 [0, 1]
        """
        # 处理空内容
        if not content1 or not content2:
            return 0.0
        
        # 完全相同的内容
        if content1 == content2:
            return 1.0
        
        # 使用字符级 Jaccard 相似度进行快速筛选
        jaccard = self._jaccard_similarity(content1, content2)
        
        # 如果 Jaccard 相似度很低，直接返回（优化性能）
        if jaccard < 0.3:
            return jaccard
        
        # 如果 Jaccard 相似度很高，可能是重复内容
        if jaccard > 0.9:
            return jaccard
        
        # 对于中等相似度，使用更精确的方法
        # 这里使用基于词的 Jaccard 相似度作为近似
        # 避免调用 embedding API 以提高性能
        word_jaccard = self._word_jaccard_similarity(content1, content2)
        
        return word_jaccard
    
    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """
        计算字符级 Jaccard 相似度
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
            
        Returns:
            Jaccard 相似度 [0, 1]
        """
        # 使用 n-gram (n=3) 进行比较
        n = 3
        
        def get_ngrams(text: str, n: int) -> set[str]:
            """获取文本的 n-gram 集合"""
            text = text.lower().strip()
            if len(text) < n:
                return {text}
            return {text[i:i+n] for i in range(len(text) - n + 1)}
        
        ngrams1 = get_ngrams(text1, n)
        ngrams2 = get_ngrams(text2, n)
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        
        return intersection / union if union > 0 else 0.0
    
    def _word_jaccard_similarity(self, text1: str, text2: str) -> float:
        """
        计算词级 Jaccard 相似度
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
            
        Returns:
            Jaccard 相似度 [0, 1]
        """
        import re
        
        def tokenize(text: str) -> set[str]:
            """简单分词"""
            # 转小写并提取词
            words = re.findall(r'\b\w+\b', text.lower())
            return set(words)
        
        words1 = tokenize(text1)
        words2 = tokenize(text2)
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _sort_results(self, results: list[ChunkResult]) -> list[ChunkResult]:
        """
        排序结果
        
        主排序：相关性分数降序
        次排序：来源多样性（相同分数时优先不同来源）
        
        算法：
        1. 按相关性分数降序排序（主排序）
        2. 对于相同分数的结果，使用来源多样性作为次排序：
           - 在同一分数组内，优先选择来自不同来源的结果
           - 使用轮询方式从不同来源中选择结果
        
        来源多样性排序逻辑：
        - 使用稳定排序，先按分数降序排序
        - 然后对相同分数的组进行重排，优先放置来自不同来源的结果
        - 在同一分数组内，使用轮询方式确保来源多样性
        
        Args:
            results: 检索结果列表
            
        Returns:
            排序后的结果列表
        
        Requirements:
            - 4.3: 按相关性分数降序排序
            - 4.4: 次排序考虑来源多样性
        
        Property 7: Result Ordering
            *For any* final retrieval results list, the relevance scores 
            SHALL be in non-increasing (descending) order.
        """
        if not results:
            return results
        
        if len(results) == 1:
            return results
        
        # 第一步：按分数降序排序（主排序）
        sorted_by_score = sorted(results, key=lambda r: r.score, reverse=True)
        
        # 第二步：对相同分数的组应用来源多样性排序
        # 将结果按分数分组
        score_groups: dict[float, list[ChunkResult]] = {}
        for chunk in sorted_by_score:
            if chunk.score not in score_groups:
                score_groups[chunk.score] = []
            score_groups[chunk.score].append(chunk)
        
        # 按分数降序获取所有分数
        sorted_scores = sorted(score_groups.keys(), reverse=True)
        
        # 构建最终结果，对每个分数组应用来源多样性排序
        final_results: list[ChunkResult] = []
        global_seen_sources: set[str] = set()  # 跟踪全局已出现的来源
        
        for score in sorted_scores:
            group = score_groups[score]
            
            if len(group) == 1:
                # 只有一个结果，直接添加
                final_results.append(group[0])
                global_seen_sources.add(group[0].article_id)
            else:
                # 多个相同分数的结果，应用来源多样性排序
                # 按来源分组
                source_chunks: dict[str, list[ChunkResult]] = {}
                for chunk in group:
                    article_id = chunk.article_id
                    if article_id not in source_chunks:
                        source_chunks[article_id] = []
                    source_chunks[article_id].append(chunk)
                
                # 对来源进行排序：优先选择全局未见过的来源
                new_sources = [s for s in source_chunks.keys() if s not in global_seen_sources]
                seen_sources = [s for s in source_chunks.keys() if s in global_seen_sources]
                ordered_sources = new_sources + seen_sources
                
                # 使用轮询方式从各来源中选择结果，确保来源多样性
                # 每轮从每个来源取一个结果，直到所有结果都被取完
                source_iterators = {s: iter(chunks) for s, chunks in source_chunks.items()}
                
                while source_iterators:
                    exhausted_sources = []
                    for source in ordered_sources:
                        if source not in source_iterators:
                            continue
                        try:
                            chunk = next(source_iterators[source])
                            final_results.append(chunk)
                            global_seen_sources.add(source)
                        except StopIteration:
                            exhausted_sources.append(source)
                    
                    # 移除已耗尽的来源
                    for source in exhausted_sources:
                        del source_iterators[source]
                        ordered_sources = [s for s in ordered_sources if s != source]
        
        logger.debug(
            f"Sort results: total={len(results)}, "
            f"unique_scores={len(sorted_scores)}, "
            f"unique_sources={len(global_seen_sources)}"
        )
        
        return final_results
    
    def to_retrieval_results(
        self,
        enhanced_result: EnhancedRetrievalResult
    ) -> list[RetrievalResult]:
        """
        将增强检索结果转换为标准 RetrievalResult 列表
        
        用于与现有 QAEngine 集成。
        
        Args:
            enhanced_result: 增强检索结果
            
        Returns:
            RetrievalResult 列表
        """
        return [
            RetrievalResult(
                doc_id=chunk.doc_id,
                content=chunk.content,
                score=chunk.score,
                metadata=chunk.metadata
            )
            for chunk in enhanced_result.chunks
        ]
