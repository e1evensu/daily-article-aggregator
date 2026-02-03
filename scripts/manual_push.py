#!/usr/bin/env python3
"""
手动推送文章到飞书

支持：
1. 查看数据库中的文章状态
2. 重置文章推送状态
3. 手动触发推送

Usage:
    python scripts/manual_push.py --status           # 查看状态
    python scripts/manual_push.py --reset 100        # 重置最近100篇为未推送
    python scripts/manual_push.py --push             # 推送未推送的文章
    python scripts/manual_push.py --push --limit 20  # 只推送20篇
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import load_config
from src.bots.feishu_bot import FeishuBot
from src.repository import ArticleRepository

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def show_status(db_path: str):
    """显示数据库状态"""
    repo = ArticleRepository(db_path)
    
    conn = repo._get_connection()
    cursor = conn.cursor()
    
    # 总文章数
    cursor.execute("SELECT COUNT(*) as total FROM articles")
    total = cursor.fetchone()['total']
    
    # 已推送数
    cursor.execute("SELECT COUNT(*) as pushed FROM articles WHERE is_pushed = 1")
    pushed = cursor.fetchone()['pushed']
    
    # 未推送数
    cursor.execute("SELECT COUNT(*) as unpushed FROM articles WHERE is_pushed = 0")
    unpushed = cursor.fetchone()['unpushed']
    
    print("\n" + "=" * 50)
    print("数据库状态")
    print("=" * 50)
    print(f"总文章数: {total}")
    print(f"已推送: {pushed}")
    print(f"未推送: {unpushed}")
    
    # 最近的文章
    cursor.execute("""
        SELECT title, source, is_pushed, fetched_at 
        FROM articles 
        ORDER BY fetched_at DESC 
        LIMIT 5
    """)
    rows = cursor.fetchall()
    
    if rows:
        print("\n最近5篇文章:")
        for row in rows:
            status = "✅" if row['is_pushed'] else "⏳"
            title = row['title'][:40] + "..." if len(row['title']) > 40 else row['title']
            print(f"  {status} {title}")
            print(f"     来源: {row['source']}, 时间: {row['fetched_at']}")
    
    repo.close()


def reset_push_status(db_path: str, count: int):
    """重置文章推送状态"""
    repo = ArticleRepository(db_path)
    
    conn = repo._get_connection()
    cursor = conn.cursor()
    
    # 获取最近的文章 ID
    cursor.execute(f"""
        SELECT id FROM articles 
        ORDER BY fetched_at DESC 
        LIMIT {count}
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("没有找到文章")
        repo.close()
        return
    
    ids = [row['id'] for row in rows]
    placeholders = ','.join('?' * len(ids))
    
    # 重置推送状态
    cursor.execute(f"""
        UPDATE articles 
        SET is_pushed = 0, pushed_at = NULL 
        WHERE id IN ({placeholders})
    """, ids)
    
    conn.commit()
    
    print(f"已重置 {len(ids)} 篇文章的推送状态")
    repo.close()


def manual_push(config: dict, db_path: str, limit: int = None, batch_size: int = 10):
    """手动推送文章"""
    # 获取 Webhook URL
    feishu_config = config.get('feishu', {})
    webhook_url = feishu_config.get('webhook_url', '')
    
    if not webhook_url:
        logger.error("未配置飞书 Webhook URL")
        return False
    
    # 获取未推送文章
    repo = ArticleRepository(db_path)
    unpushed = repo.get_unpushed_articles()
    
    if not unpushed:
        print("没有未推送的文章")
        repo.close()
        return True
    
    # 限制数量
    if limit:
        unpushed = unpushed[:limit]
    
    print(f"\n准备推送 {len(unpushed)} 篇文章")
    
    # 创建机器人并推送
    bot = FeishuBot(webhook_url)
    success = bot.push_articles(unpushed, batch_size=batch_size)
    
    if success:
        # 标记为已推送
        article_ids = [a['id'] for a in unpushed if a.get('id')]
        repo.mark_as_pushed(article_ids)
        print(f"✅ 成功推送并标记 {len(article_ids)} 篇文章")
    else:
        print("❌ 推送失败")
    
    repo.close()
    return success


def main():
    parser = argparse.ArgumentParser(description='手动推送文章到飞书')
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='配置文件路径 (默认: config.yaml)'
    )
    parser.add_argument(
        '--status', '-s',
        action='store_true',
        help='显示数据库状态'
    )
    parser.add_argument(
        '--reset', '-r',
        type=int,
        metavar='COUNT',
        help='重置最近 COUNT 篇文章为未推送状态'
    )
    parser.add_argument(
        '--push', '-p',
        action='store_true',
        help='推送未推送的文章'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        help='限制推送的文章数量'
    )
    parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=10,
        help='每批推送的文章数量 (默认: 10)'
    )
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config(args.config)
    
    # 数据库路径
    db_config = config.get('database', {})
    db_path = db_config.get('path', 'data/articles.db')
    
    if not Path(db_path).exists():
        logger.error(f"数据库文件不存在: {db_path}")
        return
    
    # 执行操作
    if args.status:
        show_status(db_path)
    
    if args.reset:
        reset_push_status(db_path, args.reset)
    
    if args.push:
        manual_push(config, db_path, args.limit, args.batch_size)
    
    # 如果没有指定任何操作，显示帮助
    if not (args.status or args.reset or args.push):
        parser.print_help()


if __name__ == '__main__':
    main()
