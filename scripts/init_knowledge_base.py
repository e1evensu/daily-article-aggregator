#!/usr/bin/env python
"""
知识库初始化脚本

从 SQLite 数据库读取所有文章，批量添加到 ChromaDB 知识库。
用于首次初始化或重建知识库。
支持断点续传（自动跳过已处理的文章）和内存优化。

Usage:
    python scripts/init_knowledge_base.py [--rebuild] [--batch-size N] [--no-resume]

Options:
    --rebuild       重建知识库（清空现有数据）
    --batch-size N  批量处理大小（默认 100）
    --limit N       限制处理文章数量（用于测试）
    --no-resume     禁用断点续传，从头开始处理所有文章

Requirements: 1.2, 1.3
"""

# SQLite 版本兼容性补丁 - ChromaDB 需要 SQLite >= 3.35.0
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import load_config
from src.repository import ArticleRepository
from src.qa.knowledge_base import KnowledgeBase
from src.qa.config import QAConfig
from src.qa.embedding_service import EmbeddingService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def init_knowledge_base(
    rebuild: bool = False,
    batch_size: int = 100,
    limit: int | None = None,
    resume: bool = True
) -> dict:
    """
    初始化知识库

    Args:
        rebuild: 是否重建知识库（清空现有数据）
        batch_size: 批量处理大小
        limit: 限制处理文章数量
        resume: 是否启用断点续传（默认 True）

    Returns:
        初始化结果统计
    """
    logger.info("=" * 60)
    logger.info("知识库初始化脚本")
    logger.info("=" * 60)
    
    # 加载配置
    config = load_config()
    
    # 初始化知识库配置
    qa_config = QAConfig.from_dict(config.get("knowledge_qa", {}))
    knowledge_base = KnowledgeBase(qa_config)
    
    # 初始化 Embedding 服务（需要传字典，并补充 AI 配置中的 api_base 和 api_key）
    ai_config = config.get("ai", {})
    embedding_dict = qa_config.embedding.to_dict()
    embedding_dict.setdefault('api_base', ai_config.get('api_base', 'https://api.openai.com/v1'))
    embedding_dict.setdefault('api_key', ai_config.get('api_key', ''))
    embedding_service = EmbeddingService(embedding_dict)
    knowledge_base.set_embedding_service(embedding_service)
    
    # 如果需要重建，先清空
    if rebuild:
        logger.info("重建模式：清空现有知识库...")
        knowledge_base.rebuild()
        logger.info("知识库已清空")
    
    # 获取当前知识库统计
    stats_before = knowledge_base.get_stats()
    logger.info(f"当前知识库状态: {stats_before['total_documents']} 个文档")

    # 初始化文章仓库
    db_path = config.get("database", {}).get("path", "data/articles.db")
    repository = ArticleRepository(db_path)

    # 获取所有文章
    logger.info("从数据库读取文章...")
    articles = repository.get_all_articles()

    if limit:
        articles = articles[:limit]
        logger.info(f"限制处理 {limit} 篇文章")

    total_articles = len(articles)
    logger.info(f"共 {total_articles} 篇文章待处理")

    if total_articles == 0:
        logger.warning("没有文章需要处理")
        return {
            "total_articles": 0,
            "processed": 0,
            "failed": 0,
            "documents_added": 0
        }

    # 获取已处理的文章 ID（用于断点续传）
    # 注意：不能一次性获取所有文档，会 OOM。使用分批查询
    processed_article_ids: set = set()
    if resume and not rebuild:
        logger.info("检查已有知识库，收集已处理的文章 ID...")
        total_docs = knowledge_base.collection.count()
        if total_docs > 0:
            batch_size = 500
            offset = 0
            logger.info(f"共有 {total_docs} 个文档，分批获取 article_id...")

            while offset < total_docs:
                # 只获取 IDs 和 metadata，分批查询
                result = knowledge_base.collection.get(
                    include=["metadatas"],
                    limit=batch_size,
                    offset=offset
                )

                if result and result["metadatas"]:
                    for meta in result["metadatas"]:
                        if "article_id" in meta:
                            processed_article_ids.add(int(meta["article_id"]))

                offset += batch_size

                # 每处理 10000 条输出一次日志
                if offset % 10000 == 0 or offset >= total_docs:
                    logger.info(f"已处理 {offset}/{total_docs} 个文档...")

                # 定期清理内存
                if offset % 20000 == 0:
                    import gc
                    gc.collect()

            del result
            import gc
            gc.collect()

        logger.info(f"发现 {len(processed_article_ids)} 篇已处理的文章，将跳过这些文章")

    # 批量处理文章（逐篇处理以便更好地跟踪进度和错误）
    processed = 0
    failed = 0
    skipped_already_processed = 0
    skipped_no_content = 0
    memory_cleanup_interval = 50  # 每处理 50 篇文章清理一次内存
    chroma_reset_interval = 200   # 每处理 200 篇文章重置一次 ChromaDB 客户端

    for i, article in enumerate(articles):
        article_id = article["id"]
        title = article["title"][:50] + "..." if len(article["title"]) > 50 else article["title"]

        # 断点续传：跳过已处理的文章
        if resume and article_id in processed_article_ids:
            skipped_already_processed += 1
            # 进度显示时也更新计数
            if (i + 1) % 10 == 0:
                logger.info(f"处理进度: {i + 1}/{total_articles} ({(i + 1) * 100 // total_articles}%) - 已跳过 {skipped_already_processed} 篇已处理文章")
            continue

        # 进度显示
        if (i + 1) % 10 == 0 or i == 0:
            logger.info(f"处理进度: {i + 1}/{total_articles} ({(i + 1) * 100 // total_articles}%)")

        try:
            content = article.get("content") or article.get("summary") or ""
            if not content.strip():
                logger.debug(f"跳过无内容文章 {article_id}: {title}")
                skipped_no_content += 1
                continue

            # 转换为知识库需要的格式
            article_dict = {
                "id": article_id,
                "title": article["title"],
                "content": content,
                "url": article["url"],
                "source": article.get("source", ""),
                "source_type": article.get("source_type", ""),
                "category": article.get("category"),
                "published_date": article.get("published_date", ""),
            }

            # 添加到知识库
            knowledge_base.add_articles([article_dict])
            processed += 1

            # 定期内存清理（避免 OOM）
            if processed > 0 and processed % memory_cleanup_interval == 0:
                import gc
                gc.collect()
                logger.debug(f"已处理 {processed} 篇文章，触发内存清理")

            # 定期重置 ChromaDB 客户端，释放内存
            if processed > 0 and processed % chroma_reset_interval == 0:
                knowledge_base.reset_client()
                logger.info(f"已处理 {processed} 篇文章，重置 ChromaDB 客户端释放内存")

        except Exception as e:
            logger.warning(f"文章 {article_id} 处理失败: {e}")
            failed += 1
            # 继续处理下一篇，不中断整个流程
    
    # 获取最终统计
    stats_after = knowledge_base.get_stats()
    documents_added = stats_after["total_documents"] - stats_before["total_documents"]
    
    logger.info("=" * 60)
    logger.info("初始化完成")
    logger.info(f"  总文章数: {total_articles}")
    logger.info(f"  成功处理: {processed}")
    logger.info(f"  跳过(已存在): {skipped_already_processed}")
    logger.info(f"  跳过(无内容): {skipped_no_content}")
    logger.info(f"  处理失败: {failed}")
    logger.info(f"  新增文档: {documents_added}")
    logger.info(f"  知识库总文档: {stats_after['total_documents']}")
    logger.info("=" * 60)
    
    return {
        "total_articles": total_articles,
        "processed": processed,
        "skipped_already_processed": skipped_already_processed,
        "skipped_no_content": skipped_no_content,
        "failed": failed,
        "documents_added": documents_added,
        "total_documents": stats_after["total_documents"]
    }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="初始化知识库",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="重建知识库（清空现有数据）"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="批量处理大小（默认 100）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制处理文章数量（用于测试）"
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="禁用断点续传，从头开始处理所有文章"
    )

    args = parser.parse_args()

    try:
        result = init_knowledge_base(
            rebuild=args.rebuild,
            batch_size=args.batch_size,
            limit=args.limit,
            resume=not args.no_resume
        )
        
        if result["failed"] > 0:
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"初始化失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
