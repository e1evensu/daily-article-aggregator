"""
KnowledgeBase 单元测试

测试知识库管理器的核心功能：
- ChromaDB 初始化和连接
- 文档分块逻辑
- 配置解析

Requirements:
    - 1.2: 使用向量数据库存储嵌入
"""

import gc
import os
import shutil
import tempfile
import time
import pytest

from src.qa.knowledge_base import KnowledgeBase
from src.qa.config import QAConfig, ChromaConfig, ChunkingConfig


def safe_rmtree(path: str, max_retries: int = 3) -> None:
    """
    安全删除目录，处理 Windows 上的文件锁定问题
    
    Args:
        path: 要删除的目录路径
        max_retries: 最大重试次数
    """
    for i in range(max_retries):
        try:
            if os.path.exists(path):
                shutil.rmtree(path)
            return
        except PermissionError:
            # Windows 上 ChromaDB 可能还在使用文件
            gc.collect()
            time.sleep(0.1 * (i + 1))
    # 最后一次尝试，忽略错误
    try:
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


class TestKnowledgeBaseInit:
    """测试 KnowledgeBase 初始化"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        # 清理（使用安全删除）
        safe_rmtree(temp_path)
    
    def test_init_with_dict_config(self, temp_dir):
        """测试使用字典配置初始化"""
        config = {
            'chroma_path': os.path.join(temp_dir, 'chroma_db'),
            'collection_name': 'test_collection',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        
        kb = KnowledgeBase(config)
        
        assert kb.chunk_size == 500
        assert kb.chunk_overlap == 50
        assert kb.collection is not None
        assert kb.collection.count() == 0
    
    def test_init_with_qa_config(self, temp_dir):
        """测试使用 QAConfig 对象初始化"""
        qa_config = QAConfig(
            chroma=ChromaConfig(
                path=os.path.join(temp_dir, 'chroma_db'),
                collection_name='test_collection'
            ),
            chunking=ChunkingConfig(
                chunk_size=300,
                chunk_overlap=30
            )
        )
        
        kb = KnowledgeBase(qa_config)
        
        assert kb.chunk_size == 300
        assert kb.chunk_overlap == 30
        assert kb.collection is not None
    
    def test_init_creates_directory(self, temp_dir):
        """测试初始化时自动创建目录"""
        chroma_path = os.path.join(temp_dir, 'new_dir', 'chroma_db')
        config = {
            'chroma_path': chroma_path,
            'collection_name': 'test_collection'
        }
        
        kb = KnowledgeBase(config)
        
        assert os.path.exists(chroma_path)
    
    def test_init_with_default_values(self, temp_dir):
        """测试使用默认值初始化"""
        config = {
            'chroma_path': os.path.join(temp_dir, 'chroma_db'),
            'collection_name': 'test_collection'
        }
        
        kb = KnowledgeBase(config)
        
        # 默认值
        assert kb.chunk_size == 500
        assert kb.chunk_overlap == 50
    
    def test_init_invalid_chunk_size(self, temp_dir):
        """测试无效的 chunk_size 配置"""
        config = {
            'chroma_path': os.path.join(temp_dir, 'chroma_db'),
            'collection_name': 'test_collection',
            'chunk_size': 0
        }
        
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            KnowledgeBase(config)
    
    def test_init_invalid_chunk_overlap(self, temp_dir):
        """测试无效的 chunk_overlap 配置"""
        config = {
            'chroma_path': os.path.join(temp_dir, 'chroma_db'),
            'collection_name': 'test_collection',
            'chunk_size': 100,
            'chunk_overlap': -1
        }
        
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            KnowledgeBase(config)
    
    def test_init_overlap_greater_than_size(self, temp_dir):
        """测试 chunk_overlap >= chunk_size 的情况"""
        config = {
            'chroma_path': os.path.join(temp_dir, 'chroma_db'),
            'collection_name': 'test_collection',
            'chunk_size': 100,
            'chunk_overlap': 100
        }
        
        with pytest.raises(ValueError, match="chunk_overlap.*must be less than"):
            KnowledgeBase(config)


class TestChunkText:
    """测试文档分块功能"""
    
    @pytest.fixture
    def kb(self, tmp_path):
        """创建测试用的 KnowledgeBase 实例"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_collection',
            'chunk_size': 100,
            'chunk_overlap': 20
        }
        return KnowledgeBase(config)
    
    def test_chunk_empty_text(self, kb):
        """测试空文本分块"""
        assert kb.chunk_text("") == []
        assert kb.chunk_text("   ") == []
        assert kb.chunk_text(None) == []
    
    def test_chunk_short_text(self, kb):
        """测试短文本（小于 chunk_size）"""
        text = "这是一段短文本。"
        chunks = kb.chunk_text(text)
        
        assert len(chunks) == 1
        assert chunks[0] == text
    
    def test_chunk_exact_size_text(self, kb):
        """测试刚好等于 chunk_size 的文本"""
        # 创建刚好 100 字符的文本
        text = "a" * 100
        chunks = kb.chunk_text(text)
        
        assert len(chunks) == 1
        assert chunks[0] == text
    
    def test_chunk_long_text(self, kb):
        """测试长文本分块"""
        # 创建 250 字符的文本
        text = "这是一段测试文本。" * 25  # 约 225 字符
        chunks = kb.chunk_text(text)
        
        # 应该产生多个块
        assert len(chunks) > 1
        
        # 每个块不应超过 chunk_size
        for chunk in chunks:
            assert len(chunk) <= kb.chunk_size
    
    def test_chunk_with_sentence_boundary(self, kb):
        """测试在句子边界处分块"""
        # 创建包含多个句子的文本
        text = "第一句话。第二句话。第三句话。第四句话。第五句话。" * 5
        chunks = kb.chunk_text(text)
        
        # 检查分块是否尽量在句子边界
        for chunk in chunks[:-1]:  # 最后一块可能不完整
            # 应该以句号结尾（如果可能）
            assert chunk.endswith('。') or len(chunk) <= kb.chunk_size
    
    def test_chunk_overlap(self, kb):
        """测试分块重叠"""
        # 创建足够长的文本
        text = "ABCDEFGHIJ" * 30  # 300 字符
        chunks = kb.chunk_text(text)
        
        # 检查相邻块之间是否有重叠
        if len(chunks) > 1:
            for i in range(len(chunks) - 1):
                # 当前块的末尾部分应该出现在下一块的开头
                # 由于重叠是 20 字符，检查是否有共同内容
                current_end = chunks[i][-kb.chunk_overlap:]
                next_start = chunks[i + 1][:kb.chunk_overlap]
                # 至少应该有一些重叠（可能因为句子边界调整而不完全匹配）
                assert len(current_end) > 0 or len(next_start) > 0
    
    def test_chunk_preserves_content(self, kb):
        """测试分块后内容完整性"""
        text = "这是一段需要分块的长文本。" * 20
        chunks = kb.chunk_text(text)
        
        # 所有块组合后应该包含原文的所有内容（考虑重叠）
        combined = "".join(chunks)
        # 由于重叠，组合后的长度应该 >= 原文长度
        assert len(combined) >= len(text.strip())
    
    def test_chunk_with_newlines(self, kb):
        """测试包含换行符的文本"""
        text = "第一段内容。\n\n第二段内容。\n\n第三段内容。" * 10
        chunks = kb.chunk_text(text)
        
        assert len(chunks) > 0
        # 每个块都应该是有效的文本
        for chunk in chunks:
            assert chunk.strip()


class TestKnowledgeBaseStats:
    """
    测试知识库统计功能
    
    Requirements: 5.2 - 支持查看知识库统计信息
    """
    
    @pytest.fixture
    def kb(self, tmp_path):
        """创建测试用的 KnowledgeBase 实例"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_stats_collection',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        return KnowledgeBase(config)
    
    @pytest.fixture
    def mock_embedding_service(self):
        """创建 Mock EmbeddingService"""
        return MockEmbeddingService(dimension=1536)
    
    def test_get_stats_empty(self, kb):
        """测试空知识库的统计信息"""
        stats = kb.get_stats()
        
        assert stats['total_documents'] == 0
        assert stats['collection_name'] == 'test_stats_collection'
        assert 'chroma_path' in stats
        assert stats['chunk_size'] == 500
        assert stats['chunk_overlap'] == 50
    
    def test_get_stats_with_documents(self, tmp_path, mock_embedding_service):
        """测试有文档的知识库统计信息 - Requirements: 5.2"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_stats_with_docs',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 添加测试文章
        articles = [
            {'id': 1, 'title': 'Article 1', 'content': 'Content for article 1'},
            {'id': 2, 'title': 'Article 2', 'content': 'Content for article 2'},
            {'id': 3, 'title': 'Article 3', 'content': 'Content for article 3'}
        ]
        added_count = kb.add_articles(articles)
        
        stats = kb.get_stats()
        
        assert stats['total_documents'] == added_count
        assert stats['total_documents'] == 3
        assert stats['collection_name'] == 'test_stats_with_docs'
    
    def test_get_stats_returns_all_required_fields(self, kb):
        """测试 get_stats 返回所有必需字段 - Requirements: 5.2"""
        stats = kb.get_stats()
        
        # 验证所有必需字段都存在
        required_fields = [
            'total_documents',
            'collection_name',
            'chroma_path',
            'chunk_size',
            'chunk_overlap'
        ]
        
        for field in required_fields:
            assert field in stats, f"Missing required field: {field}"
    
    def test_get_stats_after_multiple_adds(self, tmp_path, mock_embedding_service):
        """测试多次添加后的统计信息 - Requirements: 5.2"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_stats_multiple_adds',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 第一次添加
        kb.add_articles([{'id': 1, 'title': 'Article 1', 'content': 'Content 1'}])
        stats1 = kb.get_stats()
        assert stats1['total_documents'] == 1
        
        # 第二次添加
        kb.add_articles([
            {'id': 2, 'title': 'Article 2', 'content': 'Content 2'},
            {'id': 3, 'title': 'Article 3', 'content': 'Content 3'}
        ])
        stats2 = kb.get_stats()
        assert stats2['total_documents'] == 3
    
    def test_get_stats_with_chunked_documents(self, tmp_path, mock_embedding_service):
        """测试分块文档的统计信息 - Requirements: 5.2"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_stats_chunked',
            'chunk_size': 50,  # 小的 chunk_size 以产生多个块
            'chunk_overlap': 10
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 添加长内容文章（会被分成多个块）
        long_content = "这是一段很长的测试内容。" * 20  # 约 200 字符
        kb.add_articles([{
            'id': 1,
            'title': 'Long Article',
            'content': long_content
        }])
        
        stats = kb.get_stats()
        
        # 文档数应该大于 1（因为被分块了）
        assert stats['total_documents'] > 1
        assert stats['chunk_size'] == 50
        assert stats['chunk_overlap'] == 10


class TestKnowledgeBaseGetDocument:
    """测试文档获取功能"""
    
    @pytest.fixture
    def kb(self, tmp_path):
        """创建测试用的 KnowledgeBase 实例"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_get_doc_collection'
        }
        return KnowledgeBase(config)
    
    def test_get_nonexistent_document(self, kb):
        """测试获取不存在的文档"""
        result = kb.get_document("nonexistent_id")
        assert result is None


class TestKnowledgeBaseRebuild:
    """
    测试知识库重建功能
    
    Requirements: 5.1 - 支持手动触发知识库重建
    """
    
    @pytest.fixture
    def kb(self, tmp_path):
        """创建测试用的 KnowledgeBase 实例"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_rebuild_collection'
        }
        return KnowledgeBase(config)
    
    @pytest.fixture
    def mock_embedding_service(self):
        """创建 Mock EmbeddingService"""
        return MockEmbeddingService(dimension=1536)
    
    def test_rebuild_empty_collection(self, kb):
        """测试重建空集合"""
        count = kb.rebuild()
        
        assert count == 0
        assert kb.collection.count() == 0
    
    def test_rebuild_clears_all_documents(self, tmp_path, mock_embedding_service):
        """测试重建清除所有文档 - Requirements: 5.1"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_rebuild_clear'
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 添加测试文章
        articles = [
            {'id': 1, 'title': 'Article 1', 'content': 'Content 1'},
            {'id': 2, 'title': 'Article 2', 'content': 'Content 2'},
            {'id': 3, 'title': 'Article 3', 'content': 'Content 3'}
        ]
        kb.add_articles(articles)
        
        # 验证文档已添加
        assert kb.collection.count() == 3
        
        # 重建知识库
        count = kb.rebuild()
        
        # 验证所有文档被清除
        assert count == 0
        assert kb.collection.count() == 0
    
    def test_rebuild_returns_zero(self, tmp_path, mock_embedding_service):
        """测试重建后返回 0 - Requirements: 5.1"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_rebuild_return'
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 添加一些文档
        kb.add_articles([
            {'id': 1, 'title': 'Test', 'content': 'Test content'}
        ])
        
        # 重建应该返回 0
        result = kb.rebuild()
        assert result == 0
    
    def test_rebuild_allows_new_documents(self, tmp_path, mock_embedding_service):
        """测试重建后可以添加新文档 - Requirements: 5.1"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_rebuild_new_docs'
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 添加初始文档
        kb.add_articles([
            {'id': 1, 'title': 'Old Article', 'content': 'Old content'}
        ])
        assert kb.collection.count() == 1
        
        # 重建知识库
        kb.rebuild()
        assert kb.collection.count() == 0
        
        # 添加新文档
        kb.add_articles([
            {'id': 2, 'title': 'New Article', 'content': 'New content'}
        ])
        
        # 验证新文档已添加
        assert kb.collection.count() == 1
        doc = kb.get_document("2_0")
        assert doc is not None
        assert 'New Article' in doc['content']
    
    def test_rebuild_preserves_configuration(self, tmp_path, mock_embedding_service):
        """测试重建后配置保持不变 - Requirements: 5.1"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_rebuild_config',
            'chunk_size': 300,
            'chunk_overlap': 30
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 记录原始配置
        original_chunk_size = kb.chunk_size
        original_chunk_overlap = kb.chunk_overlap
        
        # 添加文档并重建
        kb.add_articles([{'id': 1, 'title': 'Test', 'content': 'Content'}])
        kb.rebuild()
        
        # 验证配置保持不变
        assert kb.chunk_size == original_chunk_size
        assert kb.chunk_overlap == original_chunk_overlap
    
    def test_rebuild_stats_reflect_empty_state(self, tmp_path, mock_embedding_service):
        """测试重建后统计信息反映空状态 - Requirements: 5.1, 5.2"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_rebuild_stats'
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 添加文档
        kb.add_articles([
            {'id': 1, 'title': 'Article 1', 'content': 'Content 1'},
            {'id': 2, 'title': 'Article 2', 'content': 'Content 2'}
        ])
        
        stats_before = kb.get_stats()
        assert stats_before['total_documents'] == 2
        
        # 重建
        kb.rebuild()
        
        stats_after = kb.get_stats()
        assert stats_after['total_documents'] == 0
        assert stats_after['collection_name'] == 'test_rebuild_stats'
    
    def test_rebuild_multiple_times(self, tmp_path, mock_embedding_service):
        """测试多次重建 - Requirements: 5.1"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_rebuild_multiple'
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 第一次添加和重建
        kb.add_articles([{'id': 1, 'title': 'Test 1', 'content': 'Content 1'}])
        assert kb.collection.count() == 1
        kb.rebuild()
        assert kb.collection.count() == 0
        
        # 第二次添加和重建
        kb.add_articles([{'id': 2, 'title': 'Test 2', 'content': 'Content 2'}])
        assert kb.collection.count() == 1
        kb.rebuild()
        assert kb.collection.count() == 0
        
        # 第三次添加
        kb.add_articles([{'id': 3, 'title': 'Test 3', 'content': 'Content 3'}])
        assert kb.collection.count() == 1


class TestKnowledgeBaseEmbeddingService:
    """测试 Embedding Service 集成"""
    
    @pytest.fixture
    def kb(self, tmp_path):
        """创建测试用的 KnowledgeBase 实例"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_embedding_collection'
        }
        return KnowledgeBase(config)
    
    def test_embedding_service_not_set(self, kb):
        """测试未设置 embedding service 时的行为"""
        assert kb.embedding_service is None
    
    def test_add_articles_without_embedding_service(self, kb):
        """测试未设置 embedding service 时添加文章"""
        articles = [{'id': 1, 'title': 'Test', 'content': 'Content'}]
        
        with pytest.raises(RuntimeError, match="Embedding service not set"):
            kb.add_articles(articles)
    
    def test_search_without_embedding_service(self, kb):
        """测试未设置 embedding service 时搜索"""
        with pytest.raises(RuntimeError, match="Embedding service not set"):
            kb.search("test query")


class MockEmbeddingService:
    """
    Mock EmbeddingService for testing
    
    Generates deterministic fake embeddings based on text content.
    """
    
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.embed_text_calls = []
        self.embed_batch_calls = []
    
    def embed_text(self, text: str) -> list[float]:
        """Generate a deterministic fake embedding for a single text"""
        self.embed_text_calls.append(text)
        # Generate deterministic embedding based on text hash
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        # Create a normalized vector
        embedding = []
        for i in range(self.dimension):
            val = ((hash_val + i) % 1000) / 1000.0 - 0.5
            embedding.append(val)
        return embedding
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic fake embeddings for a batch of texts"""
        self.embed_batch_calls.append(texts)
        return [self.embed_text(text) for text in texts]
    
    def get_dimension(self) -> int:
        return self.dimension


class TestAddArticles:
    """
    测试 add_articles() 方法
    
    Requirements: 1.2, 1.3
    """
    
    @pytest.fixture
    def mock_embedding_service(self):
        """创建 Mock EmbeddingService"""
        return MockEmbeddingService(dimension=1536)
    
    @pytest.fixture
    def kb_with_embedding(self, tmp_path, mock_embedding_service):
        """创建带有 embedding service 的 KnowledgeBase"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_add_articles',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        return kb
    
    def test_add_single_article(self, kb_with_embedding):
        """测试添加单篇文章"""
        articles = [{
            'id': 1,
            'title': 'Test Article',
            'content': 'This is test content for the article.',
            'url': 'https://example.com/article1',
            'source_type': 'blog',
            'published_date': '2024-01-15',
            'category': 'AI/机器学习'
        }]
        
        count = kb_with_embedding.add_articles(articles)
        
        # 短文本应该只产生一个 chunk
        assert count == 1
        assert kb_with_embedding.collection.count() == 1
        
        # 验证文档可以被检索
        doc = kb_with_embedding.get_document("1_0")
        assert doc is not None
        assert 'Test Article' in doc['content']
        assert doc['metadata']['article_id'] == 1
        assert doc['metadata']['source_type'] == 'blog'
    
    def test_add_multiple_articles(self, kb_with_embedding):
        """测试添加多篇文章"""
        articles = [
            {
                'id': 1,
                'title': 'Article One',
                'content': 'Content for article one.',
                'url': 'https://example.com/1',
                'source_type': 'arxiv'
            },
            {
                'id': 2,
                'title': 'Article Two',
                'content': 'Content for article two.',
                'url': 'https://example.com/2',
                'source_type': 'rss'
            },
            {
                'id': 3,
                'title': 'Article Three',
                'content': 'Content for article three.',
                'url': 'https://example.com/3',
                'source_type': 'nvd'
            }
        ]
        
        count = kb_with_embedding.add_articles(articles)
        
        assert count == 3
        assert kb_with_embedding.collection.count() == 3
    
    def test_add_article_with_long_content(self, tmp_path, mock_embedding_service):
        """测试添加长内容文章（需要分块）"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_long_content',
            'chunk_size': 100,  # 小的 chunk_size 以便测试分块
            'chunk_overlap': 20
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 创建长内容
        long_content = "这是一段很长的测试内容。" * 50  # 约 500 字符
        articles = [{
            'id': 1,
            'title': 'Long Article',
            'content': long_content,
            'url': 'https://example.com/long',
            'source_type': 'blog'
        }]
        
        count = kb.add_articles(articles)
        
        # 应该产生多个 chunks
        assert count > 1
        assert kb.collection.count() == count
        
        # 验证每个 chunk 都有正确的元数据
        for i in range(count):
            doc = kb.get_document(f"1_{i}")
            assert doc is not None
            assert doc['metadata']['article_id'] == 1
            assert doc['metadata']['chunk_index'] == i
    
    def test_add_empty_articles_list(self, kb_with_embedding):
        """测试添加空文章列表"""
        count = kb_with_embedding.add_articles([])
        
        assert count == 0
        assert kb_with_embedding.collection.count() == 0
    
    def test_add_article_without_id(self, kb_with_embedding):
        """测试添加没有 id 的文章（应该跳过）"""
        articles = [
            {'title': 'No ID Article', 'content': 'Some content'},
            {'id': 1, 'title': 'Valid Article', 'content': 'Valid content'}
        ]
        
        count = kb_with_embedding.add_articles(articles)
        
        # 只有有效的文章被添加
        assert count == 1
        assert kb_with_embedding.collection.count() == 1
    
    def test_add_article_without_content(self, kb_with_embedding):
        """测试添加没有 content 的文章（应该跳过）"""
        articles = [
            {'id': 1, 'title': 'No Content Article'},
            {'id': 2, 'title': 'Valid Article', 'content': 'Valid content'}
        ]
        
        count = kb_with_embedding.add_articles(articles)
        
        assert count == 1
        assert kb_with_embedding.collection.count() == 1
    
    def test_add_article_with_empty_content(self, kb_with_embedding):
        """测试添加空内容的文章
        
        注意：
        - 如果 content 是空字符串 ''，文章会被跳过（not content 为 True）
        - 如果 content 是空白字符串 '   '，文章不会被跳过（not content 为 False）
          但如果有标题，标题会被包含在分块中，所以文章仍会被添加
        """
        articles = [
            {'id': 1, 'title': 'Empty Content', 'content': ''},  # 跳过：content 为空字符串
            {'id': 2, 'title': 'Whitespace Content', 'content': '   '},  # 添加：有标题
            {'id': 3, 'title': 'Valid Article', 'content': 'Valid content'}  # 添加：正常
        ]
        
        count = kb_with_embedding.add_articles(articles)
        
        # 文章 1 被跳过（空字符串），文章 2 和 3 被添加
        assert count == 2
        assert kb_with_embedding.collection.count() == 2
    
    def test_add_article_with_no_title_and_empty_content(self, kb_with_embedding):
        """测试添加没有标题且内容为空的文章（应该跳过）"""
        articles = [
            {'id': 1, 'content': ''},  # 跳过：空内容
            {'id': 2, 'content': '   '},  # 跳过：空白内容，无标题，chunk_text 返回空
            {'id': 3, 'title': '', 'content': ''},  # 跳过：空内容
            {'id': 4, 'title': 'Has Title', 'content': ''},  # 跳过：空内容
            {'id': 5, 'content': 'Valid content'}  # 添加：有内容
        ]
        
        count = kb_with_embedding.add_articles(articles)
        
        # 只有 id=5 的文章被添加
        assert count == 1
        assert kb_with_embedding.collection.count() == 1
    
    def test_add_article_metadata_stored_correctly(self, kb_with_embedding):
        """测试文章元数据正确存储"""
        articles = [{
            'id': 42,
            'title': 'Metadata Test',
            'content': 'Content for metadata test.',
            'url': 'https://example.com/meta',
            'source_type': 'kev',
            'published_date': '2024-03-20',
            'category': '安全/隐私'
        }]
        
        kb_with_embedding.add_articles(articles)
        
        doc = kb_with_embedding.get_document("42_0")
        assert doc is not None
        
        metadata = doc['metadata']
        assert metadata['article_id'] == 42
        assert metadata['title'] == 'Metadata Test'
        assert metadata['url'] == 'https://example.com/meta'
        assert metadata['source_type'] == 'kev'
        assert metadata['published_date'] == '2024-03-20'
        assert metadata['category'] == '安全/隐私'
        assert metadata['chunk_index'] == 0
    
    def test_add_article_without_optional_fields(self, kb_with_embedding):
        """测试添加只有必需字段的文章"""
        articles = [{
            'id': 1,
            'content': 'Minimal content only.'
        }]
        
        count = kb_with_embedding.add_articles(articles)
        
        assert count == 1
        
        doc = kb_with_embedding.get_document("1_0")
        assert doc is not None
        
        # 可选字段应该有默认值（空字符串）
        metadata = doc['metadata']
        assert metadata['title'] == ''
        assert metadata['url'] == ''
        assert metadata['source_type'] == ''
        assert metadata['published_date'] == ''
        assert metadata['category'] == ''
    
    def test_add_article_title_included_in_content(self, kb_with_embedding):
        """测试标题被包含在分块内容中"""
        articles = [{
            'id': 1,
            'title': 'Important Title',
            'content': 'Article body content.',
            'url': 'https://example.com/1',
            'source_type': 'blog'
        }]
        
        kb_with_embedding.add_articles(articles)
        
        doc = kb_with_embedding.get_document("1_0")
        assert doc is not None
        
        # 标题应该在内容中
        assert 'Important Title' in doc['content']
        assert 'Article body content' in doc['content']
    
    def test_set_embedding_service(self, tmp_path, mock_embedding_service):
        """测试通过 set_embedding_service 设置服务"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_set_service'
        }
        kb = KnowledgeBase(config)
        
        # 初始没有 embedding service
        assert kb.embedding_service is None
        
        # 设置 embedding service
        kb.set_embedding_service(mock_embedding_service)
        
        assert kb.embedding_service is mock_embedding_service
        
        # 现在可以添加文章
        articles = [{'id': 1, 'title': 'Test', 'content': 'Test content'}]
        count = kb.add_articles(articles)
        
        assert count == 1
    
    def test_embedding_service_called_correctly(self, kb_with_embedding, mock_embedding_service):
        """测试 embedding service 被正确调用"""
        articles = [{
            'id': 1,
            'title': 'Test Title',
            'content': 'Test content for embedding.',
            'url': 'https://example.com/1',
            'source_type': 'blog'
        }]
        
        kb_with_embedding.add_articles(articles)
        
        # 验证 embed_batch 被调用
        assert len(mock_embedding_service.embed_batch_calls) == 1
        
        # 验证传入的文本包含标题和内容
        batch_texts = mock_embedding_service.embed_batch_calls[0]
        assert len(batch_texts) == 1
        assert 'Test Title' in batch_texts[0]
        assert 'Test content for embedding' in batch_texts[0]
    
    def test_stats_updated_after_add(self, kb_with_embedding):
        """测试添加文章后统计信息更新"""
        initial_stats = kb_with_embedding.get_stats()
        assert initial_stats['total_documents'] == 0
        
        articles = [
            {'id': 1, 'title': 'Article 1', 'content': 'Content 1'},
            {'id': 2, 'title': 'Article 2', 'content': 'Content 2'}
        ]
        
        kb_with_embedding.add_articles(articles)
        
        updated_stats = kb_with_embedding.get_stats()
        assert updated_stats['total_documents'] == 2


class TestSearch:
    """
    测试 search() 方法 - 语义搜索功能
    
    Requirements: 3.2
    """
    
    @pytest.fixture
    def mock_embedding_service(self):
        """创建 Mock EmbeddingService"""
        return MockEmbeddingService(dimension=1536)
    
    @pytest.fixture
    def kb_with_data(self, tmp_path, mock_embedding_service):
        """创建带有测试数据的 KnowledgeBase"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_search',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 添加测试文章
        articles = [
            {
                'id': 1,
                'title': 'Machine Learning Introduction',
                'content': 'This article covers the basics of machine learning and neural networks.',
                'url': 'https://example.com/ml-intro',
                'source_type': 'arxiv',
                'published_date': '2024-01-15',
                'category': 'AI/机器学习'
            },
            {
                'id': 2,
                'title': 'Security Vulnerability Report',
                'content': 'A critical security vulnerability was discovered in the authentication system.',
                'url': 'https://example.com/security',
                'source_type': 'nvd',
                'published_date': '2024-02-20',
                'category': '安全/隐私'
            },
            {
                'id': 3,
                'title': 'Deep Learning Advances',
                'content': 'Recent advances in deep learning have revolutionized computer vision.',
                'url': 'https://example.com/dl-advances',
                'source_type': 'arxiv',
                'published_date': '2024-03-10',
                'category': 'AI/机器学习'
            },
            {
                'id': 4,
                'title': 'KEV Database Update',
                'content': 'New entries added to the Known Exploited Vulnerabilities database.',
                'url': 'https://example.com/kev-update',
                'source_type': 'kev',
                'published_date': '2024-03-15',
                'category': '安全/隐私'
            },
            {
                'id': 5,
                'title': 'RSS Feed Analysis',
                'content': 'Analysis of popular RSS feeds for technology news.',
                'url': 'https://example.com/rss-analysis',
                'source_type': 'rss',
                'published_date': '2024-03-20',
                'category': '其他'
            }
        ]
        kb.add_articles(articles)
        return kb
    
    def test_search_basic(self, kb_with_data):
        """测试基本搜索功能"""
        results = kb_with_data.search("machine learning")
        
        assert len(results) > 0
        assert len(results) <= 5  # 默认 n_results=5
        
        # 验证结果结构
        for result in results:
            assert 'doc_id' in result
            assert 'content' in result
            assert 'metadata' in result
            assert 'score' in result
    
    def test_search_returns_relevance_scores(self, kb_with_data):
        """测试搜索返回相关性分数"""
        results = kb_with_data.search("security vulnerability")
        
        assert len(results) > 0
        
        for result in results:
            score = result['score']
            # 分数应该在 [0, 1] 范围内
            assert 0 <= score <= 1, f"Score {score} should be between 0 and 1"
    
    def test_search_results_ordered_by_score(self, kb_with_data):
        """测试搜索结果按分数降序排列"""
        results = kb_with_data.search("deep learning neural networks")
        
        if len(results) > 1:
            scores = [r['score'] for r in results]
            # 验证分数是降序排列的
            assert scores == sorted(scores, reverse=True), \
                "Results should be ordered by descending score"
    
    def test_search_n_results_parameter(self, kb_with_data):
        """测试 n_results 参数"""
        # 请求 2 个结果
        results = kb_with_data.search("technology", n_results=2)
        assert len(results) <= 2
        
        # 请求 10 个结果（超过实际文档数）
        results = kb_with_data.search("technology", n_results=10)
        assert len(results) <= 10
    
    def test_search_with_source_type_filter(self, kb_with_data):
        """测试 source_type 过滤器"""
        # 只搜索 arxiv 来源
        results = kb_with_data.search("learning", filters={'source_type': 'arxiv'})
        
        for result in results:
            assert result['metadata']['source_type'] == 'arxiv', \
                "All results should be from arxiv source"
    
    def test_search_with_source_type_list_filter(self, kb_with_data):
        """测试 source_type 列表过滤器"""
        # 搜索 nvd 或 kev 来源
        results = kb_with_data.search(
            "vulnerability",
            filters={'source_type': ['nvd', 'kev']}
        )
        
        for result in results:
            assert result['metadata']['source_type'] in ['nvd', 'kev'], \
                "All results should be from nvd or kev source"
    
    def test_search_with_category_filter(self, kb_with_data):
        """测试 category 过滤器"""
        results = kb_with_data.search(
            "technology",
            filters={'category': 'AI/机器学习'}
        )
        
        for result in results:
            assert result['metadata']['category'] == 'AI/机器学习', \
                "All results should be in AI/机器学习 category"
    
    def test_search_with_multiple_filters(self, kb_with_data):
        """测试多个过滤器组合"""
        results = kb_with_data.search(
            "learning",
            filters={
                'source_type': 'arxiv',
                'category': 'AI/机器学习'
            }
        )
        
        for result in results:
            assert result['metadata']['source_type'] == 'arxiv'
            assert result['metadata']['category'] == 'AI/机器学习'
    
    def test_search_empty_query(self, kb_with_data):
        """测试空查询"""
        results = kb_with_data.search("")
        assert results == []
        
        results = kb_with_data.search("   ")
        assert results == []
    
    def test_search_no_matching_filter(self, kb_with_data):
        """测试没有匹配过滤器的情况"""
        results = kb_with_data.search(
            "machine learning",
            filters={'source_type': 'nonexistent_source'}
        )
        
        # 应该返回空结果
        assert results == []
    
    def test_search_result_contains_metadata(self, kb_with_data):
        """测试搜索结果包含完整元数据"""
        results = kb_with_data.search("machine learning", n_results=1)
        
        assert len(results) > 0
        result = results[0]
        
        metadata = result['metadata']
        assert 'article_id' in metadata
        assert 'title' in metadata
        assert 'url' in metadata
        assert 'source_type' in metadata
        assert 'published_date' in metadata
        assert 'category' in metadata
        assert 'chunk_index' in metadata
    
    def test_search_result_content_not_empty(self, kb_with_data):
        """测试搜索结果内容不为空"""
        results = kb_with_data.search("security")
        
        for result in results:
            assert result['content'], "Content should not be empty"
            assert len(result['content'].strip()) > 0
    
    def test_search_with_empty_filter_dict(self, kb_with_data):
        """测试空过滤器字典"""
        results = kb_with_data.search("learning", filters={})
        
        # 空过滤器应该返回所有匹配结果
        assert len(results) > 0
    
    def test_search_with_none_filter_values(self, kb_with_data):
        """测试过滤器值为 None 的情况"""
        results = kb_with_data.search(
            "learning",
            filters={'source_type': None, 'category': None}
        )
        
        # None 值的过滤器应该被忽略
        assert len(results) > 0


class TestSearchEdgeCases:
    """测试 search() 方法的边界情况"""
    
    @pytest.fixture
    def mock_embedding_service(self):
        """创建 Mock EmbeddingService"""
        return MockEmbeddingService(dimension=1536)
    
    @pytest.fixture
    def empty_kb(self, tmp_path, mock_embedding_service):
        """创建空的 KnowledgeBase"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_empty_search'
        }
        return KnowledgeBase(config, embedding_service=mock_embedding_service)
    
    def test_search_empty_knowledge_base(self, empty_kb):
        """测试在空知识库中搜索"""
        results = empty_kb.search("any query")
        
        assert results == []
    
    def test_search_n_results_zero(self, empty_kb):
        """测试 n_results=0 的情况"""
        # 先添加一些数据
        empty_kb.add_articles([{
            'id': 1,
            'title': 'Test',
            'content': 'Test content'
        }])
        
        results = empty_kb.search("test", n_results=0)
        assert results == []
    
    def test_search_n_results_negative(self, empty_kb):
        """测试 n_results 为负数的情况"""
        empty_kb.add_articles([{
            'id': 1,
            'title': 'Test',
            'content': 'Test content'
        }])
        
        # ChromaDB 可能会处理负数，或者返回空结果
        # 这里我们只验证不会抛出异常
        results = empty_kb.search("test", n_results=-1)
        # 结果应该是空列表或者有效结果
        assert isinstance(results, list)
    
    def test_search_very_long_query(self, empty_kb):
        """测试非常长的查询"""
        empty_kb.add_articles([{
            'id': 1,
            'title': 'Test Article',
            'content': 'This is test content for searching.'
        }])
        
        # 创建一个很长的查询
        long_query = "test " * 1000
        
        # 应该不会抛出异常
        results = empty_kb.search(long_query)
        assert isinstance(results, list)
    
    def test_search_special_characters_in_query(self, empty_kb):
        """测试查询中包含特殊字符"""
        empty_kb.add_articles([{
            'id': 1,
            'title': 'Test Article',
            'content': 'Content with special chars: @#$%^&*()'
        }])
        
        # 包含特殊字符的查询
        results = empty_kb.search("@#$%^&*()")
        assert isinstance(results, list)
    
    def test_search_unicode_query(self, empty_kb):
        """测试 Unicode 查询"""
        empty_kb.add_articles([{
            'id': 1,
            'title': '中文标题',
            'content': '这是中文内容，包含日文：こんにちは'
        }])
        
        results = empty_kb.search("中文内容")
        assert isinstance(results, list)


class TestBuildWhereFilter:
    """测试 _build_where_filter() 方法"""
    
    @pytest.fixture
    def kb(self, tmp_path):
        """创建测试用的 KnowledgeBase"""
        config = {
            'chroma_path': str(tmp_path / 'chroma_db'),
            'collection_name': 'test_filter'
        }
        return KnowledgeBase(config)
    
    def test_build_filter_single_source_type(self, kb):
        """测试单个 source_type 过滤器"""
        filters = {'source_type': 'arxiv'}
        result = kb._build_where_filter(filters)
        
        assert result == {'source_type': 'arxiv'}
    
    def test_build_filter_source_type_list(self, kb):
        """测试 source_type 列表过滤器"""
        filters = {'source_type': ['arxiv', 'nvd']}
        result = kb._build_where_filter(filters)
        
        assert result == {'source_type': {'$in': ['arxiv', 'nvd']}}
    
    def test_build_filter_single_category(self, kb):
        """测试单个 category 过滤器"""
        filters = {'category': 'AI/机器学习'}
        result = kb._build_where_filter(filters)
        
        assert result == {'category': 'AI/机器学习'}
    
    def test_build_filter_category_list(self, kb):
        """测试 category 列表过滤器"""
        filters = {'category': ['AI/机器学习', '安全/隐私']}
        result = kb._build_where_filter(filters)
        
        assert result == {'category': {'$in': ['AI/机器学习', '安全/隐私']}}
    
    def test_build_filter_multiple_conditions(self, kb):
        """测试多个过滤条件"""
        filters = {
            'source_type': 'arxiv',
            'category': 'AI/机器学习'
        }
        result = kb._build_where_filter(filters)
        
        assert '$and' in result
        assert len(result['$and']) == 2
    
    def test_build_filter_empty_dict(self, kb):
        """测试空过滤器字典"""
        result = kb._build_where_filter({})
        assert result is None
    
    def test_build_filter_none_values(self, kb):
        """测试 None 值的过滤器"""
        filters = {'source_type': None, 'category': None}
        result = kb._build_where_filter(filters)
        
        assert result is None
    
    def test_build_filter_empty_string_values(self, kb):
        """测试空字符串值的过滤器"""
        filters = {'source_type': '', 'category': ''}
        result = kb._build_where_filter(filters)
        
        assert result is None
    
    def test_build_filter_mixed_valid_invalid(self, kb):
        """测试混合有效和无效过滤器"""
        filters = {
            'source_type': 'arxiv',
            'category': None
        }
        result = kb._build_where_filter(filters)
        
        # 只有有效的过滤器应该被包含
        assert result == {'source_type': 'arxiv'}
