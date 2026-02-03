#!/usr/bin/env python3
"""
数据库统计脚本
Database Statistics Script

查看数据库中文章的分布情况
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.repository import ArticleRepository


def main():
    config = load_config("config.yaml")
    db_path = config.get('database', {}).get('path', 'data/articles.db')
    repo = ArticleRepository(db_path)
    
    conn = repo._get_connection()
    cursor = conn.cursor()
    
    # 总数
    cursor.execute("SELECT COUNT(*) as total FROM articles")
    total = cursor.fetchone()['total']
    print(f"\n=== 数据库统计 ===")
    print(f"总文章数: {total}")
    
    # 按来源类型统计
    print(f"\n--- 按来源类型 ---")
    cursor.execute("""
        SELECT source_type, COUNT(*) as count, 
               SUM(CASE WHEN is_pushed = 1 THEN 1 ELSE 0 END) as pushed,
               SUM(CASE WHEN is_pushed = 0 THEN 1 ELSE 0 END) as unpushed,
               SUM(CASE WHEN zh_summary IS NOT NULL AND zh_summary != '' THEN 1 ELSE 0 END) as has_summary
        FROM articles 
        GROUP BY source_type 
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row['source_type']}: {row['count']} 篇 (已推送: {row['pushed']}, 未推送: {row['unpushed']}, 有摘要: {row['has_summary']})")
    
    # 按来源统计（前20）
    print(f"\n--- 按来源（前20）---")
    cursor.execute("""
        SELECT source, COUNT(*) as count 
        FROM articles 
        GROUP BY source 
        ORDER BY count DESC 
        LIMIT 20
    """)
    for row in cursor.fetchall():
        print(f"  {row['source'][:40]}: {row['count']} 篇")
    
    # 有 zh_summary 的文章
    cursor.execute("SELECT COUNT(*) as count FROM articles WHERE zh_summary IS NOT NULL AND zh_summary != ''")
    with_summary = cursor.fetchone()['count']
    print(f"\n--- 摘要统计 ---")
    print(f"有 zh_summary: {with_summary} 篇 ({with_summary*100/total:.1f}%)")
    print(f"无 zh_summary: {total - with_summary} 篇")
    
    # 未推送文章
    cursor.execute("SELECT COUNT(*) as count FROM articles WHERE is_pushed = 0")
    unpushed = cursor.fetchone()['count']
    print(f"\n--- 推送状态 ---")
    print(f"已推送: {total - unpushed} 篇")
    print(f"未推送: {unpushed} 篇")
    
    # 查看一些有摘要的 RSS 文章示例
    print(f"\n--- 有摘要的 RSS 文章示例 ---")
    cursor.execute("""
        SELECT title, source, zh_summary 
        FROM articles 
        WHERE source_type = 'rss' AND zh_summary IS NOT NULL AND zh_summary != ''
        ORDER BY fetched_at DESC
        LIMIT 5
    """)
    for i, row in enumerate(cursor.fetchall(), 1):
        print(f"{i}. {row['title'][:50]}...")
        print(f"   来源: {row['source'][:30]}")
        print(f"   摘要: {row['zh_summary'][:80]}...")
        print()
    
    repo.close()


if __name__ == "__main__":
    main()
