"""
调度器模块
Scheduler Module

实现定时任务调度，执行完整的爬取-分析-推送流程。
Implements scheduled task execution for the complete fetch-analyze-push workflow.

需求 7.1: 支持定时执行（每天指定时间）
需求 7.2: 支持手动触发执行
需求 7.3: 执行完整的爬取-分析-推送流程
需求 7.4: 记录执行日志
需求 7.5: 支持命令行参数控制
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import schedule

from src.config import load_config, get_config_value
from src.fetchers.arxiv_fetcher import ArxivFetcher
from src.fetchers.rss_fetcher import RSSFetcher
from src.processors.content_processor import ContentProcessor
from src.analyzers.ai_analyzer import AIAnalyzer
from src.repository import ArticleRepository
from src.bots.feishu_bot import FeishuBot, FeishuAppBot

# Import new fetchers and components
try:
    from src.fetchers.dblp_fetcher import DBLPFetcher
    from src.fetchers.nvd_fetcher import NVDFetcher
    from src.fetchers.kev_fetcher import KEVFetcher
    from src.fetchers.huggingface_fetcher import HuggingFaceFetcher
    from src.fetchers.web_blog_fetcher import HunyuanFetcher, AnthropicRedFetcher, AtumBlogFetcher
    from src.fetchers.github_fetcher import GitHubFetcher
    from src.fetchers.pwc_fetcher import PWCFetcher
    from src.fetchers.blog_fetcher import BlogFetcher
    from src.filters.vulnerability_filter import VulnerabilityFilter
    from src.scoring.priority_scorer import PriorityScorer
    from src.pushers.tiered_pusher import TieredPusher
    from src.utils.deduplication import deduplicate_by_url
    ADVANCED_FEATURES = True
except ImportError:
    ADVANCED_FEATURES = False

# Import Feishu Bitable
try:
    from src.bots.feishu_bitable import FeishuBitable
    BITABLE_AVAILABLE = True
except ImportError:
    BITABLE_AVAILABLE = False

# Import Checkpoint Manager
try:
    from src.utils.checkpoint import CheckpointManager
    CHECKPOINT_AVAILABLE = True
except ImportError:
    CHECKPOINT_AVAILABLE = False

# 配置日志
logger = logging.getLogger(__name__)


class FeishuAppBotWrapper:
    """
    FeishuAppBot 包装类，用于兼容 FeishuBot 接口

    将 FeishuAppBot 的 API 调用适配为 FeishuBot 接口，
    以便在现有代码中使用应用中心 API 发送消息。
    """

    def __init__(self, app_bot: FeishuAppBot, chat_id: str, proxy: str = None):
        """
        初始化包装类

        Args:
            app_bot: FeishuAppBot 实例
            chat_id: 群聊 ID
            proxy: 代理 URL（可选）
        """
        self.app_bot = app_bot
        self.chat_id = chat_id
        self.proxy = proxy

    def send_text(self, text: str) -> bool:
        """
        发送文本消息到群聊

        Args:
            text: 消息文本

        Returns:
            是否发送成功
        """
        # 构建飞书富文本格式的文本消息
        content = {"text": text}
        return self.app_bot.send_message_to_chat(
            self.chat_id,
            "text",
            content
        )

    def send_rich_text(self, title: str, content: list) -> bool:
        """
        发送富文本消息到群聊

        Args:
            title: 消息标题
            content: 富文本内容（飞书格式的二维数组）

        Returns:
            是否发送成功
        """
        post_content = {
            "zh_cn": {
                "title": title,
                "content": content
            }
        }
        return self.app_bot.send_message_to_chat(
            self.chat_id,
            "post",
            post_content
        )

    def push_articles(self, articles: list[dict], batch_size: int = 10, with_feedback: bool = True) -> bool:
        """
        推送文章列表到群聊

        Args:
            articles: 文章列表
            batch_size: 每批推送的文章数量
            with_feedback: 是否添加反馈按钮

        Returns:
            是否全部推送成功
        """
        if not articles:
            logger.info("没有文章需要推送")
            return True

        # 过滤有效文章
        valid_articles = [
            a for a in articles
            if a.get('title', '').strip() and a.get('url', '').strip()
        ]

        if not valid_articles:
            logger.warning("所有文章都缺少必要字段（title或url）")
            return False

        total_count = len(valid_articles)
        logger.info(f"准备推送 {total_count} 篇文章到飞书（每批 {batch_size} 篇）")

        # 分批推送
        all_success = True

        for i in range(0, total_count, batch_size):
            batch = valid_articles[i:i + batch_size]
            batch_start = i + 1
            batch_end = min(i + batch_size, total_count)

            # 构建富文本内容
            content = []
            for j, article in enumerate(batch, 1):
                title = article.get('title', '').strip()
                url = article.get('url', '').strip()

                if not title or not url:
                    continue

                # 标题行（带链接）
                title_line = [
                    {"tag": "text", "text": f"{batch_start + j - 1}. "},
                    {"tag": "a", "text": title, "href": url}
                ]
                content.append(title_line)

                # 摘要行
                zh_summary = article.get('zh_summary', '').strip()
                summary = article.get('summary', '').strip()

                if zh_summary:
                    content.append([{"tag": "text", "text": f"   摘要: {zh_summary}"}])
                elif summary:
                    content.append([{"tag": "text", "text": f"   摘要: {summary}"}])

                # 空行分隔
                content.append([{"tag": "text", "text": ""}])

            title = f"📚 今日文章推荐 ({batch_start}-{batch_end}/{total_count}篇)"

            success = self.send_rich_text(title, content)

            if not success:
                logger.error(f"第 {i // batch_size + 1} 批推送失败")
                all_success = False

            # 批次之间间隔
            if i + batch_size < total_count:
                time.sleep(1)

        if all_success:
            logger.info(f"全部 {total_count} 篇文章推送成功")
        else:
            logger.warning(f"部分批次推送失败，请检查日志")

        return all_success

    def send_interactive_card(self, card: dict) -> bool:
        """
        发送交互式卡片消息到群聊

        Args:
            card: 飞书卡片 JSON 结构

        Returns:
            是否发送成功
        """
        if not card:
            logger.warning("尝试发送空卡片")
            return False

        return self.app_bot.send_message_to_chat(
            self.chat_id,
            "interactive",
            card
        )


class Scheduler:
    """
    定时任务调度器
    Scheduled Task Scheduler
    
    负责协调各个组件，执行完整的爬取-分析-推送任务流程。
    Coordinates all components to execute the complete fetch-analyze-push workflow.
    
    Attributes:
        config: 完整配置字典
        schedule_time: 每日执行时间（如 "09:00"）
        timezone: 时区（如 "Asia/Shanghai"）
        _running: 调度器是否正在运行
    """
    
    def __init__(self, config: dict):
        """
        初始化调度器
        Initialize the scheduler
        
        Args:
            config: 完整配置字典，包含所有组件的配置
                   Complete config dict containing all component configurations
        
        Examples:
            >>> config = load_config("config.yaml")
            >>> scheduler = Scheduler(config)
        """
        self.config = config
        
        # 调度配置
        schedule_config = config.get('schedule', {})
        self.schedule_time = schedule_config.get('time', '09:00')
        self.timezone = schedule_config.get('timezone', 'Asia/Shanghai')
        
        # 断点续传配置
        checkpoint_config = config.get('checkpoint', {})
        self.checkpoint_enabled = checkpoint_config.get('enabled', True)
        self.checkpoint_dir = checkpoint_config.get('dir', 'data/checkpoints')
        self.checkpoint_max_age = checkpoint_config.get('max_age_hours', 24)
        self.checkpoint_save_interval = checkpoint_config.get('save_interval', 10)
        
        # 运行状态
        self._running = False
        
        logger.info(f"Scheduler initialized with schedule_time={self.schedule_time}, "
                   f"timezone={self.timezone}, checkpoint_enabled={self.checkpoint_enabled}")
    
    def _init_components(self) -> dict[str, Any]:
        """
        初始化所有组件
        Initialize all components
        
        Returns:
            包含所有组件实例的字典
            Dict containing all component instances
        """
        components = {}
        
        # 数据库配置
        db_config = self.config.get('database', {})
        db_path = db_config.get('path', 'data/articles.db')
        
        # 确保数据库目录存在
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化仓库
        components['repository'] = ArticleRepository(db_path)
        components['repository'].init_db()
        logger.info(f"ArticleRepository initialized with db_path={db_path}")
        
        # 数据源配置
        sources_config = self.config.get('sources', {})
        
        # arXiv获取器
        arxiv_config = sources_config.get('arxiv', {})
        if arxiv_config.get('enabled', True):
            components['arxiv_fetcher'] = ArxivFetcher(arxiv_config)
            logger.info("ArxivFetcher initialized")
        
        # RSS获取器
        rss_config = sources_config.get('rss', {})
        if rss_config.get('enabled', True):
            # 添加代理配置
            proxy_config = self.config.get('proxy', {})
            if proxy_config.get('enabled', False):
                rss_config['proxy'] = proxy_config.get('url')
            components['rss_fetcher'] = RSSFetcher(rss_config)
            logger.info("RSSFetcher initialized")
        
        # 内容处理器
        content_config = self.config.get('content', {})
        proxy_config = self.config.get('proxy', {})
        processor_config = {
            'max_content_length': content_config.get('max_length', 50000),
            'truncation_marker': content_config.get('truncation_marker', '\n\n... [内容已截断]'),
        }
        if proxy_config.get('enabled', False):
            processor_config['proxy'] = proxy_config.get('url')
        components['content_processor'] = ContentProcessor(processor_config)
        logger.info("ContentProcessor initialized")
        
        # AI分析器
        ai_config = self.config.get('ai', {})
        if ai_config.get('enabled', True):
            components['ai_analyzer'] = AIAnalyzer(ai_config)
            logger.info("AIAnalyzer initialized")
        
        # 飞书机器人
        feishu_config = self.config.get('feishu', {})
        app_id = feishu_config.get('app_id', '')
        app_secret = feishu_config.get('app_secret', '')
        chat_id = feishu_config.get('chat_id', '')
        webhook_url = feishu_config.get('webhook_url', '')

        # 优先使用应用中心 API（FeishuAppBot）
        if app_id and app_secret and chat_id:
            proxy_url = None
            proxy_config = self.config.get('proxy', {})
            if proxy_config.get('enabled', False):
                proxy_url = proxy_config.get('url')
            # 创建 FeishuAppBot 实例并包装为兼容 FeishuBot 接口
            app_bot = FeishuAppBot(app_id, app_secret)
            # 创建包装类以兼容原有接口
            components['feishu_bot'] = FeishuAppBotWrapper(app_bot, chat_id, proxy_url)
            logger.info(f"FeishuAppBot initialized with chat_id={chat_id}")
        elif webhook_url:
            proxy_url = None
            proxy_config = self.config.get('proxy', {})
            if proxy_config.get('enabled', False):
                proxy_url = proxy_config.get('url')
            components['feishu_bot'] = FeishuBot(webhook_url, proxy=proxy_url)
            logger.info("FeishuBot initialized (webhook)")
        else:
            logger.warning("Feishu app_id/app_secret/chat_id or webhook_url not configured, push will be skipped")
        
        # 初始化高级功能组件（如果可用）
        if ADVANCED_FEATURES:
            data_sources_config = self.config.get('data_sources', {})
            
            # DBLP Fetcher
            dblp_config = data_sources_config.get('dblp', {})
            if dblp_config.get('enabled', False):
                components['dblp_fetcher'] = DBLPFetcher(dblp_config)
                logger.info("DBLPFetcher initialized")
            
            # NVD Fetcher
            nvd_config = data_sources_config.get('nvd', {})
            if nvd_config.get('enabled', False):
                components['nvd_fetcher'] = NVDFetcher(nvd_config)
                logger.info("NVDFetcher initialized")
            
            # KEV Fetcher
            kev_config = data_sources_config.get('kev', {})
            if kev_config.get('enabled', False):
                components['kev_fetcher'] = KEVFetcher(kev_config)
                logger.info("KEVFetcher initialized")
            
            # HuggingFace Fetcher
            hf_config = data_sources_config.get('huggingface', {})
            if hf_config.get('enabled', False):
                components['huggingface_fetcher'] = HuggingFaceFetcher(hf_config)
                logger.info("HuggingFaceFetcher initialized")
            
            # Hunyuan Research Fetcher (腾讯混元研究)
            hunyuan_config = data_sources_config.get('hunyuan', {})
            if hunyuan_config.get('enabled', False):
                components['hunyuan_fetcher'] = HunyuanFetcher(hunyuan_config)
                logger.info("HunyuanFetcher initialized")
            
            # GitHub Fetcher (热门项目)
            github_config = data_sources_config.get('github', {})
            if github_config.get('enabled', False):
                components['github_fetcher'] = GitHubFetcher(github_config)
                logger.info("GitHubFetcher initialized")
            
            # PWC Fetcher
            pwc_config = data_sources_config.get('pwc', {})
            if pwc_config.get('enabled', False):
                components['pwc_fetcher'] = PWCFetcher(pwc_config)
                logger.info("PWCFetcher initialized")
            
            # Blog Fetcher
            blogs_config = data_sources_config.get('blogs', {})
            if blogs_config.get('enabled', False):
                components['blog_fetcher'] = BlogFetcher(blogs_config)
                logger.info("BlogFetcher initialized")
            
            # Anthropic Red Team Fetcher
            anthropic_red_config = data_sources_config.get('anthropic_red', {})
            if anthropic_red_config.get('enabled', False):
                components['anthropic_red_fetcher'] = AnthropicRedFetcher(anthropic_red_config)
                logger.info("AnthropicRedFetcher initialized")
            
            # Atum Blog Fetcher
            atum_blog_config = data_sources_config.get('atum_blog', {})
            if atum_blog_config.get('enabled', False):
                components['atum_blog_fetcher'] = AtumBlogFetcher(atum_blog_config)
                logger.info("AtumBlogFetcher initialized")
            
            # Vulnerability Filter
            vuln_filter_config = self.config.get('vulnerability_filter', {})
            if vuln_filter_config.get('enabled', False) and 'ai_analyzer' in components:
                components['vulnerability_filter'] = VulnerabilityFilter(
                    vuln_filter_config, 
                    components['ai_analyzer']
                )
                logger.info("VulnerabilityFilter initialized")
            
            # Priority Scorer
            priority_config = self.config.get('priority_scoring', {})
            if priority_config.get('enabled', False):
                components['priority_scorer'] = PriorityScorer(
                    priority_config,
                    components.get('ai_analyzer')
                )
                logger.info("PriorityScorer initialized")
            
            # Tiered Pusher
            tiered_push_config = self.config.get('tiered_push', {})
            if tiered_push_config.get('enabled', False) and 'feishu_bot' in components:
                components['tiered_pusher'] = TieredPusher(
                    tiered_push_config,
                    components['feishu_bot'],
                    components.get('ai_analyzer')
                )
                logger.info("TieredPusher initialized")
            
            # Smart Selector
            smart_selector_config = self.config.get('smart_selector', {})
            if smart_selector_config.get('enabled', True):  # 默认启用
                from src.pushers.smart_selector import SmartSelector
                components['smart_selector'] = SmartSelector(
                    smart_selector_config,
                    components.get('ai_analyzer')
                )
                logger.info("SmartSelector initialized")
        
        # 飞书多维表格（用于数据可视化）
        if BITABLE_AVAILABLE:
            bitable_config = self.config.get('feishu_bitable', {})
            if bitable_config.get('enabled', False) and bitable_config.get('app_id'):
                try:
                    components['feishu_bitable'] = FeishuBitable(bitable_config)
                    logger.info("FeishuBitable initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize FeishuBitable: {e}")

        # 用户反馈系统
        feedback_config = self.config.get('feedback', {})
        if feedback_config.get('enabled', False):
            try:
                from src.feedback.feedback_handler import FeedbackHandler
                db_path = feedback_config.get('db_path', 'data/articles.db')
                components['feedback_handler'] = FeedbackHandler(db_path)
                logger.info("FeedbackHandler initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize FeedbackHandler: {e}")

        # PDF翻译服务
        pdf_translation_config = self.config.get('pdf_translation', {})
        if pdf_translation_config.get('enabled', False):
            try:
                from src.bots.feishu_pdf_translator import FeishuPDFTranslationService
                components['pdf_translation_service'] = FeishuPDFTranslationService(pdf_translation_config)
                logger.info("FeishuPDFTranslationService initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize PDF translation service: {e}")

        return components
    
    def _cleanup_components(self, components: dict[str, Any]):
        """
        清理组件资源
        Cleanup component resources
        
        Args:
            components: 组件字典
        """
        # 关闭内容处理器（释放Playwright资源）
        if 'content_processor' in components:
            try:
                components['content_processor'].close()
            except Exception as e:
                logger.warning(f"Error closing content_processor: {e}")
        
        # 关闭数据库连接
        if 'repository' in components:
            try:
                components['repository'].close()
            except Exception as e:
                logger.warning(f"Error closing repository: {e}")
    
    def _push_error_report(
        self, 
        feishu_bot, 
        errors: list[dict], 
        duration: float
    ):
        """
        推送错误汇总报告到飞书
        
        Args:
            feishu_bot: 飞书机器人实例
            errors: 错误列表 [{'source': 'xxx', 'error': 'xxx'}, ...]
            duration: 任务耗时（秒）
        """
        if not errors:
            return
        
        try:
            # 构建错误报告
            error_lines = []
            for err in errors:
                source = err.get('source', 'Unknown')
                error_msg = err.get('error', 'Unknown error')
                # 截断过长的错误信息
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + '...'
                error_lines.append(f"• {source}: {error_msg}")
            
            report = f"""⚠️ 数据源抓取异常报告

任务耗时: {duration:.1f}s
异常数量: {len(errors)}

异常详情:
{chr(10).join(error_lines)}"""
            
            # 使用飞书机器人发送
            feishu_bot.send_text(report)
            logger.info(f"错误报告已推送，共 {len(errors)} 个异常")
            
        except Exception as e:
            logger.error(f"推送错误报告失败: {e}")
    
    def _get_existing_urls(self, repository: ArticleRepository) -> set[str]:
        """
        获取数据库中已存在的所有文章 URL
        Get all existing article URLs from database
        
        用于在抓取阶段快速过滤已存在的文章，避免重复处理。
        
        Args:
            repository: 文章仓库实例
        
        Returns:
            已存在的 URL 集合
        """
        try:
            conn = repository._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM articles")
            rows = cursor.fetchall()
            return {row['url'] for row in rows}
        except Exception as e:
            logger.warning(f"获取已存在 URL 失败: {e}")
            return set()
    
    def run_task(self):
        """
        执行完整的爬取-分析-推送任务
        Execute the complete fetch-analyze-push task
        
        任务流程：
        1. 从arXiv获取论文
        2. 从RSS订阅源获取文章（支持断点续传）
        3. 检查数据库去重
        4. 处理内容（获取HTML并转换为Markdown）
        5. AI分析（生成摘要、分类、翻译）
        6. 保存到数据库
        7. 获取未推送文章并推送到飞书
        8. 标记文章为已推送
        
        Task workflow:
        1. Fetch papers from arXiv
        2. Fetch articles from RSS feeds (with checkpoint/resume support)
        3. Check for duplicates in database
        4. Process content (fetch HTML and convert to Markdown)
        5. AI analysis (generate summary, category, translation)
        6. Save to database
        7. Get unpushed articles and push to Feishu
        8. Mark articles as pushed
        
        **验证: 需求 7.3, 7.4**
        """
        start_time = datetime.now()
        logger.info(f"=== Task started at {start_time.isoformat()} ===")
        
        components = None
        checkpoint_manager = None
        fetch_errors: list[dict] = []  # 收集抓取错误
        
        try:
            # 初始化组件
            components = self._init_components()
            repository = components['repository']
            
            # 初始化断点续传管理器
            if CHECKPOINT_AVAILABLE and self.checkpoint_enabled:
                checkpoint_manager = CheckpointManager(
                    checkpoint_dir=self.checkpoint_dir,
                    max_age_hours=self.checkpoint_max_age,
                    auto_save_interval=self.checkpoint_save_interval
                )
                checkpoint_manager.cleanup_old_checkpoints()
                logger.info("断点续传管理器已初始化")
            
            all_articles = []
            
            # 预先获取数据库中已存在的 URL 集合（用于所有数据源的快速去重）
            existing_urls = self._get_existing_urls(repository)
            logger.info(f"数据库中已有 {len(existing_urls)} 篇文章")
            
            # 步骤1: 从arXiv获取论文
            if 'arxiv_fetcher' in components:
                logger.info("Step 1: Fetching papers from arXiv...")
                try:
                    arxiv_fetcher = components['arxiv_fetcher']
                    papers = arxiv_fetcher.fetch_papers()
                    
                    # 应用关键词过滤
                    if arxiv_fetcher.keywords:
                        papers = arxiv_fetcher.filter_by_keywords(papers)
                    
                    # 过滤已存在的文章
                    new_papers = [p for p in papers if p.get('url', '') not in existing_urls]
                    logger.info(f"arXiv: 新增 {len(new_papers)} 篇，跳过 {len(papers) - len(new_papers)} 篇已存在")
                    all_articles.extend(new_papers)
                except Exception as e:
                    logger.error(f"Error fetching arXiv papers: {e}")
                    fetch_errors.append({'source': 'arXiv', 'error': str(e)})
            
            # 步骤2: 从RSS订阅源获取文章（支持断点续传）
            if 'rss_fetcher' in components:
                logger.info("Step 2: Fetching articles from RSS feeds...")
                try:
                    rss_fetcher = components['rss_fetcher']
                    opml_path = rss_fetcher.opml_path
                    
                    if opml_path and Path(opml_path).exists():
                        all_urls = rss_fetcher.parse_opml(opml_path)
                        
                        # 使用断点续传
                        if checkpoint_manager:
                            fetch_checkpoint = checkpoint_manager.start_fetch(all_urls)
                            pending_urls = checkpoint_manager.get_pending_feeds(all_urls)
                            
                            # 先加载已抓取的文章（过滤掉已存在的）
                            existing_articles = checkpoint_manager.get_all_fetched_articles()
                            if existing_articles:
                                new_from_checkpoint = [
                                    a for a in existing_articles 
                                    if a.get('url', '') not in existing_urls
                                ]
                                all_articles.extend(new_from_checkpoint)
                                logger.info(f"从检查点恢复 {len(new_from_checkpoint)} 篇新文章（跳过 {len(existing_articles) - len(new_from_checkpoint)} 篇已存在）")
                            
                            if pending_urls:
                                logger.info(f"待抓取订阅源: {len(pending_urls)}/{len(all_urls)}")
                                
                                # 定义回调函数
                                def on_feed_complete(url, name, articles):
                                    checkpoint_manager.mark_feed_completed(url, articles, name)
                                
                                def on_feed_error(url, error):
                                    checkpoint_manager.mark_feed_failed(url, error)
                                
                                # 抓取剩余订阅源
                                feeds_result = rss_fetcher.fetch_all_feeds(
                                    pending_urls,
                                    on_feed_complete=on_feed_complete,
                                    on_feed_error=on_feed_error
                                )
                                
                                # 合并新抓取的文章（过滤掉已存在的）
                                new_count = 0
                                skip_count = 0
                                for feed_name, articles in feeds_result.items():
                                    for article in articles:
                                        if article.get('url', '') not in existing_urls:
                                            all_articles.append(article)
                                            new_count += 1
                                        else:
                                            skip_count += 1
                                
                                logger.info(f"RSS 抓取: 新增 {new_count} 篇，跳过 {skip_count} 篇已存在")
                                
                                # 保存最终检查点
                                checkpoint_manager.save_fetch_checkpoint()
                            else:
                                logger.info("所有订阅源已在之前的运行中完成")
                            
                            checkpoint_manager.complete_fetch()
                        else:
                            # 不使用断点续传，直接抓取（但仍然过滤已存在的）
                            feeds_result = rss_fetcher.fetch_all_feeds(all_urls)
                            new_count = 0
                            skip_count = 0
                            for feed_name, articles in feeds_result.items():
                                for article in articles:
                                    if article.get('url', '') not in existing_urls:
                                        all_articles.append(article)
                                        new_count += 1
                                    else:
                                        skip_count += 1
                            
                            logger.info(f"RSS 抓取: 新增 {new_count} 篇，跳过 {skip_count} 篇已存在")
                        
                        logger.info(f"RSS抓取完成，共 {len(all_articles)} 篇新文章")
                    else:
                        logger.warning(f"OPML file not found: {opml_path}")
                except Exception as e:
                    logger.error(f"Error fetching RSS articles: {e}")
                    fetch_errors.append({'source': 'RSS', 'error': str(e)})
                    # 保存检查点以便下次恢复
                    if checkpoint_manager:
                        checkpoint_manager.save_fetch_checkpoint()
            
            # 步骤2.1: 从新数据源获取文章（高级功能）
            # 注意：existing_urls 已在前面获取
            vulnerability_articles = []  # 漏洞类文章单独处理
            
            # DBLP - 安全四大顶会
            if 'dblp_fetcher' in components:
                logger.info("Step 2.1a: Fetching papers from DBLP...")
                try:
                    result = components['dblp_fetcher'].fetch()
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        all_articles.extend(new_items)
                        logger.info(f"DBLP: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching DBLP papers: {e}")
                    fetch_errors.append({'source': 'DBLP', 'error': str(e)})
            
            # NVD - 漏洞数据库
            if 'nvd_fetcher' in components:
                logger.info("Step 2.1b: Fetching CVEs from NVD...")
                try:
                    result = components['nvd_fetcher'].fetch()
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        vulnerability_articles.extend(new_items)
                        logger.info(f"NVD: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching NVD CVEs: {e}")
                    fetch_errors.append({'source': 'NVD', 'error': str(e)})
            
            # KEV - CISA 在野利用漏洞
            if 'kev_fetcher' in components:
                logger.info("Step 2.1c: Fetching KEV entries from CISA...")
                try:
                    result = components['kev_fetcher'].fetch()
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        vulnerability_articles.extend(new_items)
                        logger.info(f"KEV: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching KEV entries: {e}")
                    fetch_errors.append({'source': 'KEV', 'error': str(e)})
            
            # HuggingFace Papers
            if 'huggingface_fetcher' in components:
                logger.info("Step 2.1d: Fetching papers from HuggingFace...")
                try:
                    result = components['huggingface_fetcher'].fetch()
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        all_articles.extend(new_items)
                        logger.info(f"HuggingFace: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching HuggingFace papers: {e}")
                    fetch_errors.append({'source': 'HuggingFace', 'error': str(e)})
            
            # Papers With Code
            if 'pwc_fetcher' in components:
                logger.info("Step 2.1e: Fetching papers from Papers With Code...")
                try:
                    result = components['pwc_fetcher'].fetch()
                    if result.error:
                        fetch_errors.append({'source': 'PWC', 'error': result.error})
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        all_articles.extend(new_items)
                        logger.info(f"PWC: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching PWC papers: {e}")
                    fetch_errors.append({'source': 'PWC', 'error': str(e)})
            
            # 大厂博客
            if 'blog_fetcher' in components:
                logger.info("Step 2.1f: Fetching articles from tech blogs...")
                try:
                    result = components['blog_fetcher'].fetch()
                    if result.error:
                        fetch_errors.append({'source': 'Blogs', 'error': result.error})
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        all_articles.extend(new_items)
                        logger.info(f"Blogs: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching blog articles: {e}")
                    fetch_errors.append({'source': 'Blogs', 'error': str(e)})
            
            # 腾讯混元研究
            if 'hunyuan_fetcher' in components:
                logger.info("Step 2.1g: Fetching articles from Hunyuan Research...")
                try:
                    result = components['hunyuan_fetcher'].fetch()
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        all_articles.extend(new_items)
                        logger.info(f"Hunyuan: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching Hunyuan Research articles: {e}")
                    fetch_errors.append({'source': 'Hunyuan', 'error': str(e)})
            
            # GitHub 热门项目
            if 'github_fetcher' in components:
                logger.info("Step 2.1h: Fetching trending projects from GitHub...")
                try:
                    projects = components['github_fetcher'].fetch()
                    if projects:
                        new_items = [p for p in projects if p.get('url', '') not in existing_urls]
                        all_articles.extend(new_items)
                        logger.info(f"GitHub: 新增 {len(new_items)} 个项目，跳过 {len(projects) - len(new_items)} 个已存在")
                except Exception as e:
                    logger.error(f"Error fetching GitHub projects: {e}")
                    fetch_errors.append({'source': 'GitHub', 'error': str(e)})
            
            # Anthropic Red Team
            if 'anthropic_red_fetcher' in components:
                logger.info("Step 2.1i: Fetching articles from Anthropic Red Team...")
                try:
                    result = components['anthropic_red_fetcher'].fetch()
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        all_articles.extend(new_items)
                        logger.info(f"Anthropic Red: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching Anthropic Red Team articles: {e}")
                    fetch_errors.append({'source': 'Anthropic Red', 'error': str(e)})
            
            # Atum Blog
            if 'atum_blog_fetcher' in components:
                logger.info("Step 2.1j: Fetching articles from Atum Blog...")
                try:
                    result = components['atum_blog_fetcher'].fetch()
                    if result.items:
                        new_items = [a for a in result.items if a.get('url', '') not in existing_urls]
                        all_articles.extend(new_items)
                        logger.info(f"Atum Blog: 新增 {len(new_items)} 篇，跳过 {len(result.items) - len(new_items)} 篇已存在")
                except Exception as e:
                    logger.error(f"Error fetching Atum Blog articles: {e}")
                    fetch_errors.append({'source': 'Atum Blog', 'error': str(e)})
            
            # 步骤2.2: 漏洞过滤（高级功能）
            if vulnerability_articles and 'vulnerability_filter' in components:
                logger.info("Step 2.2: Filtering vulnerabilities...")
                try:
                    vuln_filter = components['vulnerability_filter']
                    filter_results = vuln_filter.filter_vulnerabilities(vulnerability_articles)
                    
                    # 只保留通过过滤的漏洞
                    passed_vulns = [r.vulnerability for r in filter_results if r.passed]
                    filtered_count = len(vulnerability_articles) - len(passed_vulns)
                    
                    all_articles.extend(passed_vulns)
                    logger.info(f"Vulnerability filter: {len(passed_vulns)} passed, {filtered_count} filtered")
                except Exception as e:
                    logger.error(f"Error filtering vulnerabilities: {e}")
                    # 如果过滤失败，保留所有漏洞
                    all_articles.extend(vulnerability_articles)
            else:
                # 没有漏洞过滤器，直接添加所有漏洞
                all_articles.extend(vulnerability_articles)
            
            logger.info(f"Total new articles to process: {len(all_articles)}")
            
            # 步骤3: 检查数据库去重（二次确认，主要用于标题相似度去重）
            logger.info("Step 3: Checking for duplicates (title similarity)...")
            new_articles = []

            # 批量去重优化：每100篇打印进度
            batch_size = 100
            total = len(all_articles)

            for i, article in enumerate(all_articles):
                url = article.get('url', '')
                title = article.get('title', '')

                # 进度日志
                if i % batch_size == 0 or i == total - 1:
                    logger.info(f"去重进度: {i+1}/{total} ({(i+1)/total*100:.1f}%)")

                # URL去重
                if repository.exists_by_url(url):
                    logger.debug(f"Skipping duplicate URL: {url}")
                    continue

                # 标题相似度去重（已禁用：性能瓶颈）
                # similar = repository.find_similar_by_title(title)
                # if similar:
                #     logger.debug(f"Skipping similar title: {title}")
                #     continue
                # 跳过标题相似度检查以提升性能（6282篇已有文章 × 17017篇新文章 = 1.07亿次比较）
                pass

                new_articles.append(article)
            
            logger.info(f"New articles after deduplication: {len(new_articles)}")
            
            if not new_articles:
                logger.info("No new articles to process")
            else:
                # 步骤4 & 5 & 6: 处理内容、AI分析、保存到数据库（支持断点续传）
                content_processor = components.get('content_processor')
                ai_analyzer = components.get('ai_analyzer')
                
                # 初始化处理阶段检查点
                if checkpoint_manager:
                    checkpoint_manager.start_process(new_articles)
                    pending_articles = checkpoint_manager.get_pending_articles(new_articles)
                    
                    # 加载已处理的文章
                    processed_from_checkpoint = checkpoint_manager.get_processed_articles()
                    if processed_from_checkpoint:
                        logger.info(f"从检查点恢复 {len(processed_from_checkpoint)} 篇已处理文章")
                        # 这些文章已经保存到数据库了，不需要重新处理
                    
                    if not pending_articles:
                        logger.info("所有文章已在之前的运行中处理完成")
                        new_articles = []
                    else:
                        logger.info(f"待处理文章: {len(pending_articles)}/{len(new_articles)}")
                        new_articles = pending_articles
                
                processed_count = 0
                processed_lock = Lock()
                total = len(new_articles)
                
                def process_single_article(article):
                    nonlocal processed_count
                    try:
                        url = article.get('url', '')
                        title = article.get('title', '')
                        source_type = article.get('source_type', '')
                        
                        # 步骤4: 处理内容
                        if source_type == 'rss' and content_processor:
                            content = content_processor.process_article(url)
                            if content:
                                article['content'] = content
                            else:
                                article['content'] = ''
                        elif not article.get('content'):
                            content_parts = []
                            if article.get('short_description'):
                                content_parts.append(article['short_description'])
                            if article.get('description'):
                                content_parts.append(article['description'])
                            if article.get('required_action'):
                                content_parts.append(f"Required Action: {article['required_action']}")
                            if article.get('summary'):
                                content_parts.append(article['summary'])
                            
                            if content_parts:
                                article['content'] = '\n\n'.join(content_parts)
                        
                        # 步骤5: AI分析
                        if ai_analyzer and article.get('content'):
                            analysis_result = ai_analyzer.analyze_article(
                                title, 
                                article.get('content', '')
                            )
                            article['summary'] = analysis_result.get('summary', '')
                            article['category'] = analysis_result.get('category', '其他')
                            article['zh_summary'] = analysis_result.get('zh_summary', '')
                        
                        # 步骤6: 保存到数据库
                        article['fetched_at'] = datetime.now().isoformat()
                        article['is_pushed'] = False
                        
                        article_id = repository.save_article(article)
                        article['id'] = article_id
                        
                        with processed_lock:
                            nonlocal processed_count
                            processed_count += 1
                            current = processed_count
                            if current % 10 == 0 or current == total:
                                logger.info(f"处理进度: {current}/{total} ({current/total*100:.1f}%) - {title[:40]}...")
                        
                        # 标记文章处理完成
                        if checkpoint_manager:
                            checkpoint_manager.mark_article_processed(article)
                            
                        return True
                        
                    except Exception as e:
                        logger.error(f"Error processing article {article.get('title', 'unknown')}: {e}")
                        if checkpoint_manager:
                            checkpoint_manager.mark_article_failed(article.get('url', ''), str(e))
                        return False
                
                # 使用10线程并发处理
                max_workers = min(10, total)
                logger.info(f"开始并发处理 {total} 篇文章（{max_workers}线程）...")
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(process_single_article, article) for article in new_articles]
                    for future in as_completed(futures):
                        future.result()  # 等待所有任务完成
                
                # 完成处理阶段
                if checkpoint_manager:
                    checkpoint_manager.complete_process()
                    checkpoint_manager.save_process_checkpoint()
                
                logger.info(f"Processed and saved {processed_count} articles")
            
            # 步骤7: 获取未推送文章并推送到飞书
            logger.info("Step 7: Pushing articles to Feishu...")
            if 'feishu_bot' in components:
                feishu_bot = components['feishu_bot']
                unpushed_articles = repository.get_unpushed_articles()
                
                if unpushed_articles:
                    logger.info(f"Found {len(unpushed_articles)} unpushed articles")
                    
                    # 智能筛选（如果可用）
                    articles_to_push = unpushed_articles
                    if 'smart_selector' in components:
                        logger.info("Using smart selector to filter articles...")
                        smart_selector = components['smart_selector']
                        articles_to_push = smart_selector.select_articles(unpushed_articles)
                        logger.info(f"Smart selector: {len(articles_to_push)}/{len(unpushed_articles)} articles selected")
                    
                    # 使用分级推送（如果可用）
                    if 'tiered_pusher' in components and 'priority_scorer' in components:
                        logger.info("Using tiered push with priority scoring...")
                        try:
                            priority_scorer = components['priority_scorer']
                            tiered_pusher = components['tiered_pusher']
                            
                            # 评分
                            scored_articles = priority_scorer.score_articles(articles_to_push)
                            
                            # 排序
                            sorted_articles = priority_scorer.sort_by_priority(scored_articles)
                            
                            # 分级
                            tiered_articles = tiered_pusher.categorize_articles(sorted_articles)
                            
                            # 推送
                            success = tiered_pusher.push_tiered(tiered_articles)
                        except Exception as e:
                            logger.error(f"Tiered push failed, falling back to standard push: {e}")
                            success = feishu_bot.push_articles(articles_to_push)
                    else:
                        # 标准推送
                        success = feishu_bot.push_articles(articles_to_push)
                    
                    if success:
                        # 步骤8: 标记已推送的文章（只标记实际推送的）
                        article_ids = [a['id'] for a in articles_to_push if a.get('id')]
                        repository.mark_as_pushed(article_ids)
                        logger.info(f"Marked {len(article_ids)} articles as pushed")
                        
                        # 步骤9: 同步到飞书多维表格
                        if 'feishu_bitable' in components:
                            logger.info("Step 9: Syncing articles to Feishu Bitable...")
                            try:
                                bitable = components['feishu_bitable']
                                # 更新推送状态后同步
                                for article in articles_to_push:
                                    article['is_pushed'] = True
                                sync_count = bitable.batch_add_records(articles_to_push)
                                logger.info(f"Synced {sync_count} articles to Feishu Bitable")
                            except Exception as e:
                                logger.error(f"Failed to sync to Bitable: {e}")
                        
                        # 步骤10: 话题聚合与飞书文档发布
                        topic_config = self.config.get('topic_aggregation', {})
                        if topic_config.get('enabled', False):
                            logger.info("Step 10: Running topic aggregation...")
                            try:
                                self._run_topic_aggregation(articles_to_push, components)
                            except Exception as e:
                                logger.error(f"Topic aggregation failed: {e}")
                    else:
                        logger.error("Failed to push articles to Feishu")
                        # 推送失败，抛出异常以保留检查点
                        raise RuntimeError("Feishu push failed, checkpoint preserved for retry")
                else:
                    logger.info("No unpushed articles to push")
            else:
                logger.warning("FeishuBot not configured, skipping push")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"=== Task completed at {end_time.isoformat()} "
                       f"(duration: {duration:.2f}s) ===")
            
            # 推送错误汇总报告
            if fetch_errors and 'feishu_bot' in components:
                self._push_error_report(components['feishu_bot'], fetch_errors, duration)
            
            # 任务成功完成，清理检查点
            if checkpoint_manager:
                checkpoint_manager.clear_checkpoints()
                logger.info("检查点已清理")
            
        except Exception as e:
            logger.error(f"Task failed with error: {e}", exc_info=True)
            # 保存检查点以便下次恢复
            if checkpoint_manager:
                checkpoint_manager.save_fetch_checkpoint()
                checkpoint_manager.save_process_checkpoint()
                logger.info("检查点已保存，下次运行将从断点恢复")
            raise
        finally:
            # 清理资源
            if components:
                self._cleanup_components(components)
    
    def _run_topic_aggregation(
        self, 
        articles: list[dict], 
        components: dict
    ):
        """
        运行话题聚合并发布到飞书文档
        
        Args:
            articles: 文章列表
            components: 组件字典
        """
        from src.aggregation.topic_aggregation_system import TopicAggregationSystem
        from src.models import Article
        
        # 获取话题聚合配置
        topic_config = self.config.get('topic_aggregation', {})
        ai_config = self.config.get('ai', {})
        bitable_config = self.config.get('feishu_bitable', {})
        
        # 构建话题聚合系统配置
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
                'use_ai_similarity': topic_config.get('use_ai_similarity', False),
            },
            'synthesis_generator': {},
            'doc_publisher': {
                'app_id': bitable_config.get('app_id', ''),
                'app_secret': bitable_config.get('app_secret', ''),
                'folder_token': topic_config.get('folder_token', ''),
                'backup_dir': 'data/doc_backups',
            },
            'rss_generator': {
                'output_path': 'data/knowledge_feed.xml',
            },
            'ai': ai_config,
        }
        
        # 转换文章格式
        article_objects = []
        for a in articles:
            try:
                article = Article(
                    title=a.get('title', ''),
                    url=a.get('url', ''),
                    source=a.get('source', ''),
                    source_type=a.get('source_type', ''),
                    content=a.get('content', ''),
                    summary=a.get('summary', ''),
                    zh_summary=a.get('zh_summary', ''),
                    category=a.get('category', ''),
                    fetched_at=a.get('fetched_at', ''),
                )
                article_objects.append(article)
            except Exception as e:
                logger.warning(f"Failed to convert article: {e}")
        
        if not article_objects:
            logger.warning("No valid articles for topic aggregation")
            return
        
        # 运行话题聚合
        try:
            system = TopicAggregationSystem(system_config)
            result = system.run(
                article_objects,
                publish_to_feishu=True,
                generate_rss=True
            )
            
            stats = result.get('stats', {})
            logger.info(
                f"Topic aggregation completed: "
                f"clusters={stats.get('clusters_count', 0)}, "
                f"syntheses={stats.get('syntheses_count', 0)}, "
                f"published={stats.get('published_count', 0)}"
            )
            
            # 如果有综述发布成功，发送通知
            if stats.get('published_count', 0) > 0:
                publish_results = result.get('publish_results', [])
                for pr in publish_results:
                    if pr.success and pr.document_url:
                        # 发送飞书通知
                        if 'feishu_bot' in components:
                            msg = f"📄 话题综述已发布: {pr.document_url}"
                            components['feishu_bot'].send_text(msg)
                            
        except Exception as e:
            logger.error(f"Topic aggregation error: {e}", exc_info=True)
    
    def start(self):
        """
        启动定时调度
        Start scheduled execution
        
        根据配置的时间每天执行任务。
        Executes task daily at the configured time.
        
        **验证: 需求 7.1**
        """
        logger.info(f"Starting scheduler, task will run daily at {self.schedule_time}")
        
        # 清除之前的调度任务
        schedule.clear()
        
        # 设置每日定时任务
        schedule.every().day.at(self.schedule_time).do(self.run_task)
        
        self._running = True
        logger.info("Scheduler started, waiting for scheduled time...")
        
        try:
            while self._running:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            self._running = False
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            self._running = False
            raise
    
    def stop(self):
        """
        停止调度器
        Stop the scheduler
        """
        logger.info("Stopping scheduler...")
        self._running = False
        schedule.clear()
    
    def run_once(self):
        """
        手动执行一次任务
        Manually execute task once
        
        立即执行一次完整的爬取-分析-推送任务。
        Immediately executes the complete fetch-analyze-push task.
        
        **验证: 需求 7.2**
        """
        logger.info("Running task manually (once)...")
        self.run_task()
        logger.info("Manual task execution completed")
