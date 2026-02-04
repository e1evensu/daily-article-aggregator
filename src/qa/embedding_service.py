"""
文本向量化服务模块

提供文本到向量嵌入的转换功能，支持 OpenAI 兼容 API。
复用现有 AI 配置（api_base, api_key）。

Requirements:
    - 1.1: 支持将文章内容转换为向量嵌入（Embedding）
"""

import logging
import time
from typing import Any

from openai import OpenAI, APIError, APITimeoutError, APIConnectionError, RateLimitError

# 配置日志
logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"  # SiliconFlow 支持的模型
DEFAULT_EMBEDDING_DIMENSION = 4096  # Qwen3-Embedding-8B 的默认维度
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # 初始重试延迟（秒）
DEFAULT_RATE_LIMIT_DELAY = 0.2  # 默认请求间隔（秒）


class EmbeddingService:
    """
    文本向量化服务，支持 OpenAI 和兼容 API
    
    将文本转换为向量嵌入，用于语义搜索和相似度计算。
    
    Attributes:
        client: OpenAI 客户端实例
        model: Embedding 模型名称
        dimension: 向量维度
        max_retries: 最大重试次数
        timeout: API 调用超时时间（秒）
    
    Requirements: 1.1
    """
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化向量化服务
        
        Args:
            config: 配置字典，包含：
                - api_base: API 地址（可选，默认 https://api.openai.com/v1）
                - api_key: API 密钥（必需）
                - model: 模型名称（可选，默认 text-embedding-3-small）
                - dimension: 向量维度（可选，默认 1536）
                - timeout: 超时时间秒数（可选，默认 60）
                - max_retries: 最大重试次数（可选，默认 3）
                - rate_limit_delay: 请求间隔秒数（可选，默认 0.2）
        
        Examples:
            >>> config = {
            ...     'api_base': 'https://api.siliconflow.cn/v1',
            ...     'api_key': 'sk-xxx',
            ...     'model': 'BAAI/bge-m3'
            ... }
            >>> service = EmbeddingService(config)
        
        Requirements: 1.1
        """
        # 提取配置参数
        api_base = config.get('api_base', 'https://api.openai.com/v1')
        api_key = config.get('api_key', '')
        
        if not api_key:
            logger.warning("EmbeddingService initialized without API key")
        
        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            base_url=api_base,
            api_key=api_key
        )
        
        # 模型配置
        self.model = config.get('model', DEFAULT_EMBEDDING_MODEL)
        self.dimension = config.get('dimension', DEFAULT_EMBEDDING_DIMENSION)
        self.timeout = float(config.get('timeout', 60))
        self.max_retries = int(config.get('max_retries', MAX_RETRIES))
        self.rate_limit_delay = float(config.get('rate_limit_delay', DEFAULT_RATE_LIMIT_DELAY))
        self._last_request_time = 0.0
        
        logger.info(
            f"EmbeddingService initialized with model: {self.model}, "
            f"dimension: {self.dimension}, api_base: {api_base}"
        )
    
    def _wait_for_rate_limit(self) -> None:
        """等待以满足限速要求"""
        if self.rate_limit_delay > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def embed_text(self, text: str) -> list[float]:
        """
        将单个文本转换为向量
        
        Args:
            text: 待向量化的文本
        
        Returns:
            向量嵌入（浮点数列表）
        
        Raises:
            ValueError: 输入文本为空
            RuntimeError: API 调用失败（重试后仍失败）
        
        Examples:
            >>> service = EmbeddingService(config)
            >>> vector = service.embed_text("Hello, world!")
            >>> len(vector)
            1024
            >>> all(isinstance(v, float) for v in vector)
            True
        
        Requirements: 1.1
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty")
        
        # 清理文本（移除多余空白）
        cleaned_text = ' '.join(text.split())
        
        # 限速：确保请求间隔
        self._wait_for_rate_limit()
        
        # 使用重试机制调用 API
        last_error: Exception | None = None
        retry_delay = INITIAL_RETRY_DELAY
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=cleaned_text,
                    timeout=self.timeout
                )
                
                # 提取向量
                if response.data and len(response.data) > 0:
                    embedding = response.data[0].embedding
                    logger.debug(
                        f"Successfully embedded text (length: {len(cleaned_text)}, "
                        f"vector dim: {len(embedding)})"
                    )
                    return embedding
                
                raise RuntimeError("API response contains no embedding data")
                
            except RateLimitError as e:
                last_error = e
                # 获取 retry-after 时间（如果有）
                retry_after = getattr(e, 'retry_after', None)
                wait_time = float(retry_after) if retry_after else retry_delay
                
                logger.warning(
                    f"Rate limit hit, waiting {wait_time}s before retry "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                time.sleep(wait_time)
                retry_delay *= 2  # 指数退避
                
            except APITimeoutError as e:
                last_error = e
                logger.warning(
                    f"API timeout, retrying in {retry_delay}s "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                time.sleep(retry_delay)
                retry_delay *= 2
                
            except APIConnectionError as e:
                last_error = e
                logger.warning(
                    f"API connection error, retrying in {retry_delay}s "
                    f"(attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                time.sleep(retry_delay)
                retry_delay *= 2
                
            except APIError as e:
                last_error = e
                logger.error(f"API error on attempt {attempt + 1}: {e}")
                # 对于非临时性错误，不重试
                if e.status_code and e.status_code < 500:
                    raise RuntimeError(f"API error: {e}") from e
                time.sleep(retry_delay)
                retry_delay *= 2
        
        # 所有重试都失败
        error_msg = f"Failed to embed text after {self.max_retries} attempts"
        logger.error(f"{error_msg}: {last_error}")
        raise RuntimeError(error_msg) from last_error
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量向量化文本
        
        Args:
            texts: 待向量化的文本列表
        
        Returns:
            向量嵌入列表，每个元素对应输入文本的向量
        
        Raises:
            ValueError: 输入列表为空或包含空文本
            RuntimeError: API 调用失败（重试后仍失败）
        
        Examples:
            >>> service = EmbeddingService(config)
            >>> vectors = service.embed_batch(["Hello", "World"])
            >>> len(vectors)
            2
            >>> all(len(v) == 4096 for v in vectors)
            True
        
        Requirements: 1.1
        """
        if not texts:
            raise ValueError("Input text list cannot be empty")
        
        # 清理文本并过滤空文本
        cleaned_texts = []
        valid_indices = []
        
        for i, text in enumerate(texts):
            if text and text.strip():
                cleaned_texts.append(' '.join(text.split()))
                valid_indices.append(i)
            else:
                logger.warning(f"Skipping empty text at index {i}")
        
        if not cleaned_texts:
            raise ValueError("All input texts are empty")
        
        # 限速：确保请求间隔
        self._wait_for_rate_limit()
        
        if not cleaned_texts:
            raise ValueError("All input texts are empty")
        
        # 使用重试机制调用 API
        last_error: Exception | None = None
        retry_delay = INITIAL_RETRY_DELAY
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=cleaned_texts,
                    timeout=self.timeout
                )
                
                # 提取向量
                if response.data and len(response.data) == len(cleaned_texts):
                    # 按索引排序（API 可能不保证顺序）
                    sorted_data = sorted(response.data, key=lambda x: x.index)
                    embeddings = [item.embedding for item in sorted_data]
                    
                    logger.info(
                        f"Successfully embedded {len(embeddings)} texts "
                        f"(vector dim: {len(embeddings[0]) if embeddings else 0})"
                    )
                    
                    # 如果有跳过的空文本，需要在对应位置插入空向量
                    if len(valid_indices) < len(texts):
                        result = [[] for _ in range(len(texts))]
                        for idx, embedding in zip(valid_indices, embeddings):
                            result[idx] = embedding
                        return result
                    
                    return embeddings
                
                raise RuntimeError(
                    f"API response count mismatch: expected {len(cleaned_texts)}, "
                    f"got {len(response.data) if response.data else 0}"
                )
                
            except RateLimitError as e:
                last_error = e
                retry_after = getattr(e, 'retry_after', None)
                wait_time = float(retry_after) if retry_after else retry_delay
                
                logger.warning(
                    f"Rate limit hit, waiting {wait_time}s before retry "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                time.sleep(wait_time)
                retry_delay *= 2
                
            except APITimeoutError as e:
                last_error = e
                logger.warning(
                    f"API timeout, retrying in {retry_delay}s "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                time.sleep(retry_delay)
                retry_delay *= 2
                
            except APIConnectionError as e:
                last_error = e
                logger.warning(
                    f"API connection error, retrying in {retry_delay}s "
                    f"(attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                time.sleep(retry_delay)
                retry_delay *= 2
                
            except APIError as e:
                last_error = e
                logger.error(f"API error on attempt {attempt + 1}: {e}")
                if e.status_code and e.status_code < 500:
                    raise RuntimeError(f"API error: {e}") from e
                time.sleep(retry_delay)
                retry_delay *= 2
        
        # 所有重试都失败
        error_msg = f"Failed to embed batch after {self.max_retries} attempts"
        logger.error(f"{error_msg}: {last_error}")
        raise RuntimeError(error_msg) from last_error
    
    def get_dimension(self) -> int:
        """
        获取向量维度
        
        Returns:
            向量维度
        
        Examples:
            >>> service = EmbeddingService(config)
            >>> service.get_dimension()
            1536
        """
        return self.dimension


def create_embedding_service(config: dict[str, Any]) -> EmbeddingService:
    """
    创建 EmbeddingService 实例的工厂函数
    
    从完整配置中提取 AI 配置和 Embedding 配置，创建服务实例。
    复用现有 AI 配置（api_base, api_key）。
    
    Args:
        config: 完整配置字典，应包含：
            - ai: AI 配置（api_base, api_key）
            - knowledge_qa.embedding: Embedding 配置（model）
    
    Returns:
        EmbeddingService 实例
    
    Examples:
        >>> config = {
        ...     'ai': {
        ...         'api_base': 'https://api.openai.com/v1',
        ...         'api_key': 'sk-xxx'
        ...     },
        ...     'knowledge_qa': {
        ...         'embedding': {
        ...             'model': 'text-embedding-3-small'
        ...         }
        ...     }
        ... }
        >>> service = create_embedding_service(config)
    
    Requirements: 1.1
    """
    # 提取 AI 配置
    ai_config = config.get('ai', {})
    api_base = ai_config.get('api_base', 'https://api.openai.com/v1')
    api_key = ai_config.get('api_key', '')
    
    # 提取 Embedding 配置
    qa_config = config.get('knowledge_qa', {})
    embedding_config = qa_config.get('embedding', {})
    
    # 合并配置（Embedding 配置可以覆盖 AI 配置）
    service_config = {
        'api_base': embedding_config.get('api_base') or api_base,
        'api_key': embedding_config.get('api_key') or api_key,
        'model': embedding_config.get('model', DEFAULT_EMBEDDING_MODEL),
        'timeout': ai_config.get('timeout', 60),
    }
    
    return EmbeddingService(service_config)
