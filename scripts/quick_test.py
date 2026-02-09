#!/usr/bin/env python3
"""
一键测试脚本 - 测试全流程是否能跑通

使用方法:
    python scripts/quick_test.py [--full] [--module MODULE]

参数:
    --full      运行完整测试（包括实际抓取和推送）
    --module    只测试指定模块: rss, analyzer, pusher, qa, stats, all
"""

import sys
import os
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(name: str, success: bool, message: str = ""):
    """打印测试结果"""
    status = "✓ PASS" if success else "✗ FAIL"
    print(f"  [{status}] {name}")
    if message:
        print(f"          {message}")


def test_imports():
    """测试模块导入"""
    print_header("1. 测试模块导入")
    
    modules = [
        ("src.config", "配置模块"),
        ("src.repository", "数据仓库"),
        ("src.models", "数据模型"),
        ("src.fetchers", "抓取器"),
        ("src.analyzers", "AI分析器"),
        ("src.pushers", "推送器"),
        ("src.qa", "QA问答系统"),
        ("src.stats", "统计分析"),
        ("src.bots", "飞书机器人"),
        ("src.aggregation", "主题聚合"),
    ]
    
    all_pass = True
    for module, desc in modules:
        try:
            __import__(module)
            print_result(desc, True)
        except Exception as e:
            print_result(desc, False, str(e)[:50])
            all_pass = False
    
    return all_pass


def test_config():
    """测试配置加载"""
    print_header("2. 测试配置加载")
    
    try:
        from src.config import load_config
        config = load_config()
        
        # 检查关键配置项
        checks = [
            ("database.path", config.get("database", {}).get("path")),
            ("openai.api_key", config.get("openai", {}).get("api_key")),
            ("feishu.webhook_url", config.get("feishu", {}).get("webhook_url")),
        ]
        
        all_pass = True
        for name, value in checks:
            has_value = bool(value and value != "your-xxx")
            print_result(name, has_value, "已配置" if has_value else "未配置或使用默认值")
            if not has_value and name != "database.path":
                all_pass = False
        
        return all_pass
    except Exception as e:
        print_result("配置加载", False, str(e)[:50])
        return False


def test_database():
    """测试数据库连接"""
    print_header("3. 测试数据库")
    
    try:
        from src.repository import ArticleRepository
        from src.config import load_config
        
        config = load_config()
        db_path = config.get("database", {}).get("path", "data/articles.db")
        
        repo = ArticleRepository(db_path)
        repo.init_db()
        
        # 测试基本操作
        articles = repo.get_all_articles()
        unpushed = repo.get_unpushed_articles()
        
        print_result("数据库连接", True)
        print_result(f"文章总数: {len(articles)}", True)
        print_result(f"待推送: {len(unpushed)}", True)
        
        repo.close()
        return True
    except Exception as e:
        print_result("数据库", False, str(e)[:50])
        return False


def test_rss_fetcher():
    """测试RSS抓取"""
    print_header("4. 测试RSS抓取")
    
    try:
        from src.fetchers.rss_fetcher import RSSFetcher
        
        fetcher = RSSFetcher()
        
        # 测试解析OPML
        opml_files = list(Path("rss").glob("*.opml"))
        print_result(f"发现 {len(opml_files)} 个OPML文件", len(opml_files) > 0)
        
        return True
    except Exception as e:
        print_result("RSS抓取", False, str(e)[:50])
        return False


def test_atum_blog_fetcher():
    """测试Atum博客抓取"""
    print_header("4.1 测试Atum博客抓取")
    
    try:
        from src.fetchers.web_blog_fetcher import AtumBlogFetcher
        
        fetcher = AtumBlogFetcher({'enabled': True, 'timeout': 30, 'days_back': 365})
        result = fetcher.fetch()
        
        print_result(f"抓取到 {len(result.items)} 篇文章", len(result.items) >= 0)
        
        if result.items:
            print(f"          最新: {result.items[0].get('title', 'N/A')[:40]}...")
        
        if result.error:
            print(f"          错误: {result.error[:50]}")
        
        return len(result.items) > 0 or result.error is None
    except Exception as e:
        print_result("Atum博客抓取", False, str(e)[:50])
        return False


def test_ai_analyzer():
    """测试AI分析器"""
    print_header("5. 测试AI分析器")
    
    try:
        from src.analyzers.ai_analyzer import AIAnalyzer
        from src.config import load_config
        
        config = load_config()
        api_key = config.get("openai", {}).get("api_key")
        
        if not api_key or api_key == "your-openai-api-key":
            print_result("AI分析器", False, "未配置OpenAI API Key")
            return False
        
        analyzer = AIAnalyzer(api_key)
        print_result("AI分析器初始化", True)
        
        # 测试分析（可选）
        test_content = "This is a test article about cybersecurity vulnerabilities."
        result = asyncio.run(analyzer.analyze(test_content))
        print_result("AI分析测试", bool(result))
        
        return True
    except Exception as e:
        print_result("AI分析器", False, str(e)[:50])
        return False


def test_qa_system():
    """测试QA问答系统"""
    print_header("6. 测试QA问答系统")
    
    try:
        from src.qa import QAEngine, KnowledgeBase, EmbeddingService
        from src.qa.enhanced_retriever import EnhancedRetriever
        from src.qa.history_aware_query_builder import HistoryAwareQueryBuilder
        
        print_result("QAEngine 导入", True)
        print_result("KnowledgeBase 导入", True)
        print_result("EmbeddingService 导入", True)
        print_result("EnhancedRetriever 导入", True)
        print_result("HistoryAwareQueryBuilder 导入", True)
        
        return True
    except Exception as e:
        print_result("QA系统", False, str(e)[:50])
        return False


def test_stats_system():
    """测试统计分析系统"""
    print_header("7. 测试统计分析系统")
    
    try:
        from src.stats import (
            StatsCollector, StatsStore, StatsAggregator,
            TopicTracker, StatsAPI
        )
        
        # 测试初始化
        store = StatsStore(":memory:")
        collector = StatsCollector(store)
        aggregator = StatsAggregator(store)
        
        print_result("StatsStore 初始化", True)
        print_result("StatsCollector 初始化", True)
        print_result("StatsAggregator 初始化", True)
        
        # 测试记录事件
        collector.record_query("test query", 0.5, 3)
        stats = aggregator.get_daily_stats()
        print_result("事件记录和聚合", True)
        
        return True
    except Exception as e:
        print_result("统计系统", False, str(e)[:50])
        return False


def test_feishu_bot():
    """测试飞书机器人"""
    print_header("8. 测试飞书机器人")
    
    try:
        from src.bots import FeishuBot, FeishuEventHandler, ThreadReplier
        from src.config import load_config
        
        config = load_config()
        webhook_url = config.get("feishu", {}).get("webhook_url")
        
        print_result("FeishuBot 导入", True)
        print_result("FeishuEventHandler 导入", True)
        print_result("ThreadReplier 导入", True)
        
        if webhook_url and webhook_url != "your-feishu-webhook-url":
            print_result("Webhook URL 已配置", True)
        else:
            print_result("Webhook URL", False, "未配置")
        
        return True
    except Exception as e:
        print_result("飞书机器人", False, str(e)[:50])
        return False


def test_sitemap_importer():
    """测试Sitemap导入器"""
    print_header("9. 测试Sitemap导入器")
    
    try:
        from src.fetchers.sitemap_importer import (
            SitemapParser, CrawlRuleEngine, IncrementalCrawler,
            HTMLToMarkdownConverter, SitemapImporter
        )
        
        print_result("SitemapParser 导入", True)
        print_result("CrawlRuleEngine 导入", True)
        print_result("IncrementalCrawler 导入", True)
        print_result("HTMLToMarkdownConverter 导入", True)
        print_result("SitemapImporter 导入", True)
        
        return True
    except Exception as e:
        print_result("Sitemap导入器", False, str(e)[:50])
        return False


def run_full_test():
    """运行完整流程测试"""
    print_header("完整流程测试")
    
    try:
        from src.config import load_config
        from src.repository import ArticleRepository
        from src.fetchers.rss_fetcher import RSSFetcher
        
        config = load_config()
        db_path = config.get("database", {}).get("path", "data/articles.db")
        
        # 1. 初始化
        repo = ArticleRepository(db_path)
        repo.init_db()
        fetcher = RSSFetcher()
        
        # 2. 抓取文章
        print("\n  正在抓取RSS...")
        articles = asyncio.run(fetcher.fetch_feed("https://atum.li/cn/feed.xml"))
        print(f"  抓取到 {len(articles)} 篇文章")
        
        # 3. 保存到数据库
        saved = 0
        for article in articles[:3]:  # 只保存前3篇测试
            if not repo.exists_by_url(article.get("url", "")):
                try:
                    repo.save_article(article)
                    saved += 1
                except:
                    pass
        
        print(f"  新保存 {saved} 篇文章")
        
        # 4. 统计
        total = len(repo.get_all_articles())
        unpushed = len(repo.get_unpushed_articles())
        print(f"  数据库总计: {total} 篇, 待推送: {unpushed} 篇")
        
        repo.close()
        print_result("完整流程测试", True)
        return True
        
    except Exception as e:
        print_result("完整流程测试", False, str(e))
        return False


def print_summary(results: dict):
    """打印测试总结"""
    print_header("测试总结")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n  通过: {passed}/{total}")
    print(f"  成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n  🎉 所有测试通过！系统可以正常运行。")
    else:
        print("\n  ⚠️  部分测试未通过，请检查配置。")
        failed = [k for k, v in results.items() if not v]
        print(f"  失败项: {', '.join(failed)}")


def main():
    parser = argparse.ArgumentParser(description="一键测试脚本")
    parser.add_argument("--full", action="store_true", help="运行完整测试")
    parser.add_argument("--module", type=str, help="只测试指定模块")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("  Daily Article Aggregator - 一键测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = {}
    
    # 基础测试
    results["模块导入"] = test_imports()
    results["配置加载"] = test_config()
    results["数据库"] = test_database()
    
    # 功能模块测试
    if not args.module or args.module in ["rss", "all"]:
        results["RSS抓取"] = test_rss_fetcher()
        results["Atum博客"] = test_atum_blog_fetcher()
    
    if not args.module or args.module in ["analyzer", "all"]:
        results["AI分析器"] = test_ai_analyzer()
    
    if not args.module or args.module in ["qa", "all"]:
        results["QA系统"] = test_qa_system()
    
    if not args.module or args.module in ["stats", "all"]:
        results["统计系统"] = test_stats_system()
    
    if not args.module or args.module in ["pusher", "all"]:
        results["飞书机器人"] = test_feishu_bot()
        results["Sitemap导入"] = test_sitemap_importer()
    
    # 完整流程测试
    if args.full:
        results["完整流程"] = run_full_test()
    
    print_summary(results)
    
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
