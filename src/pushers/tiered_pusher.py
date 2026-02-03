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
    LEVEL_1 = 1  # 详细推送（前 10%）
    LEVEL_2 = 2  # 简要推送（10%-40%）
    LEVEL_3 = 3  # 链接推送（40%-100%）


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
        self.level2_threshold: float = config.get('level2_threshold', 0.40)
        self.feishu_bot = feishu_bot
        self.ai_analyzer = ai_analyzer
        logger.info(f"TieredPusher initialized: L1={self.level1_threshold:.0%}, L2={self.level2_threshold:.0%}")

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
        
        for i, scored in enumerate(scored_articles):
            article = getattr(scored, 'article', scored)
            score = getattr(scored, 'score', 0)
            
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
        
        logger.info(f"TieredPusher categorized {n} articles: L1={len(result[PushLevel.LEVEL_1])}, L2={len(result[PushLevel.LEVEL_2])}, L3={len(result[PushLevel.LEVEL_3])}")
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
        
        # 截断过长的标题
        if len(title) > 100:
            title = title[:97] + "..."
        
        lines = [f"📌 {title}"]
        if url:
            lines.append(f"   🔗 {url}")
        
        # 来源信息
        source_info = source_type.upper() if source_type else source
        if source_info:
            lines.append(f"   📰 来源: {source_info}")
        
        # 摘要（截断过长的摘要）
        if summary:
            if len(summary) > 300:
                summary = summary[:297] + "..."
            lines.append(f"   📝 摘要: {summary}")
        
        if category:
            lines.append(f"   📂 分类: {category}")
        if keywords_str:
            lines.append(f"   🏷️ 关键词: {keywords_str}")
        
        return '\n'.join(lines)
    
    def _format_level2_article(self, tiered: TieredArticle) -> str:
        """格式化 Level 2 文章（简要）"""
        article = tiered.article
        title = article.get('title', 'Untitled')
        url = article.get('url', '')
        source_type = article.get('source_type', '')
        
        # 优先使用 zh_summary，其次 summary，最后 short_description
        full_summary = (
            article.get('zh_summary', '') or 
            article.get('summary', '') or 
            article.get('short_description', '')
        )
        
        # 截断摘要为简短版本
        brief_summary = full_summary[:80] + '...' if len(full_summary) > 80 else full_summary
        
        # 截断过长的标题
        if len(title) > 80:
            title = title[:77] + "..."
        
        lines = [f"• [{source_type.upper()}] {title}" if source_type else f"• {title}"]
        if url:
            lines.append(f"  {url}")
        if brief_summary:
            lines.append(f"  {brief_summary}")
        return '\n'.join(lines)
    
    def _format_level3_article(self, tiered: TieredArticle) -> str:
        """格式化 Level 3 文章（链接）"""
        article = tiered.article
        title = article.get('title', 'Untitled')
        url = article.get('url', '')
        source_type = article.get('source_type', '')
        
        # 截断过长的标题
        if len(title) > 60:
            title = title[:57] + "..."
        
        prefix = f"[{source_type.upper()}] " if source_type else ""
        return f"- {prefix}{title}: {url}" if url else f"- {prefix}{title}"


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
        """分级推送到飞书（分批发送避免消息过长）"""
        if not self.feishu_bot:
            logger.warning("No feishu_bot configured, skipping push")
            return False
        
        # 检查是否有文章
        total = sum(len(v) for v in tiered_articles.values())
        if total == 0:
            logger.info("No articles to push")
            return True
        
        import time
        all_success = True
        
        # 先发送统计头部
        header = self._build_statistics_header(tiered_articles)
        logger.info(f"Sending header: {header}")
        if not self.feishu_bot.send_text(header):
            logger.warning("Failed to send statistics header")
        
        time.sleep(0.5)
        
        # Level 1 - 重点推荐（每篇单独发送，包含详细信息）
        level1_articles = tiered_articles.get(PushLevel.LEVEL_1, [])
        if level1_articles:
            logger.info(f"Pushing {len(level1_articles)} Level 1 articles (detailed with summary)")
            
            # 发送标题
            self.feishu_bot.send_text("🔥 【重点推荐】")
            time.sleep(0.3)
            
            for i, tiered in enumerate(level1_articles, 1):
                msg = self._format_level1_article(tiered)
                logger.debug(f"Level 1 article {i}: {msg[:100]}...")
                if not self.feishu_bot.send_text(msg):
                    all_success = False
                time.sleep(0.5)
        
        # Level 2 - 值得关注（分批发送，每批5篇）
        level2_articles = tiered_articles.get(PushLevel.LEVEL_2, [])
        if level2_articles:
            logger.info(f"Pushing {len(level2_articles)} Level 2 articles (brief with short summary)")
            
            self.feishu_bot.send_text("⭐ 【值得关注】")
            time.sleep(0.3)
            
            batch_size = 5
            for i in range(0, len(level2_articles), batch_size):
                batch = level2_articles[i:i + batch_size]
                lines = [self._format_level2_article(t) for t in batch]
                msg = '\n\n'.join(lines)
                if not self.feishu_bot.send_text(msg):
                    all_success = False
                time.sleep(0.5)
        
        # Level 3 - 其他文章（分批发送，每批10篇，只发链接）
        level3_articles = tiered_articles.get(PushLevel.LEVEL_3, [])
        if level3_articles:
            logger.info(f"Pushing {len(level3_articles)} Level 3 articles (links only)")
            
            self.feishu_bot.send_text("📋 【其他文章】")
            time.sleep(0.3)
            
            batch_size = 10
            for i in range(0, len(level3_articles), batch_size):
                batch = level3_articles[i:i + batch_size]
                lines = [self._format_level3_article(t) for t in batch]
                msg = '\n'.join(lines)
                if not self.feishu_bot.send_text(msg):
                    all_success = False
                time.sleep(0.5)
        
        logger.info(f"Tiered push completed: {total} articles, success={all_success}")
        return all_success


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
