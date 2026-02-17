#!/usr/bin/env python
"""
知识库增量同步脚本

检测新文章并增量添加到 ChromaDB 知识库。
支持定时运行，只同步上次同步后的新文章。

Usage:
    python scripts/sync_knowledge_base.py [--hours N] [--batch-size N]

Options:
    --hours N       同步最近 N 小时的文章（默认 24）
    --batch-size N  批量处理大小（默认 50）
    --dry-run       只检查不实际同步

Requirements: 1.3
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import load_config
from src.repository import ArticleRepository
from src.qa.knowledge_base import KnowledgeBase
from src.qa.embedding_service import EmbeddingService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def sync_knowledge_base(
    hours: int = 24,
    batch_size: int = 50,
    dry_run: bool = False
) -> dict:
    """
    增量同步知识库
    
    Args:
        hours: 同步最近 N 小时的文章
        batch_size: 批量处理大小
        dry_run: 只检查不实际同步
    
    Returns:
        同步结果统计
    """
    logger.info("=" * 60)
    logger.info("知识库增量同步脚本")
    logger.info("=" * 60)
    
    # 加载配置
    config = load_config()
    
    # 初始化知识库
    kb_config = config.get("knowledge_qa", {}).get("chroma", {})
    knowledge_base = KnowledgeBase(kb_config)

    # 设置 embedding service
    embedding_config = config.get("knowledge_qa", {}).get("embedding", {})
    embedding_service = EmbeddingService(embedding_config)
    knowledge_base.set_embedding_service(embedding_service)
    
    # 获取当前知识库统计
    stats_before = knowledge_base.get_stats()
    logger.info(f"当前知识库状态: {stats_before['total_documents']} 个文档")
    
    # 初始化文章仓库
    db_path = config.get("database", {}).get("path", "data/articles.db")
    repository = ArticleRepository(db_path)
    
    # 计算时间范围
    since_time = datetime.now() - timedelta(hours=hours)
    logger.info(f"同步时间范围: {since_time.isoformat()} 至今")
    
    # 获取新文章
    logger.info("从数据库读取新文章...")
    articles = repository.get_articles_since(since_time)
    
    total_articles = len(articles)
    logger.info(f"发现 {total_articles} 篇新文章")
    
    if total_articles == 0:
        logger.info("没有新文章需要同步")
        return {
            "total_articles": 0,
            "processed": 0,
            "failed": 0,
            "documents_added": 0,
            "dry_run": dry_run
        }
    
    if dry_run:
        logger.info("[DRY RUN] 以下文章将被同步:")
        for article in articles[:10]:
            logger.info(f"  - {article.get('title', 'N/A')[:50]}...")
        if total_articles > 10:
            logger.info(f"  ... 还有 {total_articles - 10} 篇")
        return {
            "total_articles": total_articles,
            "processed": 0,
            "failed": 0,
            "documents_added": 0,
            "dry_run": True
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
                    "id": article.get('id'),
                    "title": article.get('title', ''),
                    "content": article.get('content') or article.get('summary') or "",
                    "url": article.get('url', ''),
                    "source": article.get('source', ''),
                    "source_type": article.get('source_type', ''),
                    "category": article.get('category'),
                    "published_date": article.get('published_at'),
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
    logger.info("同步完成")
    logger.info(f"  新文章数: {total_articles}")
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
        "total_documents": stats_after["total_documents"],
        "dry_run": False
    }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="增量同步知识库",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="同步最近 N 小时的文章（默认 24）"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="批量处理大小（默认 50）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检查不实际同步"
    )
    
    args = parser.parse_args()
    
    try:
        result = sync_knowledge_base(
            hours=args.hours,
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )
        
        if result["failed"] > 0:
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"同步失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
