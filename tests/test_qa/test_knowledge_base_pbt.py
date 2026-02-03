"""
KnowledgeBase 属性测试 (Property-Based Tests)

使用 Hypothesis 进行属性测试，验证 KnowledgeBase 的正确性属性。

Feature: knowledge-qa-bot
Property 2: Document Storage Round-Trip
Validates: Requirements 1.2
"""

import gc
import hashlib
import os
import shutil
import tempfile
import time
from typing import Any

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

from src.qa.knowledge_base import KnowledgeBase


# =============================================================================
# Helper Functions
# =============================================================================

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
            gc.collect()
            time.sleep(0.1 * (i + 1))
    try:
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


class MockEmbeddingService:
    """
    Mock EmbeddingService for property-based testing
    
    Generates deterministic fake embeddings based on text content.
    This allows us to test the storage round-trip without relying on
    external API calls.
    """
    
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.embed_text_calls = []
        self.embed_batch_calls = []
    
    def embed_text(self, text: str) -> list[float]:
        """Generate a deterministic fake embedding for a single text"""
        self.embed_text_calls.append(text)
        return self._generate_embedding(text)
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic fake embeddings for a batch of texts"""
        self.embed_batch_calls.append(texts)
        return [self._generate_embedding(text) for text in texts]
    
    def _generate_embedding(self, text: str) -> list[float]:
        """Generate a deterministic embedding based on text hash"""
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        embedding = []
        for i in range(self.dimension):
            val = ((hash_val + i) % 1000) / 1000.0 - 0.5
            embedding.append(val)
        return embedding
    
    def get_dimension(self) -> int:
        return self.dimension


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# Simple alphanumeric text strategy to avoid slow filtering
alphanumeric_text = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '),
    min_size=5,
    max_size=100
).map(lambda x: x.strip() or 'default')

# Simple alphanumeric content strategy (longer text)
alphanumeric_content = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .'),
    min_size=50,
    max_size=500
).map(lambda x: x.strip() or 'default content for testing purposes')

# Long content strategy for chunking tests
alphanumeric_long_content = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .'),
    min_size=600,
    max_size=1500
).map(lambda x: x.strip() or 'a' * 600)


def article_strategy():
    """
    生成随机文章数据的 Hypothesis 策略
    
    生成符合 KnowledgeBase.add_articles() 要求的文章字典。
    使用简单的字母数字策略以避免慢速过滤。
    """
    return st.fixed_dictionaries({
        'id': st.integers(min_value=1, max_value=100000),
        'title': alphanumeric_text,
        'content': alphanumeric_content,
        'url': st.just('https://example.com/article'),
        'source_type': st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog']),
        'published_date': st.dates().map(lambda d: d.isoformat()),
        'category': st.sampled_from(['AI/机器学习', '安全/隐私', '系统/架构', '其他'])
    })


# =============================================================================
# Property 2: Document Storage Round-Trip
# =============================================================================

class TestDocumentStorageRoundTrip:
    """
    Property 2: Document Storage Round-Trip
    
    For any valid article with content, storing it in the knowledge base and 
    then retrieving it by document ID SHALL return the same content and metadata.
    
    Feature: knowledge-qa-bot, Property 2: Document storage round-trip
    Validates: Requirements 1.2
    """
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        safe_rmtree(temp_path)
    
    @pytest.fixture
    def mock_embedding_service(self):
        """创建 Mock EmbeddingService"""
        return MockEmbeddingService(dimension=1536)
    
    @pytest.fixture
    def knowledge_base(self, temp_dir, mock_embedding_service):
        """创建带有 embedding service 的 KnowledgeBase"""
        config = {
            'chroma_path': os.path.join(temp_dir, 'chroma_db'),
            'collection_name': 'test_roundtrip',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        return kb
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(article=article_strategy())
    def test_document_storage_roundtrip(self, knowledge_base, article):
        """
        Feature: knowledge-qa-bot, Property 2: Document storage round-trip
        **Validates: Requirements 1.2**
        
        Property: For any valid article with content, storing it in the knowledge 
        base and then retrieving it by document ID SHALL return the same content 
        and metadata.
        """
        # Store the article in the knowledge base
        added_count = knowledge_base.add_articles([article])
        
        # Verify at least one document was added
        assert added_count >= 1, "At least one document chunk should be added"
        
        # Retrieve the first chunk by document ID
        doc_id = f"{article['id']}_0"
        retrieved = knowledge_base.get_document(doc_id)
        
        # Verify document was retrieved
        assert retrieved is not None, f"Document {doc_id} should be retrievable"
        
        # Verify content contains the title (title is prepended to content)
        assert article['title'] in retrieved['content'], \
            f"Retrieved content should contain the article title"
        
        # Verify metadata is preserved
        metadata = retrieved['metadata']
        assert metadata['article_id'] == article['id'], \
            "Article ID should be preserved in metadata"
        assert metadata['title'] == article['title'], \
            "Title should be preserved in metadata"
        assert metadata['url'] == article['url'], \
            "URL should be preserved in metadata"
        assert metadata['source_type'] == article['source_type'], \
            "Source type should be preserved in metadata"
        assert metadata['published_date'] == article['published_date'], \
            "Published date should be preserved in metadata"
        assert metadata['category'] == article['category'], \
            "Category should be preserved in metadata"
        assert metadata['chunk_index'] == 0, \
            "First chunk should have chunk_index 0"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(article=article_strategy())
    def test_document_id_format(self, knowledge_base, article):
        """
        Feature: knowledge-qa-bot, Property 2: Document ID format consistency
        **Validates: Requirements 1.2**
        
        Property: Document IDs should follow the format "{article_id}_{chunk_index}".
        """
        knowledge_base.add_articles([article])
        
        # Verify document ID format
        doc_id = f"{article['id']}_0"
        retrieved = knowledge_base.get_document(doc_id)
        
        assert retrieved is not None, "Document should be retrievable by formatted ID"
        assert retrieved['doc_id'] == doc_id, \
            f"Retrieved doc_id should match expected format: {doc_id}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        article=st.fixed_dictionaries({
            'id': st.integers(min_value=1, max_value=100000),
            'title': alphanumeric_text,
            # Generate long content that will be chunked
            'content': alphanumeric_long_content,
            'url': st.just('https://example.com/article'),
            'source_type': st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog']),
            'published_date': st.dates().map(lambda d: d.isoformat()),
            'category': st.sampled_from(['AI/机器学习', '安全/隐私', '系统/架构', '其他'])
        })
    )
    def test_chunked_document_roundtrip(self, knowledge_base, article):
        """
        Feature: knowledge-qa-bot, Property 2: Chunked document storage round-trip
        **Validates: Requirements 1.2**
        
        Property: For articles with long content that gets chunked, each chunk 
        should be retrievable and have consistent metadata.
        """
        # Clear the collection before each example to avoid ID conflicts
        knowledge_base.rebuild()
        
        added_count = knowledge_base.add_articles([article])
        
        # Long content should produce multiple chunks
        assert added_count >= 1, "At least one chunk should be added"
        
        # Verify all chunks are retrievable with consistent metadata
        for i in range(added_count):
            doc_id = f"{article['id']}_{i}"
            retrieved = knowledge_base.get_document(doc_id)
            
            assert retrieved is not None, f"Chunk {i} should be retrievable"
            
            # Verify metadata consistency across chunks
            metadata = retrieved['metadata']
            assert metadata['article_id'] == article['id'], \
                f"Chunk {i}: Article ID should be consistent"
            assert metadata['title'] == article['title'], \
                f"Chunk {i}: Title should be consistent"
            assert metadata['url'] == article['url'], \
                f"Chunk {i}: URL should be consistent"
            assert metadata['source_type'] == article['source_type'], \
                f"Chunk {i}: Source type should be consistent"
            assert metadata['chunk_index'] == i, \
                f"Chunk {i}: chunk_index should match"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(article=article_strategy())
    def test_content_not_empty_after_storage(self, knowledge_base, article):
        """
        Feature: knowledge-qa-bot, Property 2: Content preservation
        **Validates: Requirements 1.2**
        
        Property: Retrieved document content should not be empty.
        """
        knowledge_base.add_articles([article])
        
        doc_id = f"{article['id']}_0"
        retrieved = knowledge_base.get_document(doc_id)
        
        assert retrieved is not None
        assert retrieved['content'], "Retrieved content should not be empty"
        assert len(retrieved['content'].strip()) > 0, \
            "Retrieved content should have non-whitespace characters"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        articles=st.lists(article_strategy(), min_size=2, max_size=5, unique_by=lambda x: x['id'])
    )
    def test_multiple_articles_roundtrip(self, knowledge_base, articles):
        """
        Feature: knowledge-qa-bot, Property 2: Multiple articles storage round-trip
        **Validates: Requirements 1.2**
        
        Property: Multiple articles stored together should all be retrievable 
        with correct content and metadata.
        """
        added_count = knowledge_base.add_articles(articles)
        
        # Verify all articles were added
        assert added_count >= len(articles), \
            "At least one chunk per article should be added"
        
        # Verify each article's first chunk is retrievable by checking metadata
        for article in articles:
            doc_id = f"{article['id']}_0"
            retrieved = knowledge_base.get_document(doc_id)
            
            assert retrieved is not None, \
                f"Article {article['id']} should be retrievable"
            # Check metadata matches - this is the reliable way to verify round-trip
            assert retrieved['metadata']['article_id'] == article['id'], \
                f"Article {article['id']}: metadata article_id should match"
            assert retrieved['metadata']['source_type'] == article['source_type'], \
                f"Article {article['id']}: metadata source_type should match"
            # Content should not be empty
            assert len(retrieved['content'].strip()) > 0, \
                f"Article {article['id']}: content should not be empty"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(article=article_strategy())
    def test_metadata_types_preserved(self, knowledge_base, article):
        """
        Feature: knowledge-qa-bot, Property 2: Metadata type preservation
        **Validates: Requirements 1.2**
        
        Property: Metadata field types should be preserved after storage.
        """
        knowledge_base.add_articles([article])
        
        doc_id = f"{article['id']}_0"
        retrieved = knowledge_base.get_document(doc_id)
        
        assert retrieved is not None
        metadata = retrieved['metadata']
        
        # Verify types are preserved
        assert isinstance(metadata['article_id'], int), \
            "article_id should be an integer"
        assert isinstance(metadata['title'], str), \
            "title should be a string"
        assert isinstance(metadata['url'], str), \
            "url should be a string"
        assert isinstance(metadata['source_type'], str), \
            "source_type should be a string"
        assert isinstance(metadata['published_date'], str), \
            "published_date should be a string"
        assert isinstance(metadata['category'], str), \
            "category should be a string"
        assert isinstance(metadata['chunk_index'], int), \
            "chunk_index should be an integer"


# =============================================================================
# Property 4: Filtered Search Correctness
# =============================================================================

class TestFilteredSearchCorrectness:
    """
    Property 4: Filtered Search Correctness
    
    For any search query with filters (source_type, time_range, topic), all 
    returned documents SHALL satisfy the specified filter conditions. Documents 
    not matching the filters SHALL NOT appear in results.
    
    Feature: knowledge-qa-bot, Property 4: Filtered search returns only matching documents
    **Validates: Requirements 1.4, 4.1, 4.2, 4.3, 4.4**
    """
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        safe_rmtree(temp_path)
    
    @pytest.fixture
    def mock_embedding_service(self):
        """创建 Mock EmbeddingService"""
        return MockEmbeddingService(dimension=1536)
    
    @pytest.fixture
    def knowledge_base(self, temp_dir, mock_embedding_service):
        """创建带有 embedding service 的 KnowledgeBase"""
        config = {
            'chroma_path': os.path.join(temp_dir, 'chroma_db'),
            'collection_name': 'test_filtered_search',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        return kb
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        source_type=st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog'])
    )
    def test_source_type_filter_correctness(self, knowledge_base, source_type):
        """
        Feature: knowledge-qa-bot, Property 4: Source type filter correctness
        **Validates: Requirements 1.4, 4.1, 4.2, 4.3, 4.4**
        
        Property: For any search query with source_type filter, all returned 
        documents SHALL have the specified source_type.
        """
        # Clear the collection before each example
        knowledge_base.rebuild()
        
        # Create articles with different source types
        all_source_types = ['arxiv', 'rss', 'nvd', 'kev', 'blog']
        articles = []
        for i, st_type in enumerate(all_source_types):
            articles.append({
                'id': i + 1,
                'title': f'Article about security topic {i}',
                'content': f'This is content about security and vulnerabilities for source {st_type}. ' * 10,
                'url': f'https://example.com/article{i}',
                'source_type': st_type,
                'published_date': '2024-01-15',
                'category': 'AI/机器学习'
            })
        
        # Add all articles
        knowledge_base.add_articles(articles)
        
        # Search with source_type filter
        results = knowledge_base.search(
            query='security vulnerabilities',
            n_results=10,
            filters={'source_type': source_type}
        )
        
        # Verify all returned documents have the correct source_type
        for result in results:
            assert result['metadata']['source_type'] == source_type, \
                f"Expected source_type '{source_type}', got '{result['metadata']['source_type']}'"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        category=st.sampled_from(['AI/机器学习', '安全/隐私', '系统/架构', '其他'])
    )
    def test_category_filter_correctness(self, knowledge_base, category):
        """
        Feature: knowledge-qa-bot, Property 4: Category filter correctness
        **Validates: Requirements 1.4, 4.1, 4.2, 4.3, 4.4**
        
        Property: For any search query with category filter, all returned 
        documents SHALL have the specified category.
        """
        # Clear the collection before each example
        knowledge_base.rebuild()
        
        # Create articles with different categories
        all_categories = ['AI/机器学习', '安全/隐私', '系统/架构', '其他']
        articles = []
        for i, cat in enumerate(all_categories):
            articles.append({
                'id': i + 1,
                'title': f'Article about technology topic {i}',
                'content': f'This is content about technology and research for category {cat}. ' * 10,
                'url': f'https://example.com/article{i}',
                'source_type': 'arxiv',
                'published_date': '2024-01-15',
                'category': cat
            })
        
        # Add all articles
        knowledge_base.add_articles(articles)
        
        # Search with category filter
        results = knowledge_base.search(
            query='technology research',
            n_results=10,
            filters={'category': category}
        )
        
        # Verify all returned documents have the correct category
        for result in results:
            assert result['metadata']['category'] == category, \
                f"Expected category '{category}', got '{result['metadata']['category']}'"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        source_type=st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog']),
        category=st.sampled_from(['AI/机器学习', '安全/隐私', '系统/架构', '其他'])
    )
    def test_combined_filters_correctness(self, knowledge_base, source_type, category):
        """
        Feature: knowledge-qa-bot, Property 4: Combined filters correctness
        **Validates: Requirements 1.4, 4.1, 4.2, 4.3, 4.4**
        
        Property: For any search query with multiple filters (source_type AND 
        category), all returned documents SHALL satisfy ALL filter conditions.
        """
        # Clear the collection before each example
        knowledge_base.rebuild()
        
        # Create articles with various combinations of source_type and category
        all_source_types = ['arxiv', 'rss', 'nvd', 'kev', 'blog']
        all_categories = ['AI/机器学习', '安全/隐私', '系统/架构', '其他']
        
        articles = []
        article_id = 1
        for st_type in all_source_types:
            for cat in all_categories:
                articles.append({
                    'id': article_id,
                    'title': f'Article {article_id} about research',
                    'content': f'This is content about research and analysis for {st_type} {cat}. ' * 10,
                    'url': f'https://example.com/article{article_id}',
                    'source_type': st_type,
                    'published_date': '2024-01-15',
                    'category': cat
                })
                article_id += 1
        
        # Add all articles
        knowledge_base.add_articles(articles)
        
        # Search with combined filters
        results = knowledge_base.search(
            query='research analysis',
            n_results=20,
            filters={'source_type': source_type, 'category': category}
        )
        
        # Verify all returned documents satisfy BOTH filter conditions
        for result in results:
            assert result['metadata']['source_type'] == source_type, \
                f"Expected source_type '{source_type}', got '{result['metadata']['source_type']}'"
            assert result['metadata']['category'] == category, \
                f"Expected category '{category}', got '{result['metadata']['category']}'"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        source_type=st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog'])
    )
    def test_filter_excludes_non_matching_documents(self, knowledge_base, source_type):
        """
        Feature: knowledge-qa-bot, Property 4: Filter exclusion correctness
        **Validates: Requirements 1.4, 4.1, 4.2, 4.3, 4.4**
        
        Property: Documents not matching the filters SHALL NOT appear in results.
        """
        # Clear the collection before each example
        knowledge_base.rebuild()
        
        # Create articles with different source types
        all_source_types = ['arxiv', 'rss', 'nvd', 'kev', 'blog']
        non_matching_types = [st for st in all_source_types if st != source_type]
        
        articles = []
        for i, st_type in enumerate(all_source_types):
            articles.append({
                'id': i + 1,
                'title': f'Article about machine learning {i}',
                'content': f'This is content about machine learning and AI for source {st_type}. ' * 10,
                'url': f'https://example.com/article{i}',
                'source_type': st_type,
                'published_date': '2024-01-15',
                'category': 'AI/机器学习'
            })
        
        # Add all articles
        knowledge_base.add_articles(articles)
        
        # Search with source_type filter
        results = knowledge_base.search(
            query='machine learning AI',
            n_results=10,
            filters={'source_type': source_type}
        )
        
        # Verify NO documents with non-matching source_type appear in results
        for result in results:
            assert result['metadata']['source_type'] not in non_matching_types, \
                f"Non-matching source_type '{result['metadata']['source_type']}' should not appear in results"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        source_types=st.lists(
            st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog']),
            min_size=1,
            max_size=3,
            unique=True
        )
    )
    def test_multiple_source_types_filter(self, knowledge_base, source_types):
        """
        Feature: knowledge-qa-bot, Property 4: Multiple source types filter
        **Validates: Requirements 1.4, 4.1, 4.2, 4.3, 4.4**
        
        Property: For any search query with a list of source_types, all returned 
        documents SHALL have a source_type that is in the specified list.
        """
        # Clear the collection before each example
        knowledge_base.rebuild()
        
        # Create articles with different source types
        all_source_types = ['arxiv', 'rss', 'nvd', 'kev', 'blog']
        articles = []
        for i, st_type in enumerate(all_source_types):
            articles.append({
                'id': i + 1,
                'title': f'Article about cybersecurity {i}',
                'content': f'This is content about cybersecurity and threats for source {st_type}. ' * 10,
                'url': f'https://example.com/article{i}',
                'source_type': st_type,
                'published_date': '2024-01-15',
                'category': '安全/隐私'
            })
        
        # Add all articles
        knowledge_base.add_articles(articles)
        
        # Search with multiple source_types filter
        results = knowledge_base.search(
            query='cybersecurity threats',
            n_results=10,
            filters={'source_type': source_types}
        )
        
        # Verify all returned documents have a source_type in the specified list
        for result in results:
            assert result['metadata']['source_type'] in source_types, \
                f"source_type '{result['metadata']['source_type']}' should be in {source_types}"


# =============================================================================
# Property 7: Retrieval Relevance Scoring
# =============================================================================

class TestRetrievalRelevanceScoring:
    """
    Property 7: Retrieval Relevance Scoring
    
    For any semantic search query, all returned documents SHALL have a relevance 
    score between 0 and 1, and documents SHALL be ordered by descending relevance 
    score.
    
    Feature: knowledge-qa-bot, Property 7: Retrieval returns ordered relevant documents
    **Validates: Requirements 3.2, 3.4**
    """
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        safe_rmtree(temp_path)
    
    @pytest.fixture
    def mock_embedding_service(self):
        """创建 Mock EmbeddingService"""
        return MockEmbeddingService(dimension=1536)
    
    @pytest.fixture
    def knowledge_base_with_data(self, temp_dir, mock_embedding_service):
        """创建预填充数据的 KnowledgeBase"""
        config = {
            'chroma_path': os.path.join(temp_dir, 'chroma_db'),
            'collection_name': 'test_relevance_scoring',
            'chunk_size': 500,
            'chunk_overlap': 50
        }
        kb = KnowledgeBase(config, embedding_service=mock_embedding_service)
        
        # 预填充一些文章数据
        articles = [
            {
                'id': 1,
                'title': 'Introduction to Machine Learning',
                'content': 'Machine learning is a subset of artificial intelligence that enables systems to learn from data. ' * 10,
                'url': 'https://example.com/ml-intro',
                'source_type': 'arxiv',
                'published_date': '2024-01-15',
                'category': 'AI/机器学习'
            },
            {
                'id': 2,
                'title': 'Deep Learning Neural Networks',
                'content': 'Deep learning uses neural networks with multiple layers to process complex patterns. ' * 10,
                'url': 'https://example.com/deep-learning',
                'source_type': 'rss',
                'published_date': '2024-01-16',
                'category': 'AI/机器学习'
            },
            {
                'id': 3,
                'title': 'Cybersecurity Best Practices',
                'content': 'Security vulnerabilities can be mitigated through proper authentication and encryption. ' * 10,
                'url': 'https://example.com/security',
                'source_type': 'nvd',
                'published_date': '2024-01-17',
                'category': '安全/隐私'
            },
            {
                'id': 4,
                'title': 'Natural Language Processing',
                'content': 'NLP enables computers to understand and generate human language using transformers. ' * 10,
                'url': 'https://example.com/nlp',
                'source_type': 'blog',
                'published_date': '2024-01-18',
                'category': 'AI/机器学习'
            },
            {
                'id': 5,
                'title': 'Cloud Computing Architecture',
                'content': 'Cloud systems provide scalable infrastructure for modern applications and services. ' * 10,
                'url': 'https://example.com/cloud',
                'source_type': 'kev',
                'published_date': '2024-01-19',
                'category': '系统/架构'
            }
        ]
        
        kb.add_articles(articles)
        return kb
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        query=st.text(
            alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '),
            min_size=3,
            max_size=50
        ).map(lambda x: x.strip() or 'test query')
    )
    def test_retrieval_scores_in_valid_range(self, knowledge_base_with_data, query):
        """
        Feature: knowledge-qa-bot, Property 7: Retrieval relevance scores in valid range
        **Validates: Requirements 3.2, 3.4**
        
        Property: For any semantic search query, all returned documents SHALL have 
        a relevance score between 0 and 1.
        """
        results = knowledge_base_with_data.search(query, n_results=5)
        
        # Verify all scores are in [0, 1] range
        for result in results:
            score = result['score']
            assert isinstance(score, (int, float)), \
                f"Score should be a number, got {type(score)}"
            assert 0 <= score <= 1, \
                f"Score {score} should be in range [0, 1]"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        query=st.text(
            alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '),
            min_size=3,
            max_size=50
        ).map(lambda x: x.strip() or 'test query')
    )
    def test_retrieval_results_ordered_by_descending_score(self, knowledge_base_with_data, query):
        """
        Feature: knowledge-qa-bot, Property 7: Retrieval results ordered by descending score
        **Validates: Requirements 3.2, 3.4**
        
        Property: For any semantic search query, documents SHALL be ordered by 
        descending relevance score.
        """
        results = knowledge_base_with_data.search(query, n_results=5)
        
        if len(results) <= 1:
            # Single or no results are trivially ordered
            return
        
        # Extract scores
        scores = [result['score'] for result in results]
        
        # Verify scores are in descending order
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], \
                f"Scores should be in descending order: {scores[i]} >= {scores[i + 1]} failed at index {i}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        n_results=st.integers(min_value=1, max_value=10)
    )
    def test_retrieval_respects_n_results_limit(self, knowledge_base_with_data, n_results):
        """
        Feature: knowledge-qa-bot, Property 7: Retrieval respects n_results limit
        **Validates: Requirements 3.2, 3.4**
        
        Property: The number of returned results SHALL NOT exceed n_results.
        """
        results = knowledge_base_with_data.search('machine learning', n_results=n_results)
        
        # Verify result count does not exceed n_results
        assert len(results) <= n_results, \
            f"Expected at most {n_results} results, got {len(results)}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        query=st.text(
            alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '),
            min_size=3,
            max_size=50
        ).map(lambda x: x.strip() or 'test query')
    )
    def test_retrieval_results_contain_required_fields(self, knowledge_base_with_data, query):
        """
        Feature: knowledge-qa-bot, Property 7: Retrieval results contain required fields
        **Validates: Requirements 3.2, 3.4**
        
        Property: Each returned document SHALL contain doc_id, content, metadata, 
        and score fields.
        """
        results = knowledge_base_with_data.search(query, n_results=5)
        
        required_fields = ['doc_id', 'content', 'metadata', 'score']
        
        for result in results:
            for field in required_fields:
                assert field in result, \
                    f"Result should contain '{field}' field"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        source_type=st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog'])
    )
    def test_filtered_retrieval_scores_in_valid_range(self, knowledge_base_with_data, source_type):
        """
        Feature: knowledge-qa-bot, Property 7: Filtered retrieval scores in valid range
        **Validates: Requirements 3.2, 3.4**
        
        Property: For any filtered search query, all returned documents SHALL have 
        a relevance score between 0 and 1.
        """
        results = knowledge_base_with_data.search(
            query='technology research',
            n_results=5,
            filters={'source_type': source_type}
        )
        
        # Verify all scores are in [0, 1] range
        for result in results:
            score = result['score']
            assert 0 <= score <= 1, \
                f"Score {score} should be in range [0, 1]"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        source_type=st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog'])
    )
    def test_filtered_retrieval_ordered_by_descending_score(self, knowledge_base_with_data, source_type):
        """
        Feature: knowledge-qa-bot, Property 7: Filtered retrieval ordered by descending score
        **Validates: Requirements 3.2, 3.4**
        
        Property: For any filtered search query, documents SHALL be ordered by 
        descending relevance score.
        """
        results = knowledge_base_with_data.search(
            query='technology research',
            n_results=5,
            filters={'source_type': source_type}
        )
        
        if len(results) <= 1:
            return
        
        scores = [result['score'] for result in results]
        
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], \
                f"Filtered scores should be in descending order: {scores[i]} >= {scores[i + 1]} failed"
