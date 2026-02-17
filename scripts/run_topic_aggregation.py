#!/usr/bin/env python3
"""
话题聚合系统运行脚本

支持独立运行模式和作为调度器任务运行。

Usage:
    # 独立运行（从数据库获取文章）
    python scripts/run_topic_aggregation.py
    
    # 指定天数范围
    python scripts/run_topic_aggregation.py --days 7
    
    # 不发布到飞书
    python scripts/run_topic_aggregation.py --no-publish
    
    # 不生成 RSS
    python scripts/run_topic_aggregation.py --no-rss
    
    # 查看统计信息
    python scripts/run_topic_aggregation.py --stats
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import load_config
from src.repository import ArticleRepository
from src.models import Article
from src.aggregation import TopicAggregationSystem

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_articles_from_db(
    db_path: str, 
    days: int = 7
) -> list[Article]:
    """
    从数据库加载文章
    
    Args:
        db_path: 数据库路径
        days: 加载最近多少天的文章
    
    Returns:
        文章列表
    """
    import os
    if not os.path.exists(db_path):
        logger.warning(f"数据库文件不存在: {db_path}")
        return []
    
    repo = ArticleRepository(db_path)
    
    # 计算时间范围
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # 获取所有文章（使用 SQL 查询）
    try:
        conn = repo._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles ORDER BY fetched_at DESC")
        rows = cursor.fetchall()
    except Exception as e:
        logger.warning(f"查询数据库失败: {e}")
        repo.close()
        return []
    
    # 过滤时间范围内的文章
    articles = []
    for row in rows:
        try:
            article_dict = repo._row_to_dict(row)
            
            # 解析日期
            fetched_at = article_dict.get('fetched_at', '')
            if fetched_at:
                if isinstance(fetched_at, str):
                    try:
                        article_date = datetime.fromisoformat(fetched_at.replace('Z', '+00:00'))
                    except ValueError:
                        # 尝试其他格式
                        article_date = datetime.now()
                else:
                    article_date = fetched_at
                
                # 移除时区信息进行比较
                if hasattr(article_date, 'replace'):
                    article_date = article_date.replace(tzinfo=None)
                
                if article_date < cutoff_date:
                    continue
            
            # 转换为 Article 对象
            article = Article(
                title=article_dict.get('title', ''),
                url=article_dict.get('url', ''),
                source=article_dict.get('source', ''),
                source_type=article_dict.get('source_type', ''),
                summary=article_dict.get('summary', ''),
                zh_summary=article_dict.get('zh_summary', ''),
                content=article_dict.get('content', ''),
                published_date=article_dict.get('published_date', ''),
                category=article_dict.get('category', ''),
            )

            # 跳过已分析的文章（有摘要或中文摘要）
            if article.summary or article.zh_summary:
                continue

            articles.append(article)
        except Exception as e:
            logger.warning(f"解析文章失败: {e}")
            continue
    
    repo.close()
    return articles


def main():
    parser = argparse.ArgumentParser(
        description='话题聚合系统运行脚本'
    )
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='配置文件路径 (默认: config.yaml)'
    )
    parser.add_argument(
        '--days', '-d',
        type=int,
        default=7,
        help='处理最近多少天的文章 (默认: 7)'
    )
    parser.add_argument(
        '--no-publish',
        action='store_true',
        help='不发布到飞书文档'
    )
    parser.add_argument(
        '--no-rss',
        action='store_true',
        help='不生成 RSS'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='只显示统计信息'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='显示详细日志'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 加载配置
    logger.info(f"加载配置: {args.config}")
    config = load_config(args.config)
    
    # 获取话题聚合配置
    topic_config = config.get('topic_aggregation', {})
    
    # 检查是否启用
    if not topic_config.get('enabled', False):
        logger.warning("话题聚合功能未启用，请在 config.yaml 中设置 topic_aggregation.enabled: true")
        return
    
    # 构建系统配置
    system_config = {
        'quality_filter': {
            'blacklist_domains': topic_config.get('blacklist_domains', []),
            'trusted_sources': topic_config.get('trusted_sources', []),
        },
        'aggregation_engine': {
            'similarity_threshold': topic_config.get('similarity_threshold', 0.7),
            'aggregation_threshold': topic_config.get('aggregation_threshold', 3),
            'time_window_days': topic_config.get('time_window_days', 7),
            'title_weight': topic_config.get('title_weight', 0.6),
            'keyword_weight': topic_config.get('keyword_weight', 0.4),
            'use_ai_similarity': topic_config.get('use_ai_similarity', True),
        },
        'synthesis_generator': {},
        'doc_publisher': {
            'app_id': config.get('feishu_bitable', {}).get('app_id', ''),
            'app_secret': config.get('feishu_bitable', {}).get('app_secret', ''),
            'folder_token': topic_config.get('feishu_doc_folder_token', ''),
            'backup_dir': 'data/doc_backups',
        },
        'rss_generator': {
            'output_path': topic_config.get('rss_output_path', 'data/knowledge_feed.xml'),
            'max_items': 100,
        },
        'ai': config.get('ai', {}),
    }
    
    # 初始化系统
    logger.info("初始化话题聚合系统")
    system = TopicAggregationSystem(system_config)
    
    # 只显示统计信息
    if args.stats:
        stats = system.get_stats()
        print("\n=== 话题聚合系统统计 ===")
        print(f"RSS 条目数: {stats['rss_items_count']}")
        print(f"黑名单域名: {len(stats['blacklist_domains'])} 个")
        print(f"可信来源: {len(stats['trusted_sources'])} 个")
        print(f"相似度阈值: {stats['similarity_threshold']}")
        print(f"聚合阈值: {stats['aggregation_threshold']}")
        return
    
    # 从数据库加载文章
    db_path = config.get('database', {}).get('path', 'data/articles.db')
    logger.info(f"从数据库加载文章: {db_path} (最近 {args.days} 天)")
    
    articles = load_articles_from_db(db_path, args.days)
    logger.info(f"加载了 {len(articles)} 篇文章")
    
    if not articles:
        logger.warning("没有找到文章")
        return
    
    # 运行话题聚合
    logger.info("开始话题聚合处理")
    result = system.run(
        articles,
        publish_to_feishu=not args.no_publish,
        generate_rss=not args.no_rss
    )
    
    # 输出结果
    print("\n=== 处理结果 ===")
    print(f"总文章数: {result['stats']['total_articles']}")
    print(f"过滤文章: {result['stats']['filtered_articles']}")
    print(f"通过文章: {result['stats']['passed_articles']}")
    print(f"话题聚类: {result['stats']['clusters_count']}")
    print(f"待整合聚类: {result['stats']['pending_clusters_count']}")
    print(f"生成综述: {result['stats']['syntheses_count']}")
    print(f"发布成功: {result['stats']['published_count']}")
    
    if result['rss_path']:
        print(f"RSS 文件: {result['rss_path']}")


if __name__ == '__main__':
    main()
