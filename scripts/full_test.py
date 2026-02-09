#!/usr/bin/env python3
"""
完整功能测试脚本 - 测试所有核心功能

使用方法:
    python scripts/full_test.py

测试内容:
    1. 模块导入
    2. 配置加载
    3. 数据库操作
    4. RSS抓取
    5. 网页博客抓取
    6. AI分析器
    7. 知识库
    8. QA问答
    9. 飞书推送
    10. 统计系统
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.details = []
    
    def add_pass(self, name, msg=""):
        self.passed += 1
        self.details.append(("PASS", name, msg))
        print(f"  ✅ {name}" + (f" - {msg}" if msg else ""))
    
    def add_fail(self, name, msg=""):
        self.failed += 1
        self.details.append(("FAIL", name, msg))
        print(f"  ❌ {name}" + (f" - {msg}" if msg else ""))
    
    def add_skip(self, name, msg=""):
        self.skipped += 1
        self.details.append(("SKIP", name, msg))
        print(f"  ⏭️  {name}" + (f" - {msg}" if msg else ""))


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_imports(result: TestResult):
    """测试模块导入"""
    print_header("1. 模块导入测试")
    
    modules = [
        ("src.config", "配置模块"),
        ("src.repository", "数据仓库"),
        ("src.models", "数据模型"),
        ("src.fetchers.rss_fetcher", "RSS抓取器"),
        ("src.fetchers.web_blog_fetcher", "网页博客抓取器"),
        ("src.analyzers.ai_analyzer", "AI分析器"),
        ("src.qa.knowledge_base", "知识库"),
        ("src.qa.qa_engine", "QA引擎"),
        ("src.qa.event_server", "事件服务器"),
        ("src.bots.feishu_bot", "飞书机器人"),
        ("src.stats.collector", "统计收集器"),
    ]
    
    for module, desc in modules:
        try:
            __import__(module)
            result.add_pass(desc)
        except Exception as e:
            result.add_fail(desc, str(e)[:50])


def test_config(result: TestResult):
    """测试配置加载"""
    print_header("2. 配置加载测试")
    
    try:
        from src.config import load_config
        config = load_config()
        result.add_pass("配置文件加载")
        
        # 检查关键配置
        checks = [
            ("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
            ("FEISHU_WEBHOOK_URL", os.getenv("FEISHU_WEBHOOK_URL")),
            ("FEISHU_APP_ID", os.getenv("FEISHU_APP_ID")),
            ("FEISHU_APP_SECRET", os.getenv("FEISHU_APP_SECRET")),
        ]
        
        for name, value in checks:
            if value and not value.startswith("your-"):
                result.add_pass(f"环境变量 {name}")
            else:
                result.add_skip(f"环境变量 {name}", "未配置")
                
    except Exception as e:
        result.add_fail("配置加载", str(e)[:50])


def test_database(result: TestResult):
    """测试数据库"""
    print_header("3. 数据库测试")
    
    try:
        from src.repository import ArticleRepository
        from src.config import load_config
        
        config = load_config()
        db_path = config.get("database", {}).get("path", "data/articles.db")
        
        repo = ArticleRepository(db_path)
        repo.init_db()
        result.add_pass("数据库初始化")
        
        articles = repo.get_all_articles()
        result.add_pass(f"查询文章", f"共 {len(articles)} 篇")
        
        unpushed = repo.get_unpushed_articles()
        result.add_pass(f"查询待推送", f"共 {len(unpushed)} 篇")
        
        repo.close()
        
    except Exception as e:
        result.add_fail("数据库", str(e)[:50])


def test_rss_fetcher(result: TestResult):
    """测试RSS抓取"""
    print_header("4. RSS抓取测试")
    
    try:
        from src.fetchers.rss_fetcher import RSSFetcher
        
        fetcher = RSSFetcher({'opml_path': 'feeds.opml'})
        result.add_pass("RSSFetcher初始化")
        
        # 检查OPML文件
        opml_files = list(Path("rss").glob("*.opml"))
        result.add_pass(f"OPML文件", f"发现 {len(opml_files)} 个")
        
    except Exception as e:
        result.add_fail("RSS抓取器", str(e)[:50])


def test_web_blog_fetcher(result: TestResult):
    """测试网页博客抓取"""
    print_header("5. 网页博客抓取测试")
    
    try:
        from src.fetchers.web_blog_fetcher import AtumBlogFetcher
        
        fetcher = AtumBlogFetcher({
            'enabled': True,
            'timeout': 30,
            'days_back': 365
        })
        result.add_pass("AtumBlogFetcher初始化")
        
        # 实际抓取测试
        fetch_result = fetcher.fetch()
        if fetch_result.error:
            result.add_fail("Atum博客抓取", fetch_result.error[:50])
        else:
            result.add_pass("Atum博客抓取", f"获取 {len(fetch_result.items)} 篇")
            
    except Exception as e:
        result.add_fail("网页博客抓取", str(e)[:50])


def test_ai_analyzer(result: TestResult):
    """测试AI分析器"""
    print_header("6. AI分析器测试")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("your-"):
        result.add_skip("AI分析器", "未配置OPENAI_API_KEY")
        return
    
    try:
        from src.analyzers.ai_analyzer import AIAnalyzer
        from src.config import load_config
        
        config = load_config()
        ai_config = config.get("ai", {})
        
        analyzer = AIAnalyzer(ai_config)
        result.add_pass("AIAnalyzer初始化")
        
        # 简单测试（不实际调用API）
        result.add_pass("AI分析器就绪")
        
    except Exception as e:
        result.add_fail("AI分析器", str(e)[:50])


def test_knowledge_base(result: TestResult):
    """测试知识库"""
    print_header("7. 知识库测试")
    
    try:
        from src.qa.knowledge_base import KnowledgeBase
        from src.config import load_config
        
        config = load_config()
        qa_config = config.get("knowledge_qa", {})
        
        kb_config = {
            "chroma_path": qa_config.get("chroma", {}).get("path", "data/chroma_db"),
            "collection_name": qa_config.get("chroma", {}).get("collection_name", "knowledge_articles"),
        }
        
        kb = KnowledgeBase(kb_config)
        result.add_pass("KnowledgeBase初始化")
        
        stats = kb.get_stats()
        result.add_pass("知识库统计", f"共 {stats['total_documents']} 个文档")
        
    except Exception as e:
        result.add_fail("知识库", str(e)[:50])


def test_qa_engine(result: TestResult):
    """测试QA引擎"""
    print_header("8. QA引擎测试")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("your-"):
        result.add_skip("QA引擎", "未配置OPENAI_API_KEY")
        return
    
    try:
        from src.qa.qa_engine import QAEngine
        from src.qa.knowledge_base import KnowledgeBase
        from src.qa.embedding_service import EmbeddingService
        from src.qa.context_manager import ContextManager
        from src.qa.query_processor import QueryProcessor
        from src.analyzers.ai_analyzer import AIAnalyzer
        from src.config import load_config
        
        config = load_config()
        qa_config = config.get("knowledge_qa", {})
        ai_config = config.get("ai", {})
        
        # 初始化组件
        kb_config = {
            "chroma_path": qa_config.get("chroma", {}).get("path", "data/chroma_db"),
            "collection_name": qa_config.get("chroma", {}).get("collection_name", "knowledge_articles"),
        }
        kb = KnowledgeBase(kb_config)
        
        embedding_service = EmbeddingService(qa_config.get("embedding", {}))
        kb.set_embedding_service(embedding_service)
        
        context_manager = ContextManager()
        query_processor = QueryProcessor()
        ai_analyzer = AIAnalyzer(ai_config)
        
        qa_engine = QAEngine(
            knowledge_base=kb,
            context_manager=context_manager,
            query_processor=query_processor,
            ai_analyzer=ai_analyzer
        )
        result.add_pass("QAEngine初始化")
        
    except Exception as e:
        result.add_fail("QA引擎", str(e)[:50])


def test_feishu_bot(result: TestResult):
    """测试飞书机器人"""
    print_header("9. 飞书机器人测试")
    
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook_url or webhook_url.startswith("your-"):
        result.add_skip("飞书Webhook", "未配置FEISHU_WEBHOOK_URL")
    else:
        try:
            from src.bots.feishu_bot import FeishuBot
            bot = FeishuBot(webhook_url)
            result.add_pass("FeishuBot初始化")
        except Exception as e:
            result.add_fail("FeishuBot", str(e)[:50])
    
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        result.add_skip("飞书AppBot", "未配置APP_ID/APP_SECRET")
    else:
        try:
            from src.bots.feishu_bot import FeishuAppBot
            app_bot = FeishuAppBot(app_id=app_id, app_secret=app_secret)
            result.add_pass("FeishuAppBot初始化")
        except Exception as e:
            result.add_fail("FeishuAppBot", str(e)[:50])


def test_event_server(result: TestResult):
    """测试事件服务器"""
    print_header("10. 事件服务器测试")
    
    try:
        from src.qa.event_server import FeishuEventServer
        
        server = FeishuEventServer({
            "host": "0.0.0.0",
            "port": 8080,
            "verification_token": "test"
        })
        result.add_pass("FeishuEventServer初始化")
        
        # 测试URL验证
        response = server.handle_event({
            "challenge": "test123",
            "token": "test",
            "type": "url_verification"
        })
        if response.get("challenge") == "test123":
            result.add_pass("URL验证处理")
        else:
            result.add_fail("URL验证处理")
            
    except Exception as e:
        result.add_fail("事件服务器", str(e)[:50])


def test_stats_system(result: TestResult):
    """测试统计系统"""
    print_header("11. 统计系统测试")
    
    try:
        from src.stats import StatsCollector, StatsStore, StatsAggregator
        
        # 使用临时文件而不是内存数据库
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        store = StatsStore(temp_db)
        result.add_pass("StatsStore初始化")
        
        collector = StatsCollector(store)
        result.add_pass("StatsCollector初始化")
        
        aggregator = StatsAggregator(store)
        result.add_pass("StatsAggregator初始化")
        
        # 测试热门文章查询
        hot_articles = aggregator.get_hot_articles(days=7, limit=10)
        result.add_pass("统计聚合查询")
        
        # 清理临时文件
        import os
        os.unlink(temp_db)
        
    except Exception as e:
        result.add_fail("统计系统", str(e)[:50])


def test_scheduler(result: TestResult):
    """测试调度器"""
    print_header("12. 调度器测试")
    
    try:
        from src.scheduler import Scheduler
        from src.config import load_config
        
        config = load_config()
        scheduler = Scheduler(config)
        result.add_pass("Scheduler初始化")
        
    except Exception as e:
        result.add_fail("调度器", str(e)[:50])


def print_summary(result: TestResult):
    """打印测试总结"""
    print_header("测试总结")
    
    total = result.passed + result.failed + result.skipped
    
    print(f"\n  总计: {total} 项测试")
    print(f"  ✅ 通过: {result.passed}")
    print(f"  ❌ 失败: {result.failed}")
    print(f"  ⏭️  跳过: {result.skipped}")
    
    if result.failed == 0:
        print("\n  🎉 所有测试通过！系统可以正常运行。")
    else:
        print("\n  ⚠️  部分测试失败，请检查配置和依赖。")
        print("\n  失败项:")
        for status, name, msg in result.details:
            if status == "FAIL":
                print(f"    - {name}: {msg}")
    
    if result.skipped > 0:
        print("\n  跳过项（需要配置环境变量）:")
        for status, name, msg in result.details:
            if status == "SKIP":
                print(f"    - {name}: {msg}")


def main():
    print("\n" + "=" * 60)
    print("  Daily Article Aggregator - 完整功能测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    result = TestResult()
    
    # 运行所有测试
    test_imports(result)
    test_config(result)
    test_database(result)
    test_rss_fetcher(result)
    test_web_blog_fetcher(result)
    test_ai_analyzer(result)
    test_knowledge_base(result)
    test_qa_engine(result)
    test_feishu_bot(result)
    test_event_server(result)
    test_stats_system(result)
    test_scheduler(result)
    
    print_summary(result)
    
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
