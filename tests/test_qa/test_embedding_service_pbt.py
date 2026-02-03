"""
EmbeddingService 属性测试 (Property-Based Tests)

使用 Hypothesis 进行属性测试，验证 EmbeddingService 的正确性属性。

Feature: knowledge-qa-bot
Property 1: Embedding Generation Validity
Validates: Requirements 1.1
"""

import math
from unittest.mock import Mock, patch

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

from src.qa.embedding_service import (
    EmbeddingService,
    DEFAULT_EMBEDDING_DIMENSION,
)


# =============================================================================
# Helper Functions
# =============================================================================

def create_embedding_service(dimension: int = DEFAULT_EMBEDDING_DIMENSION) -> EmbeddingService:
    """创建 EmbeddingService 实例用于测试"""
    config = {
        'api_key': 'test-key',
        'model': 'text-embedding-3-small',
        'dimension': dimension,
    }
    return EmbeddingService(config)


def create_mock_embedding(dimension: int = DEFAULT_EMBEDDING_DIMENSION) -> list[float]:
    """创建模拟的有效向量嵌入"""
    import random
    return [random.uniform(-1.0, 1.0) for _ in range(dimension)]


def create_mock_response(embedding: list[float], index: int = 0) -> Mock:
    """创建模拟的 API 响应"""
    mock_response = Mock()
    mock_response.data = [Mock(embedding=embedding, index=index)]
    return mock_response


# Simple text strategy - alphanumeric only, no filtering needed
simple_text = st.text(alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789 '), min_size=3, max_size=50)


# =============================================================================
# Property 1: Embedding Generation Validity
# =============================================================================

class TestEmbeddingGenerationValidity:
    """
    Property 1: Embedding Generation Validity
    
    Feature: knowledge-qa-bot, Property 1: Embedding generation produces valid vectors
    Validates: Requirements 1.1
    """
    
    @settings(max_examples=5, deadline=None)
    @given(text=simple_text)
    def test_embedding_generation_validity(self, text):
        """
        Feature: knowledge-qa-bot, Property 1: Embedding generation produces valid vectors
        Validates: Requirements 1.1
        """
        assume(text.strip())
        embedding_service = create_embedding_service()
        mock_embedding = create_mock_embedding()
        mock_response = create_mock_response(mock_embedding)
        
        with patch.object(embedding_service.client.embeddings, 'create', return_value=mock_response):
            vector = embedding_service.embed_text(text)
        
        assert isinstance(vector, list)
        assert len(vector) == DEFAULT_EMBEDDING_DIMENSION
        assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector)
    
    @settings(max_examples=5, deadline=None)
    @given(text=simple_text, dimension=st.sampled_from([384, 768, 1536]))
    def test_embedding_dimension_matches_config(self, text, dimension):
        """
        Feature: knowledge-qa-bot, Property 1: Embedding dimension matches configuration
        Validates: Requirements 1.1
        """
        assume(text.strip())
        service = create_embedding_service(dimension)
        mock_embedding = create_mock_embedding(dimension)
        mock_response = create_mock_response(mock_embedding)
        
        with patch.object(service.client.embeddings, 'create', return_value=mock_response):
            vector = service.embed_text(text)
        
        assert len(vector) == dimension
        assert service.get_dimension() == dimension
    
    @settings(max_examples=5, deadline=None)
    @given(texts=st.lists(simple_text, min_size=1, max_size=3))
    def test_batch_embedding_validity(self, texts):
        """
        Feature: knowledge-qa-bot, Property 1: Batch embedding produces valid vectors
        Validates: Requirements 1.1
        """
        texts = [t for t in texts if t.strip()]
        assume(len(texts) > 0)
        
        embedding_service = create_embedding_service()
        mock_embeddings = [create_mock_embedding() for _ in range(len(texts))]
        mock_response = Mock()
        mock_response.data = [Mock(embedding=emb, index=i) for i, emb in enumerate(mock_embeddings)]
        
        with patch.object(embedding_service.client.embeddings, 'create', return_value=mock_response):
            vectors = embedding_service.embed_batch(texts)
        
        assert len(vectors) == len(texts)
        for vector in vectors:
            assert len(vector) == DEFAULT_EMBEDDING_DIMENSION
            assert all(math.isfinite(v) for v in vector)
    
    @settings(max_examples=5, deadline=None)
    @given(text=simple_text, seed_value=st.integers(min_value=0, max_value=100))
    def test_embedding_values_are_finite(self, text, seed_value):
        """
        Feature: knowledge-qa-bot, Property 1: All embedding values are finite
        Validates: Requirements 1.1
        """
        assume(text.strip())
        import random
        random.seed(seed_value)
        vector_values = [random.uniform(-1.0, 1.0) for _ in range(DEFAULT_EMBEDDING_DIMENSION)]
        
        embedding_service = create_embedding_service()
        mock_response = create_mock_response(vector_values)
        
        with patch.object(embedding_service.client.embeddings, 'create', return_value=mock_response):
            vector = embedding_service.embed_text(text)
        
        assert all(math.isfinite(v) for v in vector)
        assert not any(math.isnan(v) for v in vector)
        assert not any(math.isinf(v) for v in vector)


class TestEmbeddingInputHandling:
    """测试 EmbeddingService 对各种输入的处理"""
    
    @settings(max_examples=5, deadline=None)
    @given(whitespace=st.text(alphabet=' \t\n\r', min_size=1, max_size=5))
    def test_empty_or_whitespace_input_raises_error(self, whitespace):
        """
        Feature: knowledge-qa-bot, Property 1: Empty input handling
        Validates: Requirements 1.1
        """
        embedding_service = create_embedding_service()
        with pytest.raises(ValueError, match="Input text cannot be empty"):
            embedding_service.embed_text(whitespace)
    
    @settings(max_examples=5, deadline=None)
    @given(text=simple_text, extra_ws=st.text(alphabet=' \t', min_size=0, max_size=3))
    def test_whitespace_normalization(self, text, extra_ws):
        """
        Feature: knowledge-qa-bot, Property 1: Whitespace normalization
        Validates: Requirements 1.1
        """
        assume(text.strip())
        text_with_ws = extra_ws + text + extra_ws
        
        embedding_service = create_embedding_service()
        mock_embedding = create_mock_embedding()
        mock_response = create_mock_response(mock_embedding)
        
        with patch.object(embedding_service.client.embeddings, 'create', return_value=mock_response) as mock_create:
            vector = embedding_service.embed_text(text_with_ws)
            cleaned_input = mock_create.call_args.kwargs['input']
            assert cleaned_input == cleaned_input.strip()
        
        assert len(vector) == DEFAULT_EMBEDDING_DIMENSION


class TestEmbeddingServiceConfiguration:
    """测试 EmbeddingService 配置相关的属性"""
    
    @settings(max_examples=5, deadline=None)
    @given(dimension=st.integers(min_value=64, max_value=2048))
    def test_get_dimension_returns_configured_value(self, dimension):
        """
        Feature: knowledge-qa-bot, Property 1: Dimension configuration
        Validates: Requirements 1.1
        """
        service = create_embedding_service(dimension)
        assert service.get_dimension() == dimension
