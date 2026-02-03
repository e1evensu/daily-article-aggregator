"""
EmbeddingService 单元测试

测试文本向量化服务的基本功能。

Requirements:
    - 1.1: 支持将文章内容转换为向量嵌入（Embedding）
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import math

from src.qa.embedding_service import (
    EmbeddingService,
    create_embedding_service,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_DIMENSION,
)


class TestEmbeddingServiceInit:
    """测试 EmbeddingService 初始化"""
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        config = {
            'api_key': 'test-key'
        }
        service = EmbeddingService(config)
        
        assert service.model == DEFAULT_EMBEDDING_MODEL
        assert service.dimension == DEFAULT_EMBEDDING_DIMENSION
        assert service.max_retries == 3
        assert service.timeout == 60
    
    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        config = {
            'api_base': 'https://custom.api.com/v1',
            'api_key': 'custom-key',
            'model': 'custom-embedding-model',
            'dimension': 768,
            'timeout': 30,
            'max_retries': 5
        }
        service = EmbeddingService(config)
        
        assert service.model == 'custom-embedding-model'
        assert service.dimension == 768
        assert service.timeout == 30
        assert service.max_retries == 5
    
    def test_init_without_api_key(self):
        """测试没有 API key 时的初始化（应该警告但不报错）"""
        config = {}
        # 不应该抛出异常
        service = EmbeddingService(config)
        assert service.model == DEFAULT_EMBEDDING_MODEL
    
    def test_get_dimension(self):
        """测试获取向量维度"""
        config = {'api_key': 'test-key', 'dimension': 1024}
        service = EmbeddingService(config)
        
        assert service.get_dimension() == 1024


class TestEmbedText:
    """测试 embed_text 方法"""
    
    def test_embed_text_empty_input(self):
        """测试空输入应该抛出 ValueError"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        with pytest.raises(ValueError, match="Input text cannot be empty"):
            service.embed_text("")
        
        with pytest.raises(ValueError, match="Input text cannot be empty"):
            service.embed_text("   ")
    
    def test_embed_text_success(self):
        """测试成功的文本向量化"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        # 创建模拟的 API 响应
        mock_embedding = [0.1] * 1536
        mock_response = Mock()
        mock_response.data = [Mock(embedding=mock_embedding, index=0)]
        
        with patch.object(service.client.embeddings, 'create', return_value=mock_response):
            result = service.embed_text("Hello, world!")
        
        assert result == mock_embedding
        assert len(result) == 1536
    
    def test_embed_text_cleans_whitespace(self):
        """测试文本清理（多余空白）"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        mock_embedding = [0.1] * 1536
        mock_response = Mock()
        mock_response.data = [Mock(embedding=mock_embedding, index=0)]
        
        with patch.object(service.client.embeddings, 'create', return_value=mock_response) as mock_create:
            service.embed_text("  Hello   world  ")
            
            # 验证传递给 API 的文本已被清理
            call_args = mock_create.call_args
            assert call_args.kwargs['input'] == "Hello world"


class TestEmbedBatch:
    """测试 embed_batch 方法"""
    
    def test_embed_batch_empty_list(self):
        """测试空列表应该抛出 ValueError"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        with pytest.raises(ValueError, match="Input text list cannot be empty"):
            service.embed_batch([])
    
    def test_embed_batch_all_empty_texts(self):
        """测试所有文本都为空应该抛出 ValueError"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        with pytest.raises(ValueError, match="All input texts are empty"):
            service.embed_batch(["", "   ", ""])
    
    def test_embed_batch_success(self):
        """测试成功的批量向量化"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        # 创建模拟的 API 响应
        mock_embeddings = [[0.1] * 1536, [0.2] * 1536]
        mock_response = Mock()
        mock_response.data = [
            Mock(embedding=mock_embeddings[0], index=0),
            Mock(embedding=mock_embeddings[1], index=1)
        ]
        
        with patch.object(service.client.embeddings, 'create', return_value=mock_response):
            result = service.embed_batch(["Hello", "World"])
        
        assert len(result) == 2
        assert result[0] == mock_embeddings[0]
        assert result[1] == mock_embeddings[1]
    
    def test_embed_batch_with_empty_texts(self):
        """测试批量向量化时跳过空文本"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        # 创建模拟的 API 响应（只有2个有效文本）
        mock_embeddings = [[0.1] * 1536, [0.2] * 1536]
        mock_response = Mock()
        mock_response.data = [
            Mock(embedding=mock_embeddings[0], index=0),
            Mock(embedding=mock_embeddings[1], index=1)
        ]
        
        with patch.object(service.client.embeddings, 'create', return_value=mock_response):
            result = service.embed_batch(["Hello", "", "World", "   "])
        
        # 结果应该有4个元素，但空文本位置是空列表
        assert len(result) == 4
        assert result[0] == mock_embeddings[0]
        assert result[1] == []  # 空文本
        assert result[2] == mock_embeddings[1]
        assert result[3] == []  # 空文本
    
    def test_embed_batch_preserves_order(self):
        """测试批量向量化保持顺序"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        # 创建模拟的 API 响应（乱序返回）
        mock_embeddings = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]
        mock_response = Mock()
        # 故意乱序
        mock_response.data = [
            Mock(embedding=mock_embeddings[2], index=2),
            Mock(embedding=mock_embeddings[0], index=0),
            Mock(embedding=mock_embeddings[1], index=1)
        ]
        
        with patch.object(service.client.embeddings, 'create', return_value=mock_response):
            result = service.embed_batch(["A", "B", "C"])
        
        # 结果应该按原始顺序排列
        assert result[0] == mock_embeddings[0]
        assert result[1] == mock_embeddings[1]
        assert result[2] == mock_embeddings[2]


class TestCreateEmbeddingService:
    """测试 create_embedding_service 工厂函数"""
    
    def test_create_from_full_config(self):
        """测试从完整配置创建服务"""
        config = {
            'ai': {
                'api_base': 'https://api.openai.com/v1',
                'api_key': 'sk-test-key',
                'timeout': 30
            },
            'knowledge_qa': {
                'embedding': {
                    'model': 'text-embedding-3-small'
                }
            }
        }
        
        service = create_embedding_service(config)
        
        assert service.model == 'text-embedding-3-small'
        assert service.timeout == 30
    
    def test_create_with_embedding_override(self):
        """测试 Embedding 配置覆盖 AI 配置"""
        config = {
            'ai': {
                'api_base': 'https://api.openai.com/v1',
                'api_key': 'sk-ai-key'
            },
            'knowledge_qa': {
                'embedding': {
                    'api_base': 'https://custom.embedding.api/v1',
                    'api_key': 'sk-embedding-key',
                    'model': 'custom-model'
                }
            }
        }
        
        service = create_embedding_service(config)
        
        # Embedding 配置应该覆盖 AI 配置
        assert service.model == 'custom-model'
    
    def test_create_with_minimal_config(self):
        """测试使用最小配置创建服务"""
        config = {
            'ai': {
                'api_key': 'sk-test-key'
            }
        }
        
        service = create_embedding_service(config)
        
        assert service.model == DEFAULT_EMBEDDING_MODEL


class TestEmbeddingVectorValidity:
    """测试向量有效性（Property 1 相关）"""
    
    def test_vector_dimension_matches_config(self):
        """测试向量维度与配置匹配"""
        config = {'api_key': 'test-key', 'dimension': 1536}
        service = EmbeddingService(config)
        
        # 创建模拟的 API 响应
        mock_embedding = [0.1] * 1536
        mock_response = Mock()
        mock_response.data = [Mock(embedding=mock_embedding, index=0)]
        
        with patch.object(service.client.embeddings, 'create', return_value=mock_response):
            result = service.embed_text("Test text")
        
        assert len(result) == 1536
    
    def test_vector_contains_finite_floats(self):
        """测试向量包含有限浮点数"""
        config = {'api_key': 'test-key'}
        service = EmbeddingService(config)
        
        # 创建包含有效浮点数的模拟响应
        mock_embedding = [0.1, -0.2, 0.0, 0.5, -0.8] + [0.1] * 1531
        mock_response = Mock()
        mock_response.data = [Mock(embedding=mock_embedding, index=0)]
        
        with patch.object(service.client.embeddings, 'create', return_value=mock_response):
            result = service.embed_text("Test text")
        
        # 验证所有值都是有限浮点数
        assert all(isinstance(v, float) for v in result)
        assert all(math.isfinite(v) for v in result)
