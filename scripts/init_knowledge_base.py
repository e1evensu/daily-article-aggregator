#!/usr/bin/env python
"""
知识库初始化脚本

从 SQLite 数据库读取所有文章，批量添加到 ChromaDB 知识库。
用于首次初始化或重建知识库。

Usage:
    python scripts/init_knowledge_base.py [--rebuild] [--batch-size N]

Options:
    --rebuild       重建知识库（清空现有数据）
    --batch-size N  批量处理大小（默认 100）
    --limit N       限制处理文章数量（用于测试）

Requirements: 1.2, 1.3
"""

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
from src.qa.config import KnowledgeBaseConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def init_knowledge_base(
    rebuild: bool = False,
    batch_size: int = 100,
    limit: int | None = None
) -> dict:
    """
    初始化知识库
    
    Args:
        rebuild: 是否重建知识库（清空现有数据）
        batch_size: 批量处理大小
        limit: 限制处理文章数量
    
    Returns:
        初始化结果统计
    """
    logger.info("=" * 60)
    logger.info("知识库初始化脚本")
    logger.info("=" * 60)
    
    # 加载配置
    config = load_config()
    
    # 初始化知识库
    kb_config = KnowledgeBaseConfig.from_dict(
        config.get("knowledge_qa", {}).get("knowledge_base", {})
    )
    knowledge_base = KnowledgeBase(kb_config)
    
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
    
    # 批量处理文章
    processed = 0
    failed = 0
    
    for i in range(0, total_articles, batch_size):
        batch = articles[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total_articles + batch_size - 1) // batch_size
        
        logger.info(f"处理批次 {batch_num}/{total_batches} ({len(batch)} 篇文章)...")
        
        try:
            # 转换为知识库需要的格式
            article_dicts = []
            for article in batch:
                article_dict = {
                    "id": article.id,
                    "title": article.title,
                    "content": article.content or article.summary or "",
                    "url": article.url,
                    "source": article.source,
                    "source_type": article.source_type,
                    "category": getattr(article, "category", None),
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                    "fetched_at": article.fetched_at.isoformat() if article.fetched_at else None,
                }
                article_dicts.append(article_dict)
            
            # 添加到知识库
            knowledge_base.add_articles(article_dicts)
            processed += len(batch)
            
        except Exception as e:
            logger.error(f"批次 {batch_num} 处理失败: {e}")
            failed += len(batch)
    
    # 获取最终统计
    stats_after = knowledge_base.get_stats()
    documents_added = stats_after["total_documents"] - stats_before["total_documents"]
    
    logger.info("=" * 60)
    logger.info("初始化完成")
    logger.info(f"  总文章数: {total_articles}")
    logger.info(f"  成功处理: {processed}")
    logger.info(f"  处理失败: {failed}")
    logger.info(f"  新增文档: {documents_added}")
    logger.info(f"  知识库总文档: {stats_after['total_documents']}")
    logger.info("=" * 60)
    
    return {
        "total_articles": total_articles,
        "processed": processed,
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
    
    args = parser.parse_args()
    
    try:
        result = init_knowledge_base(
            rebuild=args.rebuild,
            batch_size=args.batch_size,
            limit=args.limit
        )
        
        if result["failed"] > 0:
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"初始化失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
