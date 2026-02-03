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

import schedule

from src.config import load_config, get_config_value
from src.fetchers.arxiv_fetcher import ArxivFetcher
from src.fetchers.rss_fetcher import RSSFetcher
from src.processors.content_processor import ContentProcessor
from src.analyzers.ai_analyzer import AIAnalyzer
from src.repository import ArticleRepository
from src.bots.feishu_bot import FeishuBot

# Import new fetchers and components
try:
    from src.fetchers.dblp_fetcher import DBLPFetcher
    from src.fetchers.nvd_fetcher import NVDFetcher
    from src.fetchers.kev_fetcher import KEVFetcher
    from src.fetchers.huggingface_fetcher import HuggingFaceFetcher
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
        webhook_url = feishu_config.get('webhook_url', '')
        if webhook_url:
            proxy_url = None
            proxy_config = self.config.get('proxy', {})
            if proxy_config.get('enabled', False):
                proxy_url = proxy_config.get('url')
            components['feishu_bot'] = FeishuBot(webhook_url, proxy=proxy_url)
            logger.info("FeishuBot initialized")
        else:
            logger.warning("Feishu webhook_url not configured, push will be skipped")
        
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
        
        # 飞书多维表格（用于数据可视化）
        if BITABLE_AVAILABLE:
            bitable_config = self.config.get('feishu_bitable', {})
            if bitable_config.get('enabled', False) and bitable_config.get('app_id'):
                try:
                    components['feishu_bitable'] = FeishuBitable(bitable_config)
                    logger.info("FeishuBitable initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize FeishuBitable: {e}")
        
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
            
            # 步骤1: 从arXiv获取论文
            if 'arxiv_fetcher' in components:
                logger.info("Step 1: Fetching papers from arXiv...")
                try:
                    arxiv_fetcher = components['arxiv_fetcher']
                    papers = arxiv_fetcher.fetch_papers()
                    
                    # 应用关键词过滤
                    if arxiv_fetcher.keywords:
                        papers = arxiv_fetcher.filter_by_keywords(papers)
                    
                    logger.info(f"Fetched {len(papers)} papers from arXiv")
                    all_articles.extend(papers)
                except Exception as e:
                    logger.error(f"Error fetching arXiv papers: {e}")
            
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
                            
                            # 先加载已抓取的文章
                            existing_articles = checkpoint_manager.get_all_fetched_articles()
                            if existing_articles:
                                all_articles.extend(existing_articles)
                                logger.info(f"从检查点恢复 {len(existing_articles)} 篇已抓取文章")
                            
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
                                
                                # 合并新抓取的文章
                                for feed_name, articles in feeds_result.items():
                                    all_articles.extend(articles)
                                
                                # 保存最终检查点
                                checkpoint_manager.save_fetch_checkpoint()
                            else:
                                logger.info("所有订阅源已在之前的运行中完成")
                            
                            checkpoint_manager.complete_fetch()
                        else:
                            # 不使用断点续传，直接抓取
                            feeds_result = rss_fetcher.fetch_all_feeds(all_urls)
                            for feed_name, articles in feeds_result.items():
                                all_articles.extend(articles)
                        
                        logger.info(f"RSS抓取完成，共 {len(all_articles)} 篇文章")
                    else:
                        logger.warning(f"OPML file not found: {opml_path}")
                except Exception as e:
                    logger.error(f"Error fetching RSS articles: {e}")
                    # 保存检查点以便下次恢复
                    if checkpoint_manager:
                        checkpoint_manager.save_fetch_checkpoint()
            
            # 步骤2.1: 从新数据源获取文章（高级功能）
            vulnerability_articles = []  # 漏洞类文章单独处理
            
            # DBLP - 安全四大顶会
            if 'dblp_fetcher' in components:
                logger.info("Step 2.1a: Fetching papers from DBLP...")
                try:
                    result = components['dblp_fetcher'].fetch()
                    if result.items:
                        all_articles.extend(result.items)
                        logger.info(f"Fetched {len(result.items)} papers from DBLP")
                except Exception as e:
                    logger.error(f"Error fetching DBLP papers: {e}")
            
            # NVD - 漏洞数据库
            if 'nvd_fetcher' in components:
                logger.info("Step 2.1b: Fetching CVEs from NVD...")
                try:
                    result = components['nvd_fetcher'].fetch()
                    if result.items:
                        vulnerability_articles.extend(result.items)
                        logger.info(f"Fetched {len(result.items)} CVEs from NVD")
                except Exception as e:
                    logger.error(f"Error fetching NVD CVEs: {e}")
            
            # KEV - CISA 在野利用漏洞
            if 'kev_fetcher' in components:
                logger.info("Step 2.1c: Fetching KEV entries from CISA...")
                try:
                    result = components['kev_fetcher'].fetch()
                    if result.items:
                        vulnerability_articles.extend(result.items)
                        logger.info(f"Fetched {len(result.items)} KEV entries from CISA")
                except Exception as e:
                    logger.error(f"Error fetching KEV entries: {e}")
            
            # HuggingFace Papers
            if 'huggingface_fetcher' in components:
                logger.info("Step 2.1d: Fetching papers from HuggingFace...")
                try:
                    result = components['huggingface_fetcher'].fetch()
                    if result.items:
                        all_articles.extend(result.items)
                        logger.info(f"Fetched {len(result.items)} papers from HuggingFace")
                except Exception as e:
                    logger.error(f"Error fetching HuggingFace papers: {e}")
            
            # Papers With Code
            if 'pwc_fetcher' in components:
                logger.info("Step 2.1e: Fetching papers from Papers With Code...")
                try:
                    result = components['pwc_fetcher'].fetch()
                    if result.items:
                        all_articles.extend(result.items)
                        logger.info(f"Fetched {len(result.items)} papers from PWC")
                except Exception as e:
                    logger.error(f"Error fetching PWC papers: {e}")
            
            # 大厂博客
            if 'blog_fetcher' in components:
                logger.info("Step 2.1f: Fetching articles from tech blogs...")
                try:
                    result = components['blog_fetcher'].fetch()
                    if result.items:
                        all_articles.extend(result.items)
                        logger.info(f"Fetched {len(result.items)} articles from blogs")
                except Exception as e:
                    logger.error(f"Error fetching blog articles: {e}")
            
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
            
            logger.info(f"Total articles fetched: {len(all_articles)}")
            
            # 步骤3: 检查数据库去重
            logger.info("Step 3: Checking for duplicates...")
            new_articles = []
            for article in all_articles:
                url = article.get('url', '')
                title = article.get('title', '')
                
                # URL去重
                if repository.exists_by_url(url):
                    logger.debug(f"Skipping duplicate URL: {url}")
                    continue
                
                # 标题相似度去重
                similar = repository.find_similar_by_title(title)
                if similar:
                    logger.debug(f"Skipping similar title: {title}")
                    continue
                
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
                for article in new_articles:
                    try:
                        url = article.get('url', '')
                        title = article.get('title', '')
                        source_type = article.get('source_type', '')
                        
                        logger.info(f"Processing article: {title[:50]}...")
                        
                        # 步骤4: 处理内容（对于RSS文章获取完整内容）
                        # arXiv论文已经有摘要作为content，不需要额外获取
                        if source_type == 'rss' and content_processor:
                            content = content_processor.process_article(url)
                            if content:
                                article['content'] = content
                            else:
                                logger.warning(f"Failed to fetch content for: {url}")
                                # 使用空内容继续处理
                                article['content'] = ''
                        
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
                        
                        try:
                            article_id = repository.save_article(article)
                            article['id'] = article_id
                            processed_count += 1
                            logger.info(f"Saved article with id={article_id}: {title[:50]}...")
                            
                            # 标记文章处理完成（断点续传）
                            if checkpoint_manager:
                                checkpoint_manager.mark_article_processed(article)
                                
                        except Exception as e:
                            logger.error(f"Error saving article: {e}")
                            if checkpoint_manager:
                                checkpoint_manager.mark_article_failed(url, str(e))
                            
                    except Exception as e:
                        logger.error(f"Error processing article {article.get('title', 'unknown')}: {e}")
                        if checkpoint_manager:
                            checkpoint_manager.mark_article_failed(article.get('url', ''), str(e))
                        continue
                
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
                    
                    # 使用分级推送（如果可用）
                    if 'tiered_pusher' in components and 'priority_scorer' in components:
                        logger.info("Using tiered push with priority scoring...")
                        try:
                            priority_scorer = components['priority_scorer']
                            tiered_pusher = components['tiered_pusher']
                            
                            # 评分
                            scored_articles = priority_scorer.score_articles(unpushed_articles)
                            
                            # 排序
                            sorted_articles = priority_scorer.sort_by_priority(scored_articles)
                            
                            # 分级
                            tiered_articles = tiered_pusher.categorize_articles(sorted_articles)
                            
                            # 推送
                            success = tiered_pusher.push_tiered(tiered_articles)
                        except Exception as e:
                            logger.error(f"Tiered push failed, falling back to standard push: {e}")
                            success = feishu_bot.push_articles(unpushed_articles)
                    else:
                        # 标准推送
                        success = feishu_bot.push_articles(unpushed_articles)
                    
                    if success:
                        # 步骤8: 标记文章为已推送
                        article_ids = [a['id'] for a in unpushed_articles if a.get('id')]
                        repository.mark_as_pushed(article_ids)
                        logger.info(f"Marked {len(article_ids)} articles as pushed")
                        
                        # 步骤9: 同步到飞书多维表格
                        if 'feishu_bitable' in components:
                            logger.info("Step 9: Syncing articles to Feishu Bitable...")
                            try:
                                bitable = components['feishu_bitable']
                                # 更新推送状态后同步
                                for article in unpushed_articles:
                                    article['is_pushed'] = True
                                sync_count = bitable.batch_add_records(unpushed_articles)
                                logger.info(f"Synced {sync_count} articles to Feishu Bitable")
                            except Exception as e:
                                logger.error(f"Failed to sync to Bitable: {e}")
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
