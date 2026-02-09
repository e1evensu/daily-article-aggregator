#!/usr/bin/env python3
"""测试 Atum 博客抓取器"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fetchers.web_blog_fetcher import AtumBlogFetcher

def main():
    print("测试 Atum 博客抓取器...")
    print("-" * 50)
    
    fetcher = AtumBlogFetcher({
        'enabled': True,
        'timeout': 30,
        'days_back': 365
    })
    
    result = fetcher.fetch()
    
    print(f"抓取到 {len(result.items)} 篇文章")
    
    if result.error:
        print(f"错误: {result.error}")
        return 1
    
    print("\n最新文章:")
    for i, article in enumerate(result.items[:5], 1):
        title = article.get('title', 'N/A')[:50]
        date = article.get('published_date', 'N/A')
        url = article.get('url', 'N/A')
        print(f"  {i}. [{date}] {title}")
        print(f"     URL: {url}")
    
    print("\n✓ 测试通过!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
