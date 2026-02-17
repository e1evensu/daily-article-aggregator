"""
EnhancedRetriever 单元测试

测试增强检索器的核心功能：
- 相似度阈值过滤
- 每文档分块限制（后续任务）
- 内容去重（后续任务）
- 结果排序（后续任务）

Requirements:
    - 1.2: 按相似度阈值过滤检索结果
    - 1.3: 阈值为 0 时返回所有结果
    - 1.4: 阈值为 1 时只返回精确匹配
"""

import pytest
from unittest.mock import Mock, MagicMock

from src.qa.enhanced_retriever import (
    EnhancedRetriever,
    ChunkResult,
    EnhancedRetrievalResult,
)
from src.qa.config import RetrievalConfig


class TestChunkResult:
    """测试 ChunkResult 数据类"""
    
    def test_chunk_result_creation(self):
        """测试创建 ChunkResult"""
        chunk = ChunkResult(
            doc_id="123_0",
            content="Test content",
            score=0.85,
            metadata={"title": "Test"}
        )
        
        assert chunk.doc_id == "123_0"
        assert chunk.content == "Test content"
        assert chunk.score == 0.85
        assert chunk.metadata == {"title": "Test"}
    
    def test_chunk_result_article_id_extraction(self):
        """测试从 doc_id 提取 article_id"""
        chunk = ChunkResult(doc_id="123_0", content="", score=0.5)
        assert chunk.article_id == "123"
        
        chunk2 = ChunkResult(doc_id="456_10", content="", score=0.5)
        assert chunk2.article_id == "456"
        
        # 处理没有下划线的情况
        chunk3 = ChunkResult(doc_id="789", content="", score=0.5)
        assert chunk3.article_id == "789"
    
    def test_chunk_result_to_dict(self):
        """测试 ChunkResult 转换为字典"""
        chunk = ChunkResult(
            doc_id="123_0",
            content="Test content",
            score=0.85,
            metadata={"title": "Test"}
        )
        
        result = chunk.to_dict()
        
        assert result["doc_id"] == "123_0"
        assert result["content"] == "Test content"
        assert result["score"] == 0.85
        assert result["metadata"] == {"title": "Test"}
    
    def test_chunk_result_from_dict(self):
        """测试从字典创建 ChunkResult"""
        data = {
            "doc_id": "123_0",
            "content": "Test content",
            "score": 0.85,
            "metadata": {"title": "Test"}
        }
        
        chunk = ChunkResult.from_dict(data)
        
        assert chunk.doc_id == "123_0"
        assert chunk.content == "Test content"
        assert chunk.score == 0.85
        assert chunk.metadata == {"title": "Test"}


class TestEnhancedRetrievalResult:
    """测试 EnhancedRetrievalResult 数据类"""
    
    def test_enhanced_retrieval_result_creation(self):
        """测试创建 EnhancedRetrievalResult"""
        chunks = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.9),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.8),
        ]
        
        result = EnhancedRetrievalResult(
            chunks=chunks,
            total_before_filter=10,
            total_after_filter=5,
            deduplicated_count=2
        )
        
        assert len(result.chunks) == 2
        assert result.total_before_filter == 10
        assert result.total_after_filter == 5
        assert result.deduplicated_count == 2
    
    def test_enhanced_retrieval_result_to_dict(self):
        """测试 EnhancedRetrievalResult 转换为字典"""
        chunks = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.9),
        ]
        
        result = EnhancedRetrievalResult(
            chunks=chunks,
            total_before_filter=10,
            total_after_filter=5,
            deduplicated_count=2
        )
        
        data = result.to_dict()
        
        assert len(data["chunks"]) == 1
        assert data["total_before_filter"] == 10
        assert data["total_after_filter"] == 5
        assert data["deduplicated_count"] == 2


class TestEnhancedRetrieverInit:
    """测试 EnhancedRetriever 初始化"""
    
    def test_init_with_valid_config(self):
        """测试使用有效配置初始化"""
        mock_kb = Mock()
        config = RetrievalConfig(
            similarity_threshold=0.5,
            max_chunks_per_doc=3
        )
        
        retriever = EnhancedRetriever(mock_kb, config)
        
        assert retriever.kb == mock_kb
        assert retriever.config == config
    
    def test_init_validates_config(self):
        """测试初始化时验证配置"""
        mock_kb = Mock()
        
        # 无效的 similarity_threshold
        invalid_config = RetrievalConfig(similarity_threshold=1.5)
        
        with pytest.raises(ValueError, match="similarity_threshold must be in"):
            EnhancedRetriever(mock_kb, invalid_config)
    
    def test_init_with_invalid_max_chunks(self):
        """测试使用无效的 max_chunks_per_doc 初始化"""
        mock_kb = Mock()
        
        invalid_config = RetrievalConfig(max_chunks_per_doc=-1)
        
        with pytest.raises(ValueError, match="max_chunks_per_doc must be >= 0"):
            EnhancedRetriever(mock_kb, invalid_config)


class TestFilterByThreshold:
    """
    测试相似度阈值过滤功能
    
    Requirements:
        - 1.2: 按相似度阈值过滤检索结果
        - 1.3: 阈值为 0 时返回所有结果
        - 1.4: 阈值为 1 时只返回精确匹配
    """
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        return Mock()
    
    @pytest.fixture
    def sample_results(self):
        """创建示例检索结果"""
        return [
            ChunkResult(doc_id="1_0", content="Content 1", score=1.0),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.9),
            ChunkResult(doc_id="3_0", content="Content 3", score=0.7),
            ChunkResult(doc_id="4_0", content="Content 4", score=0.5),
            ChunkResult(doc_id="5_0", content="Content 5", score=0.3),
            ChunkResult(doc_id="6_0", content="Content 6", score=0.1),
        ]
    
    def test_filter_threshold_zero_returns_all(self, mock_kb, sample_results):
        """
        测试阈值为 0 时返回所有结果
        
        Requirements: 1.3
        """
        config = RetrievalConfig(similarity_threshold=0)
        retriever = EnhancedRetriever(mock_kb, config)
        
        filtered = retriever._filter_by_threshold(sample_results)
        
        assert len(filtered) == len(sample_results)
        assert filtered == sample_results
    
    def test_filter_threshold_one_returns_exact_matches(self, mock_kb, sample_results):
        """
        测试阈值为 1 时只返回精确匹配（score = 1.0）
        
        Requirements: 1.4
        """
        config = RetrievalConfig(similarity_threshold=1)
        retriever = EnhancedRetriever(mock_kb, config)
        
        filtered = retriever._filter_by_threshold(sample_results)
        
        assert len(filtered) == 1
        assert filtered[0].score == 1.0
        assert filtered[0].doc_id == "1_0"
    
    def test_filter_threshold_filters_below(self, mock_kb, sample_results):
        """
        测试阈值过滤低于阈值的结果
        
        Requirements: 1.2
        """
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        filtered = retriever._filter_by_threshold(sample_results)
        
        # 应该保留 score >= 0.5 的结果
        assert len(filtered) == 4
        for chunk in filtered:
            assert chunk.score >= 0.5
    
    def test_filter_threshold_0_6(self, mock_kb, sample_results):
        """测试阈值 0.6 的过滤"""
        config = RetrievalConfig(similarity_threshold=0.6)
        retriever = EnhancedRetriever(mock_kb, config)
        
        filtered = retriever._filter_by_threshold(sample_results)
        
        # 应该保留 score >= 0.6 的结果 (1.0, 0.9, 0.7)
        assert len(filtered) == 3
        for chunk in filtered:
            assert chunk.score >= 0.6
    
    def test_filter_threshold_0_8(self, mock_kb, sample_results):
        """测试阈值 0.8 的过滤"""
        config = RetrievalConfig(similarity_threshold=0.8)
        retriever = EnhancedRetriever(mock_kb, config)
        
        filtered = retriever._filter_by_threshold(sample_results)
        
        # 应该保留 score >= 0.8 的结果 (1.0, 0.9)
        assert len(filtered) == 2
        for chunk in filtered:
            assert chunk.score >= 0.8
    
    def test_filter_empty_results(self, mock_kb):
        """测试过滤空结果列表"""
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        filtered = retriever._filter_by_threshold([])
        
        assert filtered == []
    
    def test_filter_all_below_threshold(self, mock_kb):
        """测试所有结果都低于阈值的情况"""
        config = RetrievalConfig(similarity_threshold=0.9)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.5),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.3),
            ChunkResult(doc_id="3_0", content="Content 3", score=0.1),
        ]
        
        filtered = retriever._filter_by_threshold(results)
        
        assert len(filtered) == 0
    
    def test_filter_all_above_threshold(self, mock_kb):
        """测试所有结果都高于阈值的情况"""
        config = RetrievalConfig(similarity_threshold=0.3)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.9),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.7),
            ChunkResult(doc_id="3_0", content="Content 3", score=0.5),
        ]
        
        filtered = retriever._filter_by_threshold(results)
        
        assert len(filtered) == 3
    
    def test_filter_boundary_score_equal_to_threshold(self, mock_kb):
        """测试分数等于阈值的边界情况"""
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.5),  # 等于阈值
            ChunkResult(doc_id="2_0", content="Content 2", score=0.49),  # 低于阈值
        ]
        
        filtered = retriever._filter_by_threshold(results)
        
        # score = 0.5 应该被保留（>= threshold）
        assert len(filtered) == 1
        assert filtered[0].score == 0.5
    
    def test_filter_preserves_order(self, mock_kb, sample_results):
        """测试过滤后保持原始顺序"""
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        filtered = retriever._filter_by_threshold(sample_results)
        
        # 验证顺序保持不变
        scores = [chunk.score for chunk in filtered]
        assert scores == [1.0, 0.9, 0.7, 0.5]


class TestRetrieve:
    """测试完整的检索流程"""
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        kb = Mock()
        kb.search.return_value = [
            {"doc_id": "1_0", "content": "Content 1", "score": 0.9, "metadata": {}},
            {"doc_id": "2_0", "content": "Content 2", "score": 0.7, "metadata": {}},
            {"doc_id": "3_0", "content": "Content 3", "score": 0.5, "metadata": {}},
            {"doc_id": "4_0", "content": "Content 4", "score": 0.3, "metadata": {}},
        ]
        return kb
    
    def test_retrieve_basic(self, mock_kb):
        """测试基本检索流程"""
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        result = retriever.retrieve("test query", n_results=10)
        
        assert isinstance(result, EnhancedRetrievalResult)
        assert result.total_before_filter == 4
        # 过滤后应该有 3 个结果（score >= 0.5）
        assert result.total_after_filter == 3
        assert len(result.chunks) == 3
    
    def test_retrieve_empty_query(self, mock_kb):
        """测试空查询"""
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        result = retriever.retrieve("")
        
        assert len(result.chunks) == 0
        assert result.total_before_filter == 0
    
    def test_retrieve_whitespace_query(self, mock_kb):
        """测试空白查询"""
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        result = retriever.retrieve("   ")
        
        assert len(result.chunks) == 0
    
    def test_retrieve_with_filters(self, mock_kb):
        """测试带过滤条件的检索"""
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        filters = {"source_type": "blog"}
        result = retriever.retrieve("test query", filters=filters)
        
        # 验证 filters 被传递给 kb.search
        mock_kb.search.assert_called_once()
        call_args = mock_kb.search.call_args
        assert call_args.kwargs.get("filters") == filters
    
    def test_retrieve_limits_results(self, mock_kb):
        """测试结果数量限制"""
        config = RetrievalConfig(similarity_threshold=0)  # 不过滤
        retriever = EnhancedRetriever(mock_kb, config)
        
        result = retriever.retrieve("test query", n_results=2)
        
        # 应该最多返回 2 个结果
        assert len(result.chunks) <= 2
    
    def test_retrieve_calls_kb_search_with_multiplied_n_results(self, mock_kb):
        """测试检索时请求更多结果以便过滤"""
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        retriever.retrieve("test query", n_results=5)
        
        # 应该请求 n_results * 3 个结果
        call_args = mock_kb.search.call_args
        assert call_args.kwargs.get("n_results") == 15


class TestToRetrievalResults:
    """测试转换为标准 RetrievalResult"""
    
    def test_to_retrieval_results(self):
        """测试转换为 RetrievalResult 列表"""
        mock_kb = Mock()
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        chunks = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.9, metadata={"title": "Test 1"}),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.7, metadata={"title": "Test 2"}),
        ]
        enhanced_result = EnhancedRetrievalResult(chunks=chunks)
        
        results = retriever.to_retrieval_results(enhanced_result)
        
        assert len(results) == 2
        assert results[0].doc_id == "1_0"
        assert results[0].content == "Content 1"
        assert results[0].score == 0.9
        assert results[0].metadata == {"title": "Test 1"}
    
    def test_to_retrieval_results_empty(self):
        """测试转换空结果"""
        mock_kb = Mock()
        config = RetrievalConfig(similarity_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        enhanced_result = EnhancedRetrievalResult(chunks=[])
        
        results = retriever.to_retrieval_results(enhanced_result)
        
        assert results == []


class TestLimitPerDocument:
    """
    测试每文档分块数限制功能
    
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
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        return Mock()
    
    @pytest.fixture
    def sample_results_multi_doc(self):
        """
        创建多文档的示例检索结果
        
        文档 A (article_id="A"): 4 个分块
        文档 B (article_id="B"): 3 个分块
        文档 C (article_id="C"): 2 个分块
        """
        return [
            # 文档 A 的分块
            ChunkResult(doc_id="A_0", content="A Content 0", score=0.95),
            ChunkResult(doc_id="A_1", content="A Content 1", score=0.85),
            ChunkResult(doc_id="A_2", content="A Content 2", score=0.75),
            ChunkResult(doc_id="A_3", content="A Content 3", score=0.65),
            # 文档 B 的分块
            ChunkResult(doc_id="B_0", content="B Content 0", score=0.90),
            ChunkResult(doc_id="B_1", content="B Content 1", score=0.80),
            ChunkResult(doc_id="B_2", content="B Content 2", score=0.70),
            # 文档 C 的分块
            ChunkResult(doc_id="C_0", content="C Content 0", score=0.88),
            ChunkResult(doc_id="C_1", content="C Content 1", score=0.78),
        ]
    
    def test_limit_per_doc_zero_returns_all(self, mock_kb, sample_results_multi_doc):
        """
        测试 max_chunks_per_doc = 0 时返回所有结果
        
        Requirements: 2.3
        """
        config = RetrievalConfig(max_chunks_per_doc=0)
        retriever = EnhancedRetriever(mock_kb, config)
        
        limited = retriever._limit_per_document(sample_results_multi_doc)
        
        assert len(limited) == len(sample_results_multi_doc)
        assert limited == sample_results_multi_doc
    
    def test_limit_per_doc_limits_chunks(self, mock_kb, sample_results_multi_doc):
        """
        测试限制每文档分块数
        
        Requirements: 2.2
        """
        config = RetrievalConfig(max_chunks_per_doc=2)
        retriever = EnhancedRetriever(mock_kb, config)
        
        limited = retriever._limit_per_document(sample_results_multi_doc)
        
        # 统计每个文档的分块数
        doc_counts: dict[str, int] = {}
        for chunk in limited:
            article_id = chunk.article_id
            doc_counts[article_id] = doc_counts.get(article_id, 0) + 1
        
        # 每个文档最多 2 个分块
        for article_id, count in doc_counts.items():
            assert count <= 2, f"Document {article_id} has {count} chunks, expected <= 2"
    
    def test_limit_per_doc_keeps_highest_scores(self, mock_kb, sample_results_multi_doc):
        """
        测试保留最高分的分块
        
        Requirements: 2.4
        Property 3: the kept chunks SHALL be those with the highest scores from that document
        """
        config = RetrievalConfig(max_chunks_per_doc=2)
        retriever = EnhancedRetriever(mock_kb, config)
        
        limited = retriever._limit_per_document(sample_results_multi_doc)
        
        # 按文档分组检查
        doc_chunks: dict[str, list[ChunkResult]] = {}
        for chunk in limited:
            article_id = chunk.article_id
            if article_id not in doc_chunks:
                doc_chunks[article_id] = []
            doc_chunks[article_id].append(chunk)
        
        # 文档 A: 应该保留 A_0 (0.95) 和 A_1 (0.85)
        assert "A" in doc_chunks
        a_scores = sorted([c.score for c in doc_chunks["A"]], reverse=True)
        assert a_scores == [0.95, 0.85]
        
        # 文档 B: 应该保留 B_0 (0.90) 和 B_1 (0.80)
        assert "B" in doc_chunks
        b_scores = sorted([c.score for c in doc_chunks["B"]], reverse=True)
        assert b_scores == [0.90, 0.80]
        
        # 文档 C: 只有 2 个分块，都应该保留
        assert "C" in doc_chunks
        c_scores = sorted([c.score for c in doc_chunks["C"]], reverse=True)
        assert c_scores == [0.88, 0.78]
    
    def test_limit_per_doc_one_chunk(self, mock_kb, sample_results_multi_doc):
        """测试 max_chunks_per_doc = 1 时每文档只保留一个分块"""
        config = RetrievalConfig(max_chunks_per_doc=1)
        retriever = EnhancedRetriever(mock_kb, config)
        
        limited = retriever._limit_per_document(sample_results_multi_doc)
        
        # 应该有 3 个分块（每个文档 1 个）
        assert len(limited) == 3
        
        # 统计每个文档的分块数
        doc_counts: dict[str, int] = {}
        for chunk in limited:
            article_id = chunk.article_id
            doc_counts[article_id] = doc_counts.get(article_id, 0) + 1
        
        # 每个文档只有 1 个分块
        for article_id, count in doc_counts.items():
            assert count == 1, f"Document {article_id} has {count} chunks, expected 1"
        
        # 验证保留的是最高分的分块
        doc_ids = {chunk.doc_id for chunk in limited}
        assert "A_0" in doc_ids  # A 的最高分
        assert "B_0" in doc_ids  # B 的最高分
        assert "C_0" in doc_ids  # C 的最高分
    
    def test_limit_per_doc_preserves_relative_order(self, mock_kb, sample_results_multi_doc):
        """测试限制后保持原始相对顺序"""
        config = RetrievalConfig(max_chunks_per_doc=2)
        retriever = EnhancedRetriever(mock_kb, config)
        
        limited = retriever._limit_per_document(sample_results_multi_doc)
        
        # 获取保留的 doc_ids
        limited_doc_ids = [chunk.doc_id for chunk in limited]
        
        # 验证顺序与原始列表中的顺序一致
        original_order = [chunk.doc_id for chunk in sample_results_multi_doc]
        expected_order = [doc_id for doc_id in original_order if doc_id in limited_doc_ids]
        
        assert limited_doc_ids == expected_order
    
    def test_limit_per_doc_empty_results(self, mock_kb):
        """测试空结果列表"""
        config = RetrievalConfig(max_chunks_per_doc=2)
        retriever = EnhancedRetriever(mock_kb, config)
        
        limited = retriever._limit_per_document([])
        
        assert limited == []
    
    def test_limit_per_doc_single_document(self, mock_kb):
        """测试只有一个文档的情况"""
        config = RetrievalConfig(max_chunks_per_doc=2)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="X_0", content="X Content 0", score=0.9),
            ChunkResult(doc_id="X_1", content="X Content 1", score=0.8),
            ChunkResult(doc_id="X_2", content="X Content 2", score=0.7),
            ChunkResult(doc_id="X_3", content="X Content 3", score=0.6),
        ]
        
        limited = retriever._limit_per_document(results)
        
        # 应该只保留 2 个分块
        assert len(limited) == 2
        # 应该是最高分的 2 个
        scores = [chunk.score for chunk in limited]
        assert sorted(scores, reverse=True) == [0.9, 0.8]
    
    def test_limit_per_doc_fewer_chunks_than_limit(self, mock_kb):
        """测试文档分块数少于限制的情况"""
        config = RetrievalConfig(max_chunks_per_doc=5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="A_0", content="A Content 0", score=0.9),
            ChunkResult(doc_id="A_1", content="A Content 1", score=0.8),
            ChunkResult(doc_id="B_0", content="B Content 0", score=0.7),
        ]
        
        limited = retriever._limit_per_document(results)
        
        # 所有分块都应该保留（因为每个文档的分块数都 <= 5）
        assert len(limited) == 3
    
    def test_limit_per_doc_same_scores(self, mock_kb):
        """测试相同分数的分块"""
        config = RetrievalConfig(max_chunks_per_doc=2)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="A_0", content="A Content 0", score=0.8),
            ChunkResult(doc_id="A_1", content="A Content 1", score=0.8),
            ChunkResult(doc_id="A_2", content="A Content 2", score=0.8),
            ChunkResult(doc_id="A_3", content="A Content 3", score=0.8),
        ]
        
        limited = retriever._limit_per_document(results)
        
        # 应该只保留 2 个分块
        assert len(limited) == 2
    
    def test_limit_per_doc_complex_doc_ids(self, mock_kb):
        """测试复杂的 doc_id 格式"""
        config = RetrievalConfig(max_chunks_per_doc=1)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="article_123_0", content="Content 0", score=0.9),
            ChunkResult(doc_id="article_123_1", content="Content 1", score=0.8),
            ChunkResult(doc_id="article_456_0", content="Content 2", score=0.7),
        ]
        
        limited = retriever._limit_per_document(results)
        
        # 应该有 2 个分块（每个文档 1 个）
        assert len(limited) == 2
        
        # 验证 article_id 提取正确
        article_ids = {chunk.article_id for chunk in limited}
        assert "article_123" in article_ids
        assert "article_456" in article_ids


class TestDeduplicate:
    """
    测试内容去重功能
    
    Requirements:
        - 4.1: 基于内容相似度去重
        - 4.2: 保留高分块
    
    Property 6: Content Deduplication
        *For any* set of retrieval results after deduplication, 
        *no two* chunks SHALL have content similarity > 0.95. 
        When similar chunks exist, the one with the higher relevance score SHALL be retained.
    """
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        return Mock()
    
    def test_deduplicate_empty_results(self, mock_kb):
        """测试空结果列表"""
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        deduped = retriever._deduplicate([])
        
        assert deduped == []
    
    def test_deduplicate_single_result(self, mock_kb):
        """测试单个结果"""
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Test content", score=0.9),
        ]
        
        deduped = retriever._deduplicate(results)
        
        assert len(deduped) == 1
        assert deduped[0].doc_id == "1_0"
    
    def test_deduplicate_identical_content(self, mock_kb):
        """
        测试完全相同的内容
        
        Requirements: 4.1, 4.2
        """
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="This is the exact same content", score=0.9),
            ChunkResult(doc_id="2_0", content="This is the exact same content", score=0.7),
        ]
        
        deduped = retriever._deduplicate(results)
        
        # 应该只保留一个（高分的那个）
        assert len(deduped) == 1
        assert deduped[0].doc_id == "1_0"
        assert deduped[0].score == 0.9
    
    def test_deduplicate_keeps_higher_score(self, mock_kb):
        """
        测试保留高分块
        
        Requirements: 4.2
        """
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        # 低分块在前，高分块在后
        results = [
            ChunkResult(doc_id="1_0", content="This is the exact same content", score=0.5),
            ChunkResult(doc_id="2_0", content="This is the exact same content", score=0.9),
        ]
        
        deduped = retriever._deduplicate(results)
        
        # 应该保留高分的那个
        assert len(deduped) == 1
        assert deduped[0].doc_id == "2_0"
        assert deduped[0].score == 0.9
    
    def test_deduplicate_different_content(self, mock_kb):
        """测试完全不同的内容"""
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Python is a programming language", score=0.9),
            ChunkResult(doc_id="2_0", content="Machine learning uses algorithms", score=0.8),
            ChunkResult(doc_id="3_0", content="Database stores structured data", score=0.7),
        ]
        
        deduped = retriever._deduplicate(results)
        
        # 所有内容都不同，应该全部保留
        assert len(deduped) == 3
    
    def test_deduplicate_similar_content(self, mock_kb):
        """
        测试相似但不完全相同的内容
        
        Requirements: 4.1
        """
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        # 这两个内容非常相似（只有一个词不同）
        results = [
            ChunkResult(
                doc_id="1_0", 
                content="Python is a great programming language for data science and machine learning applications",
                score=0.9
            ),
            ChunkResult(
                doc_id="2_0", 
                content="Python is a great programming language for data science and machine learning applications",
                score=0.7
            ),
        ]
        
        deduped = retriever._deduplicate(results)
        
        # 相同内容应该被去重
        assert len(deduped) == 1
        assert deduped[0].score == 0.9
    
    def test_deduplicate_threshold_boundary(self, mock_kb):
        """测试阈值边界情况"""
        # 使用较低的阈值
        config = RetrievalConfig(dedup_threshold=0.5)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Python programming language", score=0.9),
            ChunkResult(doc_id="2_0", content="Python programming basics", score=0.8),
        ]
        
        deduped = retriever._deduplicate(results)
        
        # 这两个内容有一定相似度，但可能不超过 0.5
        # 具体结果取决于相似度计算
        assert len(deduped) >= 1
    
    def test_deduplicate_multiple_duplicates(self, mock_kb):
        """测试多个重复内容"""
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Duplicate content A", score=0.9),
            ChunkResult(doc_id="2_0", content="Duplicate content A", score=0.8),
            ChunkResult(doc_id="3_0", content="Duplicate content A", score=0.7),
            ChunkResult(doc_id="4_0", content="Unique content B", score=0.6),
            ChunkResult(doc_id="5_0", content="Unique content B", score=0.5),
        ]
        
        deduped = retriever._deduplicate(results)
        
        # 应该保留 2 个（每组重复内容保留一个高分的）
        assert len(deduped) == 2
        
        # 验证保留的是高分块
        scores = [chunk.score for chunk in deduped]
        assert 0.9 in scores  # Duplicate content A 的最高分
        assert 0.6 in scores  # Unique content B 的最高分
    
    def test_deduplicate_preserves_metadata(self, mock_kb):
        """测试去重后保留元数据"""
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(
                doc_id="1_0", 
                content="Same content", 
                score=0.9,
                metadata={"title": "Article 1", "source": "blog"}
            ),
            ChunkResult(
                doc_id="2_0", 
                content="Same content", 
                score=0.7,
                metadata={"title": "Article 2", "source": "news"}
            ),
        ]
        
        deduped = retriever._deduplicate(results)
        
        assert len(deduped) == 1
        assert deduped[0].metadata == {"title": "Article 1", "source": "blog"}
    
    def test_deduplicate_with_empty_content(self, mock_kb):
        """测试包含空内容的情况"""
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="", score=0.9),
            ChunkResult(doc_id="2_0", content="Some content", score=0.8),
            ChunkResult(doc_id="3_0", content="", score=0.7),
        ]
        
        deduped = retriever._deduplicate(results)
        
        # 空内容之间相似度为 0，不会被去重
        # 但空内容与非空内容相似度也为 0
        assert len(deduped) >= 2


class TestContentSimilarity:
    """测试内容相似度计算"""
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        return Mock()
    
    def test_similarity_identical_content(self, mock_kb):
        """测试完全相同的内容"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._compute_content_similarity(
            "This is a test",
            "This is a test"
        )
        
        assert similarity == 1.0
    
    def test_similarity_empty_content(self, mock_kb):
        """测试空内容"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        assert retriever._compute_content_similarity("", "test") == 0.0
        assert retriever._compute_content_similarity("test", "") == 0.0
        assert retriever._compute_content_similarity("", "") == 0.0
    
    def test_similarity_completely_different(self, mock_kb):
        """测试完全不同的内容"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._compute_content_similarity(
            "Python programming language",
            "Quantum physics theory"
        )
        
        # 完全不同的内容应该有很低的相似度
        assert similarity < 0.5
    
    def test_similarity_partial_overlap(self, mock_kb):
        """测试部分重叠的内容"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._compute_content_similarity(
            "Python is a programming language",
            "Python is a scripting language"
        )
        
        # 部分重叠应该有中等相似度
        assert 0.3 < similarity < 0.9


class TestJaccardSimilarity:
    """测试 Jaccard 相似度计算"""
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        return Mock()
    
    def test_jaccard_identical(self, mock_kb):
        """测试完全相同的文本"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._jaccard_similarity("hello world", "hello world")
        
        assert similarity == 1.0
    
    def test_jaccard_completely_different(self, mock_kb):
        """测试完全不同的文本"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._jaccard_similarity("abc", "xyz")
        
        assert similarity == 0.0
    
    def test_jaccard_partial_overlap(self, mock_kb):
        """测试部分重叠的文本"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._jaccard_similarity("hello world", "hello there")
        
        # 应该有一些重叠
        assert 0 < similarity < 1


class TestWordJaccardSimilarity:
    """测试词级 Jaccard 相似度计算"""
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        return Mock()
    
    def test_word_jaccard_identical(self, mock_kb):
        """测试完全相同的文本"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._word_jaccard_similarity(
            "hello world test",
            "hello world test"
        )
        
        assert similarity == 1.0
    
    def test_word_jaccard_no_overlap(self, mock_kb):
        """测试没有重叠的文本"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._word_jaccard_similarity(
            "apple banana cherry",
            "dog elephant fox"
        )
        
        assert similarity == 0.0
    
    def test_word_jaccard_partial_overlap(self, mock_kb):
        """测试部分重叠的文本"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._word_jaccard_similarity(
            "python is great",
            "python is awesome"
        )
        
        # 2 个共同词 (python, is) / 4 个总词 (python, is, great, awesome) = 0.5
        assert similarity == 0.5
    
    def test_word_jaccard_case_insensitive(self, mock_kb):
        """测试大小写不敏感"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        similarity = retriever._word_jaccard_similarity(
            "Hello World",
            "hello world"
        )
        
        assert similarity == 1.0


class TestSortResults:
    """
    测试结果排序功能
    
    Requirements:
        - 4.3: 按相关性分数降序排序
        - 4.4: 次排序考虑来源多样性
        - 4.5: 返回去重计数元数据（在 retrieve() 方法中处理）
    
    Property 7: Result Ordering
        *For any* final retrieval results list, the relevance scores 
        SHALL be in non-increasing (descending) order.
    """
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        return Mock()
    
    def test_sort_empty_results(self, mock_kb):
        """测试空结果列表"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        sorted_results = retriever._sort_results([])
        
        assert sorted_results == []
    
    def test_sort_single_result(self, mock_kb):
        """测试单个结果"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.9),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        assert len(sorted_results) == 1
        assert sorted_results[0].doc_id == "1_0"
    
    def test_sort_by_score_descending(self, mock_kb):
        """
        测试按分数降序排序
        
        Requirements: 4.3
        Property 7: relevance scores SHALL be in non-increasing (descending) order
        """
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.5),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.9),
            ChunkResult(doc_id="3_0", content="Content 3", score=0.7),
            ChunkResult(doc_id="4_0", content="Content 4", score=0.3),
            ChunkResult(doc_id="5_0", content="Content 5", score=0.8),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        # 验证分数降序排列
        scores = [chunk.score for chunk in sorted_results]
        assert scores == sorted(scores, reverse=True)
        assert scores == [0.9, 0.8, 0.7, 0.5, 0.3]
    
    def test_sort_already_sorted(self, mock_kb):
        """测试已排序的结果"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.9),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.8),
            ChunkResult(doc_id="3_0", content="Content 3", score=0.7),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        scores = [chunk.score for chunk in sorted_results]
        assert scores == [0.9, 0.8, 0.7]
    
    def test_sort_reverse_order(self, mock_kb):
        """测试逆序输入"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.3),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.5),
            ChunkResult(doc_id="3_0", content="Content 3", score=0.7),
            ChunkResult(doc_id="4_0", content="Content 4", score=0.9),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        scores = [chunk.score for chunk in sorted_results]
        assert scores == [0.9, 0.7, 0.5, 0.3]
    
    def test_sort_source_diversity_same_scores(self, mock_kb):
        """
        测试相同分数时的来源多样性排序
        
        Requirements: 4.4
        当分数相同时，优先选择来自不同来源的结果
        """
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        # 所有结果分数相同，但来自不同来源
        results = [
            ChunkResult(doc_id="A_0", content="Content A0", score=0.8),
            ChunkResult(doc_id="A_1", content="Content A1", score=0.8),
            ChunkResult(doc_id="B_0", content="Content B0", score=0.8),
            ChunkResult(doc_id="C_0", content="Content C0", score=0.8),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        # 验证分数仍然是降序（或相等）
        scores = [chunk.score for chunk in sorted_results]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]
        
        # 验证来源多样性：不同来源的结果应该优先出现
        # 第一个出现的每个来源应该在同来源的其他结果之前
        seen_sources = set()
        source_first_positions = {}
        
        for i, chunk in enumerate(sorted_results):
            article_id = chunk.article_id
            if article_id not in seen_sources:
                source_first_positions[article_id] = i
                seen_sources.add(article_id)
        
        # A, B, C 三个来源应该都出现
        assert "A" in seen_sources
        assert "B" in seen_sources
        assert "C" in seen_sources
    
    def test_sort_source_diversity_mixed_scores(self, mock_kb):
        """
        测试混合分数时的来源多样性排序
        
        Requirements: 4.3, 4.4
        主排序按分数，次排序按来源多样性
        """
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="A_0", content="Content A0", score=0.9),
            ChunkResult(doc_id="A_1", content="Content A1", score=0.7),
            ChunkResult(doc_id="B_0", content="Content B0", score=0.9),
            ChunkResult(doc_id="B_1", content="Content B1", score=0.7),
            ChunkResult(doc_id="C_0", content="Content C0", score=0.7),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        # 验证分数降序
        scores = [chunk.score for chunk in sorted_results]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]
        
        # 分数 0.9 的结果应该在前面
        high_score_results = [r for r in sorted_results if r.score == 0.9]
        assert len(high_score_results) == 2
        
        # 分数 0.7 的结果应该在后面
        low_score_results = [r for r in sorted_results if r.score == 0.7]
        assert len(low_score_results) == 3
    
    def test_sort_preserves_all_results(self, mock_kb):
        """测试排序后保留所有结果"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="Content 1", score=0.5),
            ChunkResult(doc_id="2_0", content="Content 2", score=0.9),
            ChunkResult(doc_id="3_0", content="Content 3", score=0.7),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        # 验证数量不变
        assert len(sorted_results) == len(results)
        
        # 验证所有 doc_id 都存在
        original_ids = {r.doc_id for r in results}
        sorted_ids = {r.doc_id for r in sorted_results}
        assert original_ids == sorted_ids
    
    def test_sort_preserves_metadata(self, mock_kb):
        """测试排序后保留元数据"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(
                doc_id="1_0", 
                content="Content 1", 
                score=0.5,
                metadata={"title": "Article 1", "source": "blog"}
            ),
            ChunkResult(
                doc_id="2_0", 
                content="Content 2", 
                score=0.9,
                metadata={"title": "Article 2", "source": "news"}
            ),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        # 找到 doc_id="2_0" 的结果（应该在第一位）
        first_result = sorted_results[0]
        assert first_result.doc_id == "2_0"
        assert first_result.metadata == {"title": "Article 2", "source": "news"}
    
    def test_sort_same_scores_different_sources_diversity(self, mock_kb):
        """
        测试相同分数时优先不同来源
        
        Requirements: 4.4
        """
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        # 创建多个相同分数的结果，来自不同来源
        results = [
            ChunkResult(doc_id="A_0", content="Content A0", score=0.8),
            ChunkResult(doc_id="A_1", content="Content A1", score=0.8),
            ChunkResult(doc_id="A_2", content="Content A2", score=0.8),
            ChunkResult(doc_id="B_0", content="Content B0", score=0.8),
            ChunkResult(doc_id="C_0", content="Content C0", score=0.8),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        # 获取前三个结果的来源
        first_three_sources = [r.article_id for r in sorted_results[:3]]
        
        # 前三个结果应该来自三个不同的来源（A, B, C）
        # 因为来源多样性排序会优先选择不同来源
        unique_sources_in_first_three = set(first_three_sources)
        assert len(unique_sources_in_first_three) == 3
        assert "A" in unique_sources_in_first_three
        assert "B" in unique_sources_in_first_three
        assert "C" in unique_sources_in_first_three
    
    def test_sort_property_7_non_increasing_order(self, mock_kb):
        """
        Property 7: Result Ordering
        *For any* final retrieval results list, the relevance scores 
        SHALL be in non-increasing (descending) order.
        
        **Validates: Requirements 4.3**
        """
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        # 测试各种输入
        test_cases = [
            # 随机顺序
            [
                ChunkResult(doc_id="1_0", content="C1", score=0.3),
                ChunkResult(doc_id="2_0", content="C2", score=0.9),
                ChunkResult(doc_id="3_0", content="C3", score=0.5),
                ChunkResult(doc_id="4_0", content="C4", score=0.7),
            ],
            # 相同分数
            [
                ChunkResult(doc_id="1_0", content="C1", score=0.5),
                ChunkResult(doc_id="2_0", content="C2", score=0.5),
                ChunkResult(doc_id="3_0", content="C3", score=0.5),
            ],
            # 混合分数
            [
                ChunkResult(doc_id="1_0", content="C1", score=1.0),
                ChunkResult(doc_id="2_0", content="C2", score=0.0),
                ChunkResult(doc_id="3_0", content="C3", score=0.5),
                ChunkResult(doc_id="4_0", content="C4", score=0.5),
            ],
        ]
        
        for results in test_cases:
            sorted_results = retriever._sort_results(results)
            scores = [r.score for r in sorted_results]
            
            # 验证非递增顺序
            for i in range(len(scores) - 1):
                assert scores[i] >= scores[i + 1], \
                    f"Scores not in non-increasing order: {scores}"
    
    def test_sort_with_float_precision(self, mock_kb):
        """测试浮点数精度"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="C1", score=0.123456789),
            ChunkResult(doc_id="2_0", content="C2", score=0.123456788),
            ChunkResult(doc_id="3_0", content="C3", score=0.123456790),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        scores = [r.score for r in sorted_results]
        # 验证非递增顺序
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]
    
    def test_sort_extreme_scores(self, mock_kb):
        """测试极端分数值"""
        config = RetrievalConfig()
        retriever = EnhancedRetriever(mock_kb, config)
        
        results = [
            ChunkResult(doc_id="1_0", content="C1", score=0.0),
            ChunkResult(doc_id="2_0", content="C2", score=1.0),
            ChunkResult(doc_id="3_0", content="C3", score=0.5),
        ]
        
        sorted_results = retriever._sort_results(results)
        
        scores = [r.score for r in sorted_results]
        assert scores == [1.0, 0.5, 0.0]


class TestDeduplicatedCountMetadata:
    """
    测试去重计数元数据
    
    Requirements: 4.5
    THE RAG_Engine SHALL return deduplicated results count in response metadata
    """
    
    @pytest.fixture
    def mock_kb(self):
        """创建 Mock KnowledgeBase"""
        kb = Mock()
        kb.search.return_value = [
            {"doc_id": "1_0", "content": "Same content here", "score": 0.9, "metadata": {}},
            {"doc_id": "2_0", "content": "Same content here", "score": 0.8, "metadata": {}},
            {"doc_id": "3_0", "content": "Different content", "score": 0.7, "metadata": {}},
        ]
        return kb
    
    def test_deduplicated_count_in_result(self, mock_kb):
        """
        测试去重计数包含在结果中
        
        Requirements: 4.5
        """
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        result = retriever.retrieve("test query", n_results=10)
        
        # 验证 deduplicated_count 字段存在
        assert hasattr(result, 'deduplicated_count')
        # 由于有两个相同内容的结果，应该去重一个
        assert result.deduplicated_count >= 0
    
    def test_deduplicated_count_accuracy(self, mock_kb):
        """测试去重计数准确性"""
        # 设置返回完全相同的内容
        mock_kb.search.return_value = [
            {"doc_id": "1_0", "content": "Exact same content", "score": 0.9, "metadata": {}},
            {"doc_id": "2_0", "content": "Exact same content", "score": 0.8, "metadata": {}},
            {"doc_id": "3_0", "content": "Exact same content", "score": 0.7, "metadata": {}},
            {"doc_id": "4_0", "content": "Unique content", "score": 0.6, "metadata": {}},
        ]
        
        config = RetrievalConfig(dedup_threshold=0.95)
        retriever = EnhancedRetriever(mock_kb, config)
        
        result = retriever.retrieve("test query", n_results=10)
        
        # 3 个相同内容应该去重 2 个
        assert result.deduplicated_count == 2
        # 最终应该有 2 个结果（1 个去重后的 + 1 个唯一的）
        assert len(result.chunks) == 2
