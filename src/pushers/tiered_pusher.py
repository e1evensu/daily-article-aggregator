"""
TieredPusher - 分级推送器
TieredPusher - Tiered Article Pusher

根据文章优先级进行分级推送。
Pushes articles based on priority tiers.

需求 Requirements:
- 9.1: Level 1 (前10%) - 详细推送
- 10.1: Level 2 (10%-40%) - 简要推送
- 11.1: Level 3 (40%-100%) - 链接推送
- 12.1-12.4: 飞书分级推送格式
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PushLevel(Enum):
    """
    推送级别枚举
    Push Level Enumeration
    """
    LEVEL_1 = 1  # 详细推送（前 10%）- 重点推荐
    LEVEL_2 = 2  # 简要推送（10%-30%）- 推荐
    LEVEL_3 = 3  # 链接推送（30%-60%）- 其他
    LEVEL_4 = 4  # 不推送（后 40%）


@dataclass
class TieredArticle:
    """分级后的文章数据类"""
    article: dict[str, Any] = field(default_factory=dict)
    score: int = 0
    level: PushLevel = PushLevel.LEVEL_3


class TieredPusher:
    """分级推送器"""
    
    def __init__(
        self, 
        config: dict[str, Any], 
        feishu_bot: Any = None,
        ai_analyzer: Any = None
    ):
        self.level1_threshold: float = config.get('level1_threshold', 0.10)
        self.level2_threshold: float = config.get('level2_threshold', 0.30)
        self.level3_threshold: float = config.get('level3_threshold', 0.60)
        self.feishu_bot = feishu_bot
        self.ai_analyzer = ai_analyzer
        logger.info(f"TieredPusher initialized: L1={self.level1_threshold:.0%}, L2={self.level2_threshold:.0%}, L3={self.level3_threshold:.0%}")

    def categorize_articles(
        self,
        scored_articles: list[Any]
    ) -> dict[PushLevel, list[TieredArticle]]:
        """将文章按优先级分级"""
        result: dict[PushLevel, list[TieredArticle]] = {
            PushLevel.LEVEL_1: [],
            PushLevel.LEVEL_2: [],
            PushLevel.LEVEL_3: [],
        }

        if not scored_articles:
            return result

        n = len(scored_articles)
        level1_end = int(n * self.level1_threshold)
        level2_end = int(n * self.level2_threshold)
        level3_end = int(n * self.level3_threshold)

        push_count = 0
        skip_count = 0

        for i, scored in enumerate(scored_articles):
            article = getattr(scored, 'article', scored)
            score = getattr(scored, 'score', 0)

            # 后40%不推送
            if i >= level3_end:
                skip_count += 1
                continue

            if i < level1_end:
                level = PushLevel.LEVEL_1
            elif i < level2_end:
                level = PushLevel.LEVEL_2
            else:
                level = PushLevel.LEVEL_3

            tiered = TieredArticle(
                article=article if isinstance(article, dict) else {},
                score=score,
                level=level
            )
            result[level].append(tiered)
            push_count += 1

        logger.info(f"TieredPusher categorized {n} articles: 推送{push_count}篇(L1={len(result[PushLevel.LEVEL_1])}, L2={len(result[PushLevel.LEVEL_2])}, L3={len(result[PushLevel.LEVEL_3])}), 跳过{skip_count}篇")
        return result

    def _format_level1_article(self, tiered: TieredArticle) -> str:
        """格式化 Level 1 文章（详细）"""
        article = tiered.article
        title = article.get('title', 'Untitled')
        url = article.get('url', '')
        source = article.get('source', '')
        source_type = article.get('source_type', '')
        
        # 优先使用 zh_summary，其次 summary，最后 short_description
        summary = (
            article.get('zh_summary', '') or 
            article.get('summary', '') or 
            article.get('short_description', '')
        )
        category = article.get('category', '')
        keywords = article.get('keywords', [])
        keywords_str = ', '.join(keywords) if isinstance(keywords, list) else str(keywords) if keywords else ''
        
        lines = [f"📌 {title}"]
        if url:
            lines.append(f"🔗 {url}")
        
        # 来源信息：优先显示具体来源名称，其次显示来源类型
        if source:
            # 对于 RSS，显示具体的博客/订阅源名称
            source_display = f"[{source_type.upper()}] {source}" if source_type else source
        else:
            source_display = source_type.upper() if source_type else ""
        if source_display:
            lines.append(f"📰 来源: {source_display}")
        
        # 摘要（截断过长的摘要）
        if summary:
            if len(summary) > 500:
                summary = summary[:497] + "..."
            lines.append(f"📝 {summary}")
        
        if category:
            lines.append(f"📂 分类: {category}")
        if keywords_str:
            lines.append(f"🏷️ 关键词: {keywords_str}")
        
        return '\n'.join(lines)
    
    def _format_level2_article(self, tiered: TieredArticle) -> str:
        """格式化 Level 2 文章（简要）"""
        article = tiered.article
        title = article.get('title', 'Untitled')
        url = article.get('url', '')
        source = article.get('source', '')
        source_type = article.get('source_type', '')
        
        # 优先使用 zh_summary，其次 summary，最后 short_description
        full_summary = (
            article.get('zh_summary', '') or 
            article.get('summary', '') or 
            article.get('short_description', '')
        )
        
        # 截断摘要为简短版本
        brief_summary = full_summary[:120] + '...' if len(full_summary) > 120 else full_summary
        
        # 来源前缀：优先显示具体来源名称
        if source and source_type:
            prefix = f"[{source_type.upper()}] [{source}] "
        elif source_type:
            prefix = f"[{source_type.upper()}] "
        elif source:
            prefix = f"[{source}] "
        else:
            prefix = ""
        
        lines = [f"• {prefix}{title}"]
        if brief_summary:
            lines.append(f"  {brief_summary}")
        return '\n'.join(lines)
    
    def _format_level3_article(self, tiered: TieredArticle) -> str:
        """格式化 Level 3 文章（链接）"""
        article = tiered.article
        title = article.get('title', 'Untitled')
        source = article.get('source', '')
        source_type = article.get('source_type', '')
        
        # 来源前缀：优先显示具体来源名称
        if source and source_type:
            prefix = f"[{source_type.upper()}] [{source}] "
        elif source_type:
            prefix = f"[{source_type.upper()}] "
        elif source:
            prefix = f"[{source}] "
        else:
            prefix = ""
        
        return f"- {prefix}{title}"


    def _build_statistics_header(
        self, 
        tiered_articles: dict[PushLevel, list[TieredArticle]]
    ) -> str:
        """构建统计头部"""
        counts = []
        if tiered_articles[PushLevel.LEVEL_1]:
            counts.append(f"重点 {len(tiered_articles[PushLevel.LEVEL_1])} 篇")
        if tiered_articles[PushLevel.LEVEL_2]:
            counts.append(f"推荐 {len(tiered_articles[PushLevel.LEVEL_2])} 篇")
        if tiered_articles[PushLevel.LEVEL_3]:
            counts.append(f"其他 {len(tiered_articles[PushLevel.LEVEL_3])} 篇")
        
        total = sum(len(v) for v in tiered_articles.values())
        return f"📊 今日文章汇总 (共 {total} 篇): {', '.join(counts)}"

    def _format_tiered_message(
        self, 
        tiered_articles: dict[PushLevel, list[TieredArticle]]
    ) -> str:
        """格式化分级推送消息"""
        sections = []
        
        # 统计头部
        header = self._build_statistics_header(tiered_articles)
        sections.append(header)
        sections.append("")
        
        # Level 1 - 重点推荐
        if tiered_articles[PushLevel.LEVEL_1]:
            sections.append("🔥 【重点推荐】")
            for tiered in tiered_articles[PushLevel.LEVEL_1]:
                sections.append(self._format_level1_article(tiered))
                sections.append("")
        
        # Level 2 - 值得关注
        if tiered_articles[PushLevel.LEVEL_2]:
            sections.append("⭐ 【值得关注】")
            for tiered in tiered_articles[PushLevel.LEVEL_2]:
                sections.append(self._format_level2_article(tiered))
            sections.append("")
        
        # Level 3 - 其他文章
        if tiered_articles[PushLevel.LEVEL_3]:
            sections.append("📋 【其他文章】")
            for tiered in tiered_articles[PushLevel.LEVEL_3]:
                sections.append(self._format_level3_article(tiered))
        
        return '\n'.join(sections)

    def push_tiered(
        self, 
        tiered_articles: dict[PushLevel, list[TieredArticle]]
    ) -> bool:
        """分级推送到飞书（单条富文本消息）"""
        if not self.feishu_bot:
            logger.warning("No feishu_bot configured, skipping push")
            return False
        
        # 检查是否有文章
        total = sum(len(v) for v in tiered_articles.values())
        if total == 0:
            logger.info("No articles to push")
            return True
        
        # 构建富文本内容
        content = self._build_rich_text_content(tiered_articles)
        
        # 构建标题
        header = self._build_statistics_header(tiered_articles)
        
        # 发送单条富文本消息
        logger.info(f"Sending tiered push: {total} articles in one message")
        success = self.feishu_bot.send_rich_text(header, content)
        
        if success:
            logger.info(f"Tiered push completed: {total} articles")
        else:
            logger.error("Tiered push failed")
        
        return success
    
    def _build_rich_text_content(
        self, 
        tiered_articles: dict[PushLevel, list[TieredArticle]]
    ) -> list:
        """构建富文本消息内容"""
        content = []
        
        # Level 1 - 重点推荐
        level1_articles = tiered_articles.get(PushLevel.LEVEL_1, [])
        if level1_articles:
            content.append([{"tag": "text", "text": "🔥 【重点推荐】"}])
            content.append([{"tag": "text", "text": ""}])
            
            for tiered in level1_articles:
                article = tiered.article
                title = article.get('title', 'Untitled')
                url = article.get('url', '')
                source = article.get('source', '')
                source_type = article.get('source_type', '')
                summary = (
                    article.get('zh_summary', '') or 
                    article.get('summary', '') or 
                    article.get('short_description', '')
                )
                category = article.get('category', '')
                
                # 标题行（带链接）
                content.append([
                    {"tag": "text", "text": "📌 "},
                    {"tag": "a", "text": title, "href": url} if url else {"tag": "text", "text": title}
                ])
                
                # 来源：优先显示具体来源名称
                if source and source_type:
                    source_display = f"[{source_type.upper()}] {source}"
                elif source_type:
                    source_display = source_type.upper()
                elif source:
                    source_display = source
                else:
                    source_display = ""
                if source_display:
                    content.append([{"tag": "text", "text": f"📰 来源: {source_display}"}])
                
                # 摘要
                if summary:
                    if len(summary) > 400:
                        summary = summary[:397] + "..."
                    content.append([{"tag": "text", "text": f"📝 {summary}"}])
                
                # 分类
                if category:
                    content.append([{"tag": "text", "text": f"📂 分类: {category}"}])
                
                content.append([{"tag": "text", "text": ""}])
        
        # Level 2 - 值得关注
        level2_articles = tiered_articles.get(PushLevel.LEVEL_2, [])
        if level2_articles:
            content.append([{"tag": "text", "text": "⭐ 【值得关注】"}])
            content.append([{"tag": "text", "text": ""}])
            
            for tiered in level2_articles:
                article = tiered.article
                title = article.get('title', 'Untitled')
                url = article.get('url', '')
                source_type = article.get('source_type', '')
                summary = (
                    article.get('zh_summary', '') or 
                    article.get('summary', '') or 
                    article.get('short_description', '')
                )
                
                # 标题行
                prefix = f"[{source_type.upper()}] " if source_type else ""
                content.append([
                    {"tag": "text", "text": f"• {prefix}"},
                    {"tag": "a", "text": title, "href": url} if url else {"tag": "text", "text": title}
                ])
                
                # 简短摘要
                if summary:
                    brief = summary[:100] + "..." if len(summary) > 100 else summary
                    content.append([{"tag": "text", "text": f"  {brief}"}])
            
            content.append([{"tag": "text", "text": ""}])
        
        # Level 3 - 其他文章
        level3_articles = tiered_articles.get(PushLevel.LEVEL_3, [])
        if level3_articles:
            content.append([{"tag": "text", "text": "📋 【其他文章】"}])
            
            for tiered in level3_articles:
                article = tiered.article
                title = article.get('title', 'Untitled')
                url = article.get('url', '')
                source_type = article.get('source_type', '')

                prefix = f"[{source_type.upper()}] " if source_type else ""
                content.append([
                    {"tag": "text", "text": f"- {prefix}"},
                    {"tag": "a", "text": title, "href": url} if url else {"tag": "text", "text": title}
                ])

        # 添加反馈提示
        content.append([{"tag": "text", "text": ""}])
        content.append([{"tag": "text", "text": "💡 反馈命令："}])
        content.append([{"tag": "text", "text": "• \"有用\" / \"没用\" - 快速反馈"}])
        content.append([{"tag": "text", "text": "• \"收藏\" - 收藏此文章"}])
        content.append([{"tag": "text", "text": "• \"更多类似\" - 推荐更多同类文章"}])

        return content

    def push_articles(self, articles: list[dict[str, Any]]) -> bool:
        """
        便捷方法：直接推送文章列表
        
        Args:
            articles: 文章列表（字典格式）
        
        Returns:
            是否推送成功
        """
        if not articles:
            logger.info("No articles to push")
            return True
        
        # 创建简单的评分对象
        class SimpleScoredArticle:
            def __init__(self, article: dict, score: int):
                self.article = article
                self.score = score
        
        # 按来源类型排序，优先级：kev > nvd > dblp > arxiv > huggingface > pwc > blog > rss
        source_priority = {
            'kev': 0,
            'nvd': 1,
            'dblp': 2,
            'arxiv': 3,
            'huggingface': 4,
            'pwc': 5,
            'blog': 6,
            'rss': 7,
        }
        
        def get_priority(article: dict) -> int:
            source_type = article.get('source_type', 'rss')
            return source_priority.get(source_type, 99)
        
        # 排序：先按来源优先级，再按是否有摘要
        sorted_articles = sorted(
            articles,
            key=lambda a: (
                get_priority(a),
                0 if (a.get('zh_summary') or a.get('summary')) else 1
            )
        )
        
        # 创建评分对象
        scored = [
            SimpleScoredArticle(a, 100 - i)  # 排名越前分数越高
            for i, a in enumerate(sorted_articles)
        ]
        
        # 分级
        tiered = self.categorize_articles(scored)
        
        # 推送
        return self.push_tiered(tiered)


# 独立函数用于属性测试
def categorize_by_position(
    articles: list[dict[str, Any]],
    level1_threshold: float = 0.10,
    level2_threshold: float = 0.40
) -> dict[PushLevel, list[TieredArticle]]:
    """根据位置对文章进行分级（独立函数，用于属性测试）"""
    pusher = TieredPusher({
        'level1_threshold': level1_threshold,
        'level2_threshold': level2_threshold
    })
    
    class SimpleScoredArticle:
        def __init__(self, article: dict, score: int):
            self.article = article
            self.score = score
    
    scored = [SimpleScoredArticle(a, a.get('score', 0)) for a in articles]
    return pusher.categorize_articles(scored)


def format_article_by_level(article: dict[str, Any], level: PushLevel) -> str:
    """根据级别格式化文章（独立函数，用于属性测试）"""
    pusher = TieredPusher({})
    tiered = TieredArticle(article=article, score=50, level=level)
    
    if level == PushLevel.LEVEL_1:
        return pusher._format_level1_article(tiered)
    elif level == PushLevel.LEVEL_2:
        return pusher._format_level2_article(tiered)
    else:
        return pusher._format_level3_article(tiered)


def format_tiered_message(tiered_articles: dict[PushLevel, list[TieredArticle]]) -> str:
    """格式化分级消息（独立函数，用于属性测试）"""
    pusher = TieredPusher({})
    return pusher._format_tiered_message(tiered_articles)
