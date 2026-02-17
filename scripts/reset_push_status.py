#!/usr/bin/env python3
"""
重置推送状态脚本
Reset Push Status Script

可以选择性地重置文章的推送状态，让它们可以重新被推送。
支持按来源类型、时间范围等条件筛选。
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.repository import ArticleRepository


def main():
    parser = argparse.ArgumentParser(description='重置文章推送状态')
    parser.add_argument('--source-type', '-s', help='只重置指定来源类型 (rss, arxiv, kev, nvd, dblp, etc.)')
    parser.add_argument('--exclude-nvd', action='store_true', help='排除 NVD 文章')
    parser.add_argument('--has-summary', action='store_true', help='只重置有 zh_summary 的文章')
    parser.add_argument('--days', '-d', type=int, default=7, help='只重置最近 N 天的文章 (默认: 7)')
    parser.add_argument('--dry-run', action='store_true', help='只显示会影响的文章数，不实际执行')
    parser.add_argument('--all', action='store_true', help='重置所有文章（危险！）')
    args = parser.parse_args()
    
    config = load_config("config.yaml")
    db_path = config.get('database', {}).get('path', 'data/articles.db')
    repo = ArticleRepository(db_path)
    
    conn = repo._get_connection()
    cursor = conn.cursor()
    
    # 构建查询条件
    conditions = ["is_pushed = 1"]  # 只重置已推送的
    params = []
    
    if not args.all:
        conditions.append(f"fetched_at >= datetime('now', '-{args.days} days')")
    
    if args.source_type:
        conditions.append("source_type = ?")
        params.append(args.source_type)
    
    if args.exclude_nvd:
        conditions.append("source_type != 'nvd'")
    
    if args.has_summary:
        conditions.append("zh_summary IS NOT NULL AND zh_summary != ''")
    
    where_clause = " AND ".join(conditions)
    
    # 查询会影响的文章数
    count_sql = f"SELECT COUNT(*) as count FROM articles WHERE {where_clause}"
    cursor.execute(count_sql, params)
    count = cursor.fetchone()['count']
    
    print(f"\n=== 重置推送状态 ===")
    print(f"条件: {where_clause}")
    print(f"将影响: {count} 篇文章")
    
    if args.dry_run:
        print("\n[DRY RUN] 未实际执行")
        
        # 显示一些示例
        sample_sql = f"""
            SELECT title, source_type, source 
            FROM articles 
            WHERE {where_clause}
            ORDER BY fetched_at DESC
            LIMIT 10
        """
        cursor.execute(sample_sql, params)
        print("\n示例文章:")
        for row in cursor.fetchall():
            print(f"  [{row['source_type']}] {row['title'][:50]}...")
    else:
        if count == 0:
            print("没有需要重置的文章")
        else:
            confirm = input(f"\n确认重置 {count} 篇文章的推送状态? (y/N): ")
            if confirm.lower() == 'y':
                update_sql = f"UPDATE articles SET is_pushed = 0, pushed_at = NULL WHERE {where_clause}"
                cursor.execute(update_sql, params)
                conn.commit()
                print(f"✓ 已重置 {count} 篇文章的推送状态")
            else:
                print("已取消")
    
    repo.close()


if __name__ == "__main__":
    main()
