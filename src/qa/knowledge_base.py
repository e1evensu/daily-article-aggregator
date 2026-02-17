"""
知识库管理模块

负责向量数据库的初始化、更新和查询。使用 ChromaDB 作为向量存储后端。

Requirements:
    - 1.2: 使用向量数据库存储嵌入（如 ChromaDB、Milvus 或 SQLite-VSS）
"""

import logging
import os
import sys
from typing import Any

# ChromaDB 需要 sqlite3 >= 3.35.0，某些系统版本过低
# 使用 pysqlite3 替换标准库的 sqlite3
try:
    import pysqlite3
    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass  # 如果没有安装 pysqlite3，使用系统自带的 sqlite3

import chromadb
from chromadb.config import Settings

from src.qa.config import QAConfig, ChunkingConfig, ChromaConfig
from src.qa.embedding_service import EmbeddingService
from src.qa.models import KnowledgeDocument, RetrievalResult

# 配置日志
logger = logging.getLogger(__name__)

# ChromaDB 集合配置
COLLECTION_METADATA = {
    "hnsw:space": "cosine",  # 使用余弦相似度
    "hnsw:M": 16,            # HNSW 参数
    "hnsw:construction_ef": 100
}


class KnowledgeBase:
    """
    知识库管理器，负责向量数据库的初始化、更新和查询
    
    使用 ChromaDB 作为向量存储后端，支持：
    - 文档分块和向量化存储
    - 语义搜索和过滤查询
    - 增量更新和知识库重建
    
    Attributes:
        chroma_client: ChromaDB 客户端实例
        collection: ChromaDB 集合
        embedding_service: 向量化服务
        chunk_size: 文档分块大小（字符）
        chunk_overlap: 分块重叠大小（字符）
    
    Requirements: 1.2
    """
    
    def __init__(
        self,
        config: dict[str, Any] | QAConfig,
        embedding_service: EmbeddingService | None = None
    ):
        """
        初始化知识库
        
        Args:
            config: 配置字典或 QAConfig 对象，包含：
                - chroma_path: ChromaDB 持久化路径
                - collection_name: 集合名称
                - chunk_size: 分块大小（可选，默认 500）
                - chunk_overlap: 分块重叠（可选，默认 50）
            embedding_service: 向量化服务实例（可选，用于依赖注入）
        
        Examples:
            >>> config = {
            ...     'chroma_path': 'data/chroma_db',
            ...     'collection_name': 'knowledge_articles',
            ...     'chunk_size': 500,
            ...     'chunk_overlap': 50
            ... }
            >>> kb = KnowledgeBase(config)
        
        Requirements: 1.2
        """
        # 解析配置
        if isinstance(config, QAConfig):
            self._chroma_config = config.chroma
            self._chunking_config = config.chunking
        else:
            self._chroma_config = ChromaConfig(
                path=config.get('chroma_path', 'data/chroma_db'),
                collection_name=config.get('collection_name', 'knowledge_articles')
            )
            self._chunking_config = ChunkingConfig(
                chunk_size=config.get('chunk_size', 500),
                chunk_overlap=config.get('chunk_overlap', 50)
            )
        
        # 分块配置
        self.chunk_size = self._chunking_config.chunk_size
        self.chunk_overlap = self._chunking_config.chunk_overlap
        
        # 验证分块配置
        if self.chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {self.chunk_size}")
        if self.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be non-negative, got {self.chunk_overlap}")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be less than "
                f"chunk_size ({self.chunk_size})"
            )
        
        # 初始化 ChromaDB
        self._init_chromadb()
        
        # 存储 embedding service（可选，用于 add_articles）
        self._embedding_service = embedding_service
        
        logger.info(
            f"KnowledgeBase initialized: path={self._chroma_config.path}, "
            f"collection={self._chroma_config.collection_name}, "
            f"chunk_size={self.chunk_size}, chunk_overlap={self.chunk_overlap}"
        )
    
    def _init_chromadb(self) -> None:
        """
        初始化 ChromaDB 客户端和集合
        
        创建持久化目录（如果不存在），初始化 ChromaDB 客户端，
        并获取或创建指定的集合。
        
        Raises:
            RuntimeError: ChromaDB 初始化失败
        
        Requirements: 1.2
        """
        try:
            # 确保持久化目录存在
            chroma_path = self._chroma_config.path
            if not os.path.exists(chroma_path):
                os.makedirs(chroma_path, exist_ok=True)
                logger.info(f"Created ChromaDB directory: {chroma_path}")
            
            # 初始化 ChromaDB 客户端（持久化模式）
            self.chroma_client = chromadb.PersistentClient(
                path=chroma_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # 获取或创建集合
            self.collection = self.chroma_client.get_or_create_collection(
                name=self._chroma_config.collection_name,
                metadata=COLLECTION_METADATA
            )
            
            logger.info(
                f"ChromaDB collection '{self._chroma_config.collection_name}' ready, "
                f"document count: {self.collection.count()}"
            )
            
        except Exception as e:
            error_msg = f"Failed to initialize ChromaDB: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def chunk_text(self, text: str) -> list[str]:
        """
        将文本分割成多个块
        
        使用滑动窗口方式分块，支持重叠以保持上下文连贯性。
        分块时尽量在句子边界处切分。
        
        Args:
            text: 待分块的文本
        
        Returns:
            文本块列表
        
        Examples:
            >>> kb = KnowledgeBase({'chunk_size': 100, 'chunk_overlap': 20})
            >>> chunks = kb.chunk_text("这是一段很长的文本..." * 10)
            >>> len(chunks) > 1
            True
            >>> all(len(c) <= 100 for c in chunks)  # 每块不超过 chunk_size
            True
        
        Requirements: 1.2
        """
        if not text or not text.strip():
            return []
        
        # 清理文本
        text = text.strip()
        
        # 如果文本长度小于等于 chunk_size，直接返回
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            # 计算当前块的结束位置
            end = min(start + self.chunk_size, text_length)
            
            # 如果不是最后一块，尝试在句子边界处切分
            if end < text_length:
                # 在 chunk_size 范围内寻找最后一个句子结束符
                best_break = self._find_sentence_boundary(text, start, end)
                if best_break > start:
                    end = best_break
            
            # 提取当前块
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # 计算下一块的起始位置（考虑重叠）
            if end >= text_length:
                break
            
            # 下一块从 (end - overlap) 开始，但不能小于当前 end
            # 这样可以确保有重叠，同时避免无限循环
            next_start = end - self.chunk_overlap
            if next_start <= start:
                # 如果重叠导致没有前进，强制前进
                next_start = end
            start = next_start
        
        return chunks
    
    def _find_sentence_boundary(self, text: str, start: int, end: int) -> int:
        """
        在指定范围内寻找最佳的句子边界
        
        优先在句号、问号、感叹号等处切分，其次在逗号、分号处切分。
        
        Args:
            text: 完整文本
            start: 搜索起始位置
            end: 搜索结束位置
        
        Returns:
            最佳切分位置，如果找不到则返回 end
        """
        # 句子结束符（优先级从高到低）
        sentence_endings = ['。', '！', '？', '.', '!', '?', '\n\n', '\n']
        clause_endings = ['；', '，', ';', ',', '：', ':']
        
        # 在后半部分搜索（避免切分太早）
        search_start = start + (end - start) // 2
        search_text = text[search_start:end]
        
        # 首先尝试找句子结束符
        best_pos = -1
        for ending in sentence_endings:
            pos = search_text.rfind(ending)
            if pos != -1:
                actual_pos = search_start + pos + len(ending)
                if actual_pos > best_pos:
                    best_pos = actual_pos
                break  # 找到最高优先级的就停止
        
        if best_pos > start:
            return best_pos
        
        # 如果没找到句子结束符，尝试找子句结束符
        for ending in clause_endings:
            pos = search_text.rfind(ending)
            if pos != -1:
                return search_start + pos + len(ending)
        
        # 如果都没找到，返回原始 end
        return end
    
    def set_embedding_service(self, embedding_service: EmbeddingService) -> None:
        """
        设置向量化服务
        
        Args:
            embedding_service: EmbeddingService 实例
        """
        self._embedding_service = embedding_service
        logger.info("Embedding service set for KnowledgeBase")
    
    @property
    def embedding_service(self) -> EmbeddingService | None:
        """获取向量化服务"""
        return self._embedding_service
    
    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """
        根据文档 ID 获取文档
        
        Args:
            doc_id: 文档 ID
        
        Returns:
            文档字典，包含 content 和 metadata，如果不存在则返回 None
        
        Requirements: 1.2
        """
        try:
            result = self.collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"]
            )
            
            if result and result['ids'] and len(result['ids']) > 0:
                return {
                    'doc_id': result['ids'][0],
                    'content': result['documents'][0] if result['documents'] else '',
                    'metadata': result['metadatas'][0] if result['metadatas'] else {}
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get document {doc_id}: {e}")
            return None
    
    def get_stats(self) -> dict[str, Any]:
        """
        获取知识库统计信息
        
        Returns:
            统计信息字典，包含：
                - total_documents: 文档总数
                - collection_name: 集合名称
                - chroma_path: 存储路径
        
        Requirements: 5.2
        """
        return {
            'total_documents': self.collection.count(),
            'collection_name': self._chroma_config.collection_name,
            'chroma_path': self._chroma_config.path,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap
        }
    
    def add_articles(self, articles: list[dict[str, Any]]) -> int:
        """
        添加文章到知识库
        
        将文章分块、向量化后存储到 ChromaDB。
        
        Args:
            articles: 文章列表，每篇文章包含：
                - id: 文章 ID
                - title: 标题
                - content: 内容
                - url: 原文链接
                - source_type: 来源类型
                - published_date: 发布日期（可选）
                - category: 分类（可选）
        
        Returns:
            成功添加的文档块数量
        
        Raises:
            RuntimeError: 未设置 embedding_service
        
        Requirements: 1.2, 1.3
        """
        if not self._embedding_service:
            raise RuntimeError(
                "Embedding service not set. Call set_embedding_service() first "
                "or pass embedding_service to constructor."
            )
        
        if not articles:
            return 0
        
        added_count = 0
        
        for article in articles:
            try:
                article_id = article.get('id')
                title = article.get('title', '')
                content = article.get('content', '')
                
                if not article_id or not content:
                    logger.warning(f"Skipping article with missing id or content")
                    continue
                
                # 组合标题和内容进行分块
                full_text = f"{title}\n\n{content}" if title else content
                chunks = self.chunk_text(full_text)
                
                if not chunks:
                    logger.warning(f"No chunks generated for article {article_id}")
                    continue
                
                # 批量向量化
                embeddings = self._embedding_service.embed_batch(chunks)
                
                # 准备文档数据
                doc_ids = []
                documents = []
                metadatas = []
                valid_embeddings = []
                
                for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                    if not embedding:  # 跳过空向量
                        continue
                    
                    doc_id = f"{article_id}_{i}"
                    doc_ids.append(doc_id)
                    documents.append(chunk)
                    valid_embeddings.append(embedding)
                    metadatas.append({
                        'article_id': int(article_id),
                        'title': title,
                        'url': article.get('url', ''),
                        'source_type': article.get('source_type', ''),
                        'published_date': article.get('published_date', ''),
                        'category': article.get('category', ''),
                        'chunk_index': i
                    })
                
                if doc_ids:
                    # 添加到 ChromaDB
                    self.collection.add(
                        ids=doc_ids,
                        documents=documents,
                        embeddings=valid_embeddings,
                        metadatas=metadatas
                    )
                    added_count += len(doc_ids)
                    logger.debug(
                        f"Added article {article_id} with {len(doc_ids)} chunks"
                    )
                
            except Exception as e:
                logger.error(f"Failed to add article {article.get('id')}: {e}")
                continue
        
        logger.info(f"Added {added_count} document chunks to knowledge base")
        return added_count
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        语义搜索
        
        Args:
            query: 查询文本
            n_results: 返回结果数量
            filters: 过滤条件（source_type, time_range 等）
        
        Returns:
            相关文档列表，每个文档包含 content, metadata, score
        
        Requirements: 3.2
        """
        if not self._embedding_service:
            raise RuntimeError(
                "Embedding service not set. Call set_embedding_service() first."
            )
        
        if not query or not query.strip():
            return []
        
        try:
            # 向量化查询
            query_embedding = self._embedding_service.embed_text(query)
            
            # 构建 ChromaDB where 过滤器
            where_filter = self._build_where_filter(filters) if filters else None
            
            # 执行搜索
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
            
            # 转换结果格式
            search_results = []
            if results and results['ids'] and results['ids'][0]:
                for i, doc_id in enumerate(results['ids'][0]):
                    # ChromaDB 返回的是距离，需要转换为相似度分数
                    # 对于余弦距离：similarity = 1 - distance
                    distance = results['distances'][0][i] if results['distances'] else 0
                    score = max(0, min(1, 1 - distance))  # 确保在 [0, 1] 范围内
                    
                    search_results.append({
                        'doc_id': doc_id,
                        'content': results['documents'][0][i] if results['documents'] else '',
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'score': score
                    })
            
            return search_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def _build_where_filter(
        self,
        filters: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        构建 ChromaDB where 过滤器
        
        Args:
            filters: 过滤条件字典
        
        Returns:
            ChromaDB where 过滤器，如果没有有效过滤条件则返回 None
        """
        conditions = []
        
        # source_type 过滤
        if 'source_type' in filters and filters['source_type']:
            source_type = filters['source_type']
            if isinstance(source_type, list):
                conditions.append({'source_type': {'$in': source_type}})
            else:
                conditions.append({'source_type': source_type})
        
        # category 过滤
        if 'category' in filters and filters['category']:
            category = filters['category']
            if isinstance(category, list):
                conditions.append({'category': {'$in': category}})
            else:
                conditions.append({'category': category})
        
        # 如果没有条件，返回 None
        if not conditions:
            return None
        
        # 如果只有一个条件，直接返回
        if len(conditions) == 1:
            return conditions[0]
        
        # 多个条件用 $and 组合
        return {'$and': conditions}
    
    def rebuild(self) -> int:
        """
        重建知识库
        
        删除现有集合并重新创建。
        
        Returns:
            重建后的文档数量（通常为 0，需要重新添加文档）
        
        Requirements: 5.1
        """
        try:
            # 删除现有集合
            self.chroma_client.delete_collection(
                name=self._chroma_config.collection_name
            )
            logger.info(
                f"Deleted collection '{self._chroma_config.collection_name}'"
            )
            
            # 重新创建集合
            self.collection = self.chroma_client.create_collection(
                name=self._chroma_config.collection_name,
                metadata=COLLECTION_METADATA
            )
            logger.info(
                f"Recreated collection '{self._chroma_config.collection_name}'"
            )
            
            return self.collection.count()
            
        except Exception as e:
            error_msg = f"Failed to rebuild knowledge base: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
