"""
RSSEvaluator - RSS源质量评估器
RSS Feed Quality Evaluator

评估RSS订阅源的质量，包括活跃度检查、原创性评估、技术深度评估等。
Evaluates RSS feed quality including activity check, originality assessment, 
technical depth evaluation, etc.

需求 Requirements:
- 9.1: 检查RSS源最后更新时间
- 9.2: 标记超过6个月未更新的源为不活跃
- 9.3: 获取最近3篇文章进行评估
- 9.4: 使用AI评估文章原创性
- 9.5: 使用AI评估技术深度
- 9.6: 计算综合质量评分
- 9.7: 生成技术分类标签
- 9.8: 生成评估报告和筛选后的OPML
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import feedparser

logger = logging.getLogger(__name__)


# AI评估提示词模板
ORIGINALITY_PROMPT = """请评估以下文章内容的原创性。

文章内容：
{content}

请判断这篇文章是否为原创内容（而非转载、翻译或聚合内容）。
请按以下格式回复：
原创性: [是/否]
评分: [0.0-1.0之间的数字，1.0表示完全原创]
理由: [简短说明]"""

TECHNICAL_DEPTH_PROMPT = """请评估以下技术文章的技术深度。

标题：{title}

内容：
{content}

请评估这篇文章的技术含金量，考虑以下因素：
- 是否包含深入的技术细节
- 是否有代码示例或技术实现
- 是否讨论了技术原理或架构设计
- 是否对读者有实际的技术价值

请只回复以下三个选项之一：high、medium、low"""

CATEGORIZE_PROMPT = """请根据以下文章列表，为这个RSS订阅源生成技术分类标签。

文章列表：
{articles}

请生成2-4个最能代表这个订阅源内容方向的技术分类标签。
可选分类包括但不限于：
- AI/机器学习
- 安全/隐私
- 系统/架构
- 编程语言
- 数据库/存储
- 网络/分布式
- 前端/移动端
- DevOps/云计算
- 开源项目
- 技术管理

请只输出分类标签，用逗号分隔，例如：AI/机器学习, 系统/架构"""


@dataclass
class FeedEvaluation:
    """
    RSS源评估结果
    RSS Feed Evaluation Result
    
    存储单个RSS订阅源的完整评估结果。
    Stores complete evaluation result for a single RSS feed.
    
    Attributes:
        url: 订阅源URL
        name: 订阅源名称
        last_updated: 最后更新时间（ISO格式字符串）
        is_active: 是否活跃（6个月内有更新）
        quality_score: 质量评分 (0-1)
        originality_score: 原创性评分 (0-1)
        technical_depth: 技术深度：high/medium/low
        categories: 技术分类标签列表
        recommendation: 推荐操作：keep/remove/review
        sample_articles: 评估的样本文章列表
        failure_reason: 失败原因（超时、解析错误等）
    """
    url: str
    name: str
    last_updated: str = ""
    is_active: bool = True
    quality_score: float = 0.0
    originality_score: float = 0.0
    technical_depth: str = "medium"
    categories: list[str] = field(default_factory=list)
    recommendation: str = "review"
    sample_articles: list[dict] = field(default_factory=list)
    failure_reason: str = ""


class RSSEvaluator:
    """
    RSS源质量评估器
    RSS Feed Quality Evaluator
    
    评估RSS订阅源的质量，包括：
    - 活跃度检查（6个月内是否有更新）
    - 原创性评估（使用AI判断）
    - 技术深度评估（使用AI判断）
    - 综合质量评分
    - 技术分类标签生成
    
    Evaluates RSS feed quality including:
    - Activity check (updates within 6 months)
    - Originality assessment (using AI)
    - Technical depth evaluation (using AI)
    - Overall quality scoring
    - Technical category tagging
    
    Attributes:
        ai_analyzer: AI分析器实例
        config: 评估配置
        inactive_months: 不活跃判定的月数阈值（默认6）
        sample_count: 评估的样本文章数量（默认3）
        min_quality_score: 推荐保留的最低质量评分（默认0.6）
    """
    
    def __init__(self, ai_analyzer: Any, config: dict):
        """
        初始化评估器
        Initialize the evaluator
        
        Args:
            ai_analyzer: AI分析器实例（AIAnalyzer类型）
                        AI analyzer instance (AIAnalyzer type)
            config: 评估配置字典，可包含：
                   Evaluation config dict, may contain:
                   - inactive_months: 不活跃判定月数（默认6）
                   - sample_count: 样本文章数量（默认3）
                   - min_quality_score: 最低质量评分阈值（默认0.6）
                   - proxy: 代理URL（可选）
                   - timeout: 请求超时时间（默认30秒）
        
        Examples:
            >>> from src.analyzers.ai_analyzer import AIAnalyzer
            >>> ai_config = {'api_base': '...', 'api_key': '...', 'model': '...'}
            >>> ai_analyzer = AIAnalyzer(ai_config)
            >>> evaluator = RSSEvaluator(ai_analyzer, {'inactive_months': 6})
        """
        self.ai_analyzer = ai_analyzer
        self.config = config or {}
        
        # 配置参数
        self.inactive_months = self.config.get('inactive_months', 6)
        self.sample_count = self.config.get('sample_count', 3)
        self.min_quality_score = self.config.get('min_quality_score', 0.6)
        self.proxy = self.config.get('proxy')
        self.timeout = self.config.get('timeout', 30)
        
        logger.info(f"RSSEvaluator initialized: inactive_months={self.inactive_months}, "
                   f"sample_count={self.sample_count}")

    
    def check_feed_activity(self, url: str) -> tuple[bool, str]:
        """
        检查订阅源活跃度
        Check feed activity status
        
        获取订阅源的最后更新时间，判断是否在指定月数内有更新。
        Gets the feed's last update time and checks if updated within specified months.
        
        Args:
            url: 订阅源URL
                 Feed URL
        
        Returns:
            (是否活跃, 最后更新时间) 元组
            (is_active, last_updated) tuple
            - is_active: True如果在inactive_months内有更新
            - last_updated: ISO格式的最后更新时间字符串，无法获取时为空字符串
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> is_active, last_updated = evaluator.check_feed_activity(
            ...     'https://example.com/feed.xml'
            ... )
            >>> isinstance(is_active, bool)
            True
        
        **验证: 需求 9.1, 9.2**
        """
        try:
            feed = feedparser.parse(url)
            
            # 检查解析错误
            if feed.bozo and not feed.entries:
                logger.warning(f"无法解析订阅源 {url}: {feed.bozo_exception}")
                return False, ""
            
            # 获取最后更新时间
            last_updated_str = ""
            last_updated_dt = None
            
            # 尝试从feed级别获取更新时间
            if hasattr(feed.feed, 'updated_parsed') and feed.feed.updated_parsed:
                last_updated_dt = datetime(*feed.feed.updated_parsed[:6])
            elif hasattr(feed.feed, 'published_parsed') and feed.feed.published_parsed:
                last_updated_dt = datetime(*feed.feed.published_parsed[:6])
            
            # 如果feed级别没有，从最新条目获取
            if last_updated_dt is None and feed.entries:
                for entry in feed.entries:
                    entry_dt = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        entry_dt = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        entry_dt = datetime(*entry.updated_parsed[:6])
                    
                    if entry_dt:
                        if last_updated_dt is None or entry_dt > last_updated_dt:
                            last_updated_dt = entry_dt
            
            # 格式化最后更新时间
            if last_updated_dt:
                last_updated_str = last_updated_dt.strftime("%Y-%m-%d")
                
                # 计算是否活跃（在指定月数内有更新）
                cutoff_date = datetime.now() - timedelta(days=self.inactive_months * 30)
                is_active = last_updated_dt >= cutoff_date
                
                logger.info(f"订阅源 {url} 最后更新: {last_updated_str}, 活跃: {is_active}")
                return is_active, last_updated_str
            
            # 无法获取更新时间，默认为不活跃
            logger.warning(f"无法获取订阅源 {url} 的更新时间")
            return False, ""
            
        except Exception as e:
            logger.error(f"检查订阅源活跃度失败 {url}: {e}")
            return False, ""

    
    def fetch_recent_articles(self, url: str, count: int = 3) -> list[dict]:
        """
        获取最近的文章
        Fetch recent articles from feed
        
        从订阅源获取最近的N篇文章，用于质量评估。
        Fetches the most recent N articles from feed for quality evaluation.
        
        Args:
            url: 订阅源URL
                 Feed URL
            count: 获取数量（默认3）
                   Number of articles to fetch (default 3)
        
        Returns:
            文章列表，每篇文章包含title, url, content, published_date
            List of articles, each containing title, url, content, published_date
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> articles = evaluator.fetch_recent_articles(
            ...     'https://example.com/feed.xml', count=3
            ... )
            >>> len(articles) <= 3
            True
        
        **验证: 需求 9.3**
        """
        try:
            feed = feedparser.parse(url)
            
            if feed.bozo and not feed.entries:
                logger.warning(f"无法解析订阅源 {url}")
                return []
            
            articles = []
            
            for entry in feed.entries[:count]:
                article = {
                    'title': entry.get('title', '').strip(),
                    'url': entry.get('link', '').strip(),
                    'content': '',
                    'published_date': ''
                }
                
                # 跳过没有标题或URL的条目
                if not article['title'] or not article['url']:
                    continue
                
                # 获取内容（优先使用content，其次summary）
                if hasattr(entry, 'content') and entry.content:
                    article['content'] = entry.content[0].get('value', '')
                elif hasattr(entry, 'summary') and entry.summary:
                    article['content'] = entry.summary
                elif hasattr(entry, 'description') and entry.description:
                    article['content'] = entry.description
                
                # 获取发布日期
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        dt = datetime(*entry.published_parsed[:6])
                        article['published_date'] = dt.strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass
                
                articles.append(article)
            
            logger.info(f"从订阅源 {url} 获取了 {len(articles)} 篇文章")
            return articles
            
        except Exception as e:
            logger.error(f"获取文章失败 {url}: {e}")
            return []

    
    def evaluate_originality(self, content: str) -> tuple[bool, float]:
        """
        评估文章原创性
        Evaluate article originality
        
        使用AI判断文章是否为原创内容，并给出原创性评分。
        Uses AI to determine if article is original content and provides originality score.
        
        Args:
            content: 文章内容
                     Article content
        
        Returns:
            (是否原创, 原创性评分) 元组
            (is_original, originality_score) tuple
            - is_original: True如果判定为原创
            - originality_score: 0.0-1.0之间的评分
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> is_original, score = evaluator.evaluate_originality(
            ...     "这是一篇关于深度学习的原创文章..."
            ... )
            >>> 0.0 <= score <= 1.0
            True
        
        **验证: 需求 9.4**
        """
        if not content or not content.strip():
            logger.warning("内容为空，无法评估原创性")
            return False, 0.0
        
        # 截断过长的内容
        max_content_length = 3000
        truncated_content = content[:max_content_length] if len(content) > max_content_length else content
        
        try:
            # 构建提示词
            prompt = ORIGINALITY_PROMPT.format(content=truncated_content)
            
            # 调用AI分析
            response = self.ai_analyzer._call_api(prompt)
            
            if not response:
                logger.warning("AI原创性评估返回空结果")
                return True, 0.5  # 默认中等评分
            
            # 解析响应
            is_original = True
            score = 0.5
            
            response_lower = response.lower()
            
            # 解析原创性判断
            if '原创性: 否' in response or '原创性:否' in response:
                is_original = False
            elif '原创性: 是' in response or '原创性:是' in response:
                is_original = True
            
            # 解析评分
            import re
            score_match = re.search(r'评分[：:]\s*([0-9.]+)', response)
            if score_match:
                try:
                    parsed_score = float(score_match.group(1))
                    if 0.0 <= parsed_score <= 1.0:
                        score = parsed_score
                except ValueError:
                    pass
            
            logger.info(f"原创性评估: is_original={is_original}, score={score}")
            return is_original, score
            
        except Exception as e:
            logger.error(f"原创性评估失败: {e}")
            return True, 0.5  # 出错时返回默认值

    
    def evaluate_technical_depth(self, title: str, content: str) -> str:
        """
        评估技术含金量
        Evaluate technical depth
        
        使用AI评估文章的技术深度，返回high/medium/low。
        Uses AI to evaluate article's technical depth, returns high/medium/low.
        
        Args:
            title: 文章标题
                   Article title
            content: 文章内容
                     Article content
        
        Returns:
            技术深度：high/medium/low
            Technical depth: high/medium/low
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> depth = evaluator.evaluate_technical_depth(
            ...     "深入理解Transformer架构",
            ...     "本文详细介绍了Transformer的注意力机制..."
            ... )
            >>> depth in ['high', 'medium', 'low']
            True
        
        **验证: 需求 9.5**
        """
        if not title and not content:
            logger.warning("标题和内容都为空，无法评估技术深度")
            return "low"
        
        # 截断过长的内容
        max_content_length = 3000
        truncated_content = content[:max_content_length] if content and len(content) > max_content_length else (content or "")
        
        try:
            # 构建提示词
            prompt = TECHNICAL_DEPTH_PROMPT.format(title=title or "", content=truncated_content)
            
            # 调用AI分析
            response = self.ai_analyzer._call_api(prompt)
            
            if not response:
                logger.warning("AI技术深度评估返回空结果")
                return "medium"  # 默认中等
            
            # 解析响应
            response_lower = response.lower().strip()
            
            if 'high' in response_lower:
                return "high"
            elif 'low' in response_lower:
                return "low"
            else:
                return "medium"
            
        except Exception as e:
            logger.error(f"技术深度评估失败: {e}")
            return "medium"  # 出错时返回默认值

    
    def categorize_feed(self, articles: list[dict]) -> list[str]:
        """
        为订阅源生成技术分类
        Generate technical categories for feed
        
        根据文章列表，使用AI生成订阅源的技术分类标签。
        Based on article list, uses AI to generate technical category tags for the feed.
        
        Args:
            articles: 文章列表，每篇包含title和content
                      List of articles, each containing title and content
        
        Returns:
            分类标签列表
            List of category tags
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> categories = evaluator.categorize_feed([
            ...     {'title': 'AI入门', 'content': '...'},
            ...     {'title': '机器学习实践', 'content': '...'}
            ... ])
            >>> isinstance(categories, list)
            True
        
        **验证: 需求 9.7**
        """
        if not articles:
            logger.warning("文章列表为空，无法生成分类")
            return ["其他"]
        
        try:
            # 构建文章摘要列表
            articles_text = ""
            for i, article in enumerate(articles[:5], 1):  # 最多使用5篇文章
                title = article.get('title', '')
                content = article.get('content', '')[:500]  # 截断内容
                articles_text += f"{i}. 标题: {title}\n   内容摘要: {content[:200]}...\n\n"
            
            # 构建提示词
            prompt = CATEGORIZE_PROMPT.format(articles=articles_text)
            
            # 调用AI分析
            response = self.ai_analyzer._call_api(prompt)
            
            if not response:
                logger.warning("AI分类生成返回空结果")
                return ["其他"]
            
            # 解析响应（逗号分隔的标签）
            categories = [cat.strip() for cat in response.split(',') if cat.strip()]
            
            if not categories:
                return ["其他"]
            
            logger.info(f"生成分类标签: {categories}")
            return categories[:4]  # 最多返回4个标签
            
        except Exception as e:
            logger.error(f"分类生成失败: {e}")
            return ["其他"]

    
    def _calculate_quality_score(self, is_active: bool, originality_score: float, 
                                  technical_depth: str) -> float:
        """
        计算综合质量评分
        Calculate overall quality score
        
        根据活跃度、原创性和技术深度计算综合评分。
        Calculates overall score based on activity, originality, and technical depth.
        
        Args:
            is_active: 是否活跃
            originality_score: 原创性评分 (0-1)
            technical_depth: 技术深度 (high/medium/low)
        
        Returns:
            综合质量评分 (0-1)
        
        **验证: 需求 9.6**
        """
        # 活跃度权重：30%
        activity_score = 1.0 if is_active else 0.0
        
        # 原创性权重：40%
        # originality_score 已经是 0-1
        
        # 技术深度权重：30%
        depth_scores = {'high': 1.0, 'medium': 0.6, 'low': 0.2}
        depth_score = depth_scores.get(technical_depth, 0.6)
        
        # 加权计算
        quality_score = (
            activity_score * 0.3 +
            originality_score * 0.4 +
            depth_score * 0.3
        )
        
        return round(quality_score, 2)
    
    def _determine_recommendation(self, is_active: bool, quality_score: float) -> str:
        """
        确定推荐操作
        Determine recommendation action
        
        根据活跃度和质量评分确定推荐操作。
        Determines recommendation based on activity and quality score.
        
        Args:
            is_active: 是否活跃
            quality_score: 质量评分
        
        Returns:
            推荐操作：keep/remove/review
        """
        if not is_active:
            return "remove"
        
        if quality_score >= self.min_quality_score:
            return "keep"
        elif quality_score >= self.min_quality_score - 0.2:
            return "review"
        else:
            return "remove"

    
    def evaluate_feed(self, url: str) -> FeedEvaluation:
        """
        完整评估单个订阅源
        Complete evaluation of a single feed
        
        执行完整的评估流程：
        1. 检查活跃度
        2. 获取最近文章
        3. 评估原创性
        4. 评估技术深度
        5. 生成分类标签
        6. 计算综合评分
        7. 确定推荐操作
        
        Performs complete evaluation workflow:
        1. Check activity
        2. Fetch recent articles
        3. Evaluate originality
        4. Evaluate technical depth
        5. Generate category tags
        6. Calculate overall score
        7. Determine recommendation
        
        Args:
            url: 订阅源URL
                 Feed URL
        
        Returns:
            FeedEvaluation评估结果
            FeedEvaluation result
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> result = evaluator.evaluate_feed('https://example.com/feed.xml')
            >>> isinstance(result, FeedEvaluation)
            True
        
        **验证: 需求 9.1-9.7**
        """
        logger.info(f"开始评估订阅源: {url}")
        
        # 获取订阅源名称
        try:
            feed = feedparser.parse(url)
            feed_name = feed.feed.get('title', url)
        except Exception:
            feed_name = url
        
        # 1. 检查活跃度
        is_active, last_updated = self.check_feed_activity(url)
        
        # 如果不活跃，直接返回结果
        if not is_active:
            logger.info(f"订阅源 {feed_name} 不活跃，跳过详细评估")
            return FeedEvaluation(
                url=url,
                name=feed_name,
                last_updated=last_updated,
                is_active=False,
                quality_score=0.0,
                originality_score=0.0,
                technical_depth="low",
                categories=[],
                recommendation="remove",
                sample_articles=[]
            )
        
        # 2. 获取最近文章
        articles = self.fetch_recent_articles(url, count=self.sample_count)
        
        if not articles:
            logger.warning(f"订阅源 {feed_name} 无法获取文章")
            return FeedEvaluation(
                url=url,
                name=feed_name,
                last_updated=last_updated,
                is_active=is_active,
                quality_score=0.3,
                originality_score=0.5,
                technical_depth="medium",
                categories=["其他"],
                recommendation="review",
                sample_articles=[]
            )
        
        # 3. 评估原创性（使用所有样本文章的平均值）
        originality_scores = []
        for article in articles:
            content = article.get('content', '')
            if content:
                _, score = self.evaluate_originality(content)
                originality_scores.append(score)
        
        avg_originality = sum(originality_scores) / len(originality_scores) if originality_scores else 0.5
        
        # 4. 评估技术深度（使用第一篇文章）
        first_article = articles[0]
        technical_depth = self.evaluate_technical_depth(
            first_article.get('title', ''),
            first_article.get('content', '')
        )
        
        # 5. 生成分类标签
        categories = self.categorize_feed(articles)
        
        # 6. 计算综合评分
        quality_score = self._calculate_quality_score(is_active, avg_originality, technical_depth)
        
        # 7. 确定推荐操作
        recommendation = self._determine_recommendation(is_active, quality_score)
        
        # 构建样本文章列表（简化版）
        sample_articles = [
            {
                'title': a.get('title', ''),
                'url': a.get('url', ''),
                'published_date': a.get('published_date', '')
            }
            for a in articles
        ]
        
        result = FeedEvaluation(
            url=url,
            name=feed_name,
            last_updated=last_updated,
            is_active=is_active,
            quality_score=quality_score,
            originality_score=round(avg_originality, 2),
            technical_depth=technical_depth,
            categories=categories,
            recommendation=recommendation,
            sample_articles=sample_articles
        )
        
        logger.info(f"订阅源 {feed_name} 评估完成: score={quality_score}, recommendation={recommendation}")
        return result
    
    def _evaluate_feed_with_timeout(self, url: str, timeout: int = 60) -> FeedEvaluation:
        """
        带超时的单个订阅源评估
        Evaluate single feed with timeout
        
        Args:
            url: 订阅源URL
            timeout: 超时时间（秒），默认60秒
        
        Returns:
            FeedEvaluation评估结果，超时返回失败结果
        """
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.evaluate_feed, url)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.warning(f"评估订阅源超时 ({timeout}s): {url}")
                return FeedEvaluation(
                    url=url,
                    name=url,
                    is_active=False,
                    quality_score=0.0,
                    recommendation="review",
                    failure_reason=f"timeout ({timeout}s)"
                )
            except Exception as e:
                error_msg = str(e)[:100]
                logger.error(f"评估订阅源失败 {url}: {error_msg}")
                return FeedEvaluation(
                    url=url,
                    name=url,
                    is_active=False,
                    quality_score=0.0,
                    recommendation="review",
                    failure_reason=f"error: {error_msg}"
                )

    
    def evaluate_all_feeds(self, opml_path: str, checkpoint_path: str = None, 
                           concurrency: int = 5, feed_timeout: int = 60) -> list[FeedEvaluation]:
        """
        评估OPML文件中的所有订阅源（支持并发和超时）
        Evaluate all feeds in OPML file (with concurrency and timeout support)
        
        解析OPML文件并评估其中的所有订阅源。
        支持断点续传：如果提供checkpoint_path，会保存进度并支持从中断处继续。
        支持并发评估和单个源超时控制。
        
        Parses OPML file and evaluates all feeds within.
        Supports checkpoint: if checkpoint_path provided, saves progress and can resume.
        Supports concurrent evaluation and per-feed timeout.
        
        Args:
            opml_path: OPML文件路径
                       OPML file path
            checkpoint_path: 检查点文件路径（可选），用于保存进度
                            Checkpoint file path (optional), for saving progress
            concurrency: 并发数（默认5）
                        Number of concurrent workers (default 5)
            feed_timeout: 单个源评估超时时间（秒，默认60）
                         Timeout for single feed evaluation (seconds, default 60)
        
        Returns:
            所有订阅源的评估结果列表
            List of evaluation results for all feeds
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> results = evaluator.evaluate_all_feeds('feeds.opml')
            >>> isinstance(results, list)
            True
        """
        import json
        import concurrent.futures
        from pathlib import Path
        from ..fetchers.rss_fetcher import RSSFetcher
        
        # 解析OPML获取URL列表
        fetcher = RSSFetcher({'opml_path': opml_path})
        try:
            urls = fetcher.parse_opml(opml_path)
        except Exception as e:
            logger.error(f"解析OPML文件失败: {e}")
            return []
        
        logger.info(f"从OPML文件解析出 {len(urls)} 个订阅源，并发数: {concurrency}，超时: {feed_timeout}s")
        
        # 尝试加载检查点
        evaluations = []
        processed_urls = set()
        
        if checkpoint_path:
            checkpoint_file = Path(checkpoint_path)
            if checkpoint_file.exists():
                try:
                    with open(checkpoint_file, 'r', encoding='utf-8') as f:
                        checkpoint_data = json.load(f)
                    
                    # 恢复已评估的结果
                    for item in checkpoint_data.get('evaluations', []):
                        eval_obj = FeedEvaluation(
                            url=item['url'],
                            name=item['name'],
                            last_updated=item.get('last_updated', ''),
                            is_active=item.get('is_active', False),
                            quality_score=item.get('quality_score', 0.0),
                            originality_score=item.get('originality_score', 0.0),
                            technical_depth=item.get('technical_depth', 'medium'),
                            categories=item.get('categories', []),
                            recommendation=item.get('recommendation', 'review'),
                            sample_articles=item.get('sample_articles', []),
                            failure_reason=item.get('failure_reason', '')
                        )
                        evaluations.append(eval_obj)
                        processed_urls.add(item['url'])
                    
                    logger.info(f"从检查点恢复 {len(evaluations)} 个已评估的订阅源")
                except Exception as e:
                    logger.warning(f"加载检查点失败，将从头开始: {e}")
        
        # 过滤出待处理的URL
        pending_urls = [url for url in urls if url not in processed_urls]
        total = len(urls)
        processed_count = len(processed_urls)
        
        logger.info(f"待评估: {len(pending_urls)} 个，已完成: {processed_count} 个")
        
        # 使用线程池并发评估
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            # 提交所有任务
            future_to_url = {
                executor.submit(self._evaluate_feed_with_timeout, url, feed_timeout): url 
                for url in pending_urls
            }
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                processed_count += 1
                
                try:
                    evaluation = future.result()
                    evaluations.append(evaluation)
                    logger.info(f"评估进度: {processed_count}/{total} - {evaluation.name[:30]}... ({evaluation.recommendation})")
                except Exception as e:
                    logger.error(f"评估订阅源 {url} 失败: {e}")
                    evaluations.append(FeedEvaluation(
                        url=url,
                        name=url,
                        is_active=False,
                        quality_score=0.0,
                        recommendation="review"
                    ))
                
                # 每评估20个保存一次检查点
                if checkpoint_path and len(evaluations) % 20 == 0:
                    self._save_checkpoint(checkpoint_path, evaluations)
        
        # 最终保存检查点
        if checkpoint_path:
            self._save_checkpoint(checkpoint_path, evaluations)
        
        logger.info(f"完成 {len(evaluations)} 个订阅源的评估")
        return evaluations
    
    def _save_checkpoint(self, checkpoint_path: str, evaluations: list[FeedEvaluation]):
        """保存评估进度到检查点文件"""
        import json
        
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'count': len(evaluations),
            'evaluations': [
                {
                    'url': e.url,
                    'name': e.name,
                    'last_updated': e.last_updated,
                    'is_active': e.is_active,
                    'quality_score': e.quality_score,
                    'originality_score': e.originality_score,
                    'technical_depth': e.technical_depth,
                    'categories': e.categories,
                    'recommendation': e.recommendation,
                    'sample_articles': e.sample_articles,
                    'failure_reason': e.failure_reason
                }
                for e in evaluations
            ]
        }
        
        try:
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
            logger.info(f"检查点已保存: {len(evaluations)} 个评估结果")
        except Exception as e:
            logger.error(f"保存检查点失败: {e}")

    
    def generate_report(self, evaluations: list[FeedEvaluation]) -> str:
        """
        生成Markdown格式的评估报告
        Generate Markdown format evaluation report
        
        生成包含所有评估结果的详细报告，包括：
        - 总体统计
        - 推荐保留的订阅源
        - 建议移除的订阅源
        - 需要人工审核的订阅源
        
        Generates detailed report with all evaluation results including:
        - Overall statistics
        - Recommended feeds to keep
        - Suggested feeds to remove
        - Feeds requiring manual review
        
        Args:
            evaluations: 评估结果列表
                         List of evaluation results
        
        Returns:
            Markdown格式的评估报告
            Markdown format evaluation report
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> report = evaluator.generate_report(evaluations)
            >>> '# RSS订阅源评估报告' in report
            True
        
        **验证: 需求 9.8**
        """
        if not evaluations:
            return "# RSS订阅源评估报告\n\n没有评估结果。"
        
        # 统计数据
        total = len(evaluations)
        active_count = sum(1 for e in evaluations if e.is_active)
        keep_count = sum(1 for e in evaluations if e.recommendation == 'keep')
        remove_count = sum(1 for e in evaluations if e.recommendation == 'remove')
        review_count = sum(1 for e in evaluations if e.recommendation == 'review')
        avg_score = sum(e.quality_score for e in evaluations) / total if total > 0 else 0
        
        # 生成报告
        report_lines = [
            "# RSS订阅源评估报告",
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 总体统计",
            "",
            f"- 总订阅源数: {total}",
            f"- 活跃订阅源: {active_count} ({active_count/total*100:.1f}%)" if total > 0 else "- 活跃订阅源: 0",
            f"- 平均质量评分: {avg_score:.2f}",
            f"- 推荐保留: {keep_count}",
            f"- 建议移除: {remove_count}",
            f"- 需要审核: {review_count}",
            "",
        ]
        
        # 推荐保留的订阅源
        keep_feeds = [e for e in evaluations if e.recommendation == 'keep']
        if keep_feeds:
            report_lines.extend([
                "## ✅ 推荐保留",
                "",
            ])
            for e in sorted(keep_feeds, key=lambda x: x.quality_score, reverse=True):
                categories_str = ', '.join(e.categories) if e.categories else '未分类'
                report_lines.extend([
                    f"### {e.name}",
                    f"- URL: {e.url}",
                    f"- 质量评分: {e.quality_score}",
                    f"- 原创性评分: {e.originality_score}",
                    f"- 技术深度: {e.technical_depth}",
                    f"- 分类: {categories_str}",
                    f"- 最后更新: {e.last_updated}",
                    "",
                ])
        
        # 需要审核的订阅源
        review_feeds = [e for e in evaluations if e.recommendation == 'review']
        if review_feeds:
            report_lines.extend([
                "## ⚠️ 需要审核",
                "",
            ])
            # 分开显示：有失败原因的和没有的
            failed_feeds = [e for e in review_feeds if e.failure_reason]
            normal_review = [e for e in review_feeds if not e.failure_reason]
            
            if failed_feeds:
                report_lines.extend([
                    "### 评估失败（超时/错误）",
                    "",
                ])
                for e in failed_feeds:
                    report_lines.extend([
                        f"- **{e.name}**",
                        f"  - URL: {e.url}",
                        f"  - 失败原因: {e.failure_reason}",
                        "",
                    ])
            
            if normal_review:
                report_lines.extend([
                    "### 质量待定",
                    "",
                ])
                for e in sorted(normal_review, key=lambda x: x.quality_score, reverse=True):
                    categories_str = ', '.join(e.categories) if e.categories else '未分类'
                    report_lines.extend([
                        f"- **{e.name}**",
                        f"  - URL: {e.url}",
                        f"  - 质量评分: {e.quality_score}",
                        f"  - 活跃状态: {'活跃' if e.is_active else '不活跃'}",
                        f"  - 分类: {categories_str}",
                        "",
                    ])
        
        # 建议移除的订阅源
        remove_feeds = [e for e in evaluations if e.recommendation == 'remove']
        if remove_feeds:
            report_lines.extend([
                "## ❌ 建议移除",
                "",
            ])
            for e in remove_feeds:
                reason = "不活跃" if not e.is_active else f"质量评分过低 ({e.quality_score})"
                report_lines.extend([
                    f"- **{e.name}**: {reason}",
                    f"  - URL: {e.url}",
                    f"  - 最后更新: {e.last_updated or '未知'}",
                    "",
                ])
        
        return '\n'.join(report_lines)

    
    def export_filtered_opml(self, evaluations: list[FeedEvaluation], 
                              output_path: str, 
                              min_score: float = 0.6) -> int:
        """
        导出筛选后的OPML文件
        Export filtered OPML file
        
        根据质量评分筛选订阅源，导出新的OPML文件。
        Filters feeds by quality score and exports new OPML file.
        
        Args:
            evaluations: 评估结果列表
                         List of evaluation results
            output_path: 输出文件路径
                         Output file path
            min_score: 最低质量评分阈值（默认0.6）
                       Minimum quality score threshold (default 0.6)
        
        Returns:
            保留的订阅源数量
            Number of feeds kept
        
        Examples:
            >>> evaluator = RSSEvaluator(ai_analyzer, {})
            >>> count = evaluator.export_filtered_opml(
            ...     evaluations, 'filtered_feeds.opml', min_score=0.6
            ... )
            >>> count >= 0
            True
        
        **验证: 需求 9.8**
        """
        # 筛选符合条件的订阅源
        filtered_feeds = [
            e for e in evaluations 
            if e.is_active and e.quality_score >= min_score
        ]
        
        # 创建OPML结构
        opml = ET.Element('opml', version='2.0')
        
        # 添加head
        head = ET.SubElement(opml, 'head')
        title = ET.SubElement(head, 'title')
        title.text = 'Filtered RSS Feeds'
        date_created = ET.SubElement(head, 'dateCreated')
        date_created.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 添加body
        body = ET.SubElement(opml, 'body')
        
        # 按分类组织订阅源
        categories_map: dict[str, list[FeedEvaluation]] = {}
        for feed in filtered_feeds:
            # 使用第一个分类作为主分类
            main_category = feed.categories[0] if feed.categories else '其他'
            if main_category not in categories_map:
                categories_map[main_category] = []
            categories_map[main_category].append(feed)
        
        # 添加订阅源
        for category, feeds in sorted(categories_map.items()):
            # 创建分类outline
            category_outline = ET.SubElement(body, 'outline', text=category, title=category)
            
            # 添加该分类下的订阅源
            for feed in sorted(feeds, key=lambda x: x.quality_score, reverse=True):
                ET.SubElement(
                    category_outline, 
                    'outline',
                    type='rss',
                    text=feed.name,
                    title=feed.name,
                    xmlUrl=feed.url
                )
        
        # 写入文件
        tree = ET.ElementTree(opml)
        
        # 添加XML声明
        try:
            tree.write(output_path, encoding='utf-8', xml_declaration=True)
            logger.info(f"导出筛选后的OPML文件: {output_path}, 保留 {len(filtered_feeds)} 个订阅源")
        except Exception as e:
            logger.error(f"导出OPML文件失败: {e}")
            raise
        
        return len(filtered_feeds)
