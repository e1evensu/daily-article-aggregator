#!/usr/bin/env python3
"""
调试推送问题的脚本
Debug script for push issues

检查：
1. 数据库中文章是否有 zh_summary
2. 分级推送是否正常工作
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.repository import ArticleRepository

def main():
    # 加载配置
    config = load_config("config.yaml")
    
    # 连接数据库
    db_path = config.get('database', {}).get('path', 'data/articles.db')
    repo = ArticleRepository(db_path)
    
    # 获取未推送文章
    unpushed = repo.get_unpushed_articles()
    print(f"\n=== 未推送文章: {len(unpushed)} 篇 ===\n")
    
    # 统计有无 zh_summary 的文章
    with_summary = 0
    without_summary = 0
    
    for i, article in enumerate(unpushed[:20], 1):  # 只显示前20篇
        title = article.get('title', '')[:60]
        source_type = article.get('source_type', '')
        zh_summary = article.get('zh_summary', '')
        summary = article.get('summary', '')
        content = article.get('content', '')
        
        has_zh = bool(zh_summary)
        has_summary = bool(summary)
        has_content = bool(content)
        
        if has_zh:
            with_summary += 1
        else:
            without_summary += 1
        
        print(f"{i}. [{source_type}] {title}")
        print(f"   zh_summary: {'✓' if has_zh else '✗'} ({len(zh_summary)} chars)")
        print(f"   summary: {'✓' if has_summary else '✗'} ({len(summary)} chars)")
        print(f"   content: {'✓' if has_content else '✗'} ({len(content)} chars)")
        if zh_summary:
            print(f"   摘要预览: {zh_summary[:100]}...")
        print()
    
    print(f"\n=== 统计 ===")
    print(f"有 zh_summary: {with_summary} 篇")
    print(f"无 zh_summary: {without_summary} 篇")
    
    repo.close()

if __name__ == "__main__":
    main()
