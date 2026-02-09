"""
统计数据模型
Statistics Data Models

定义统计系统使用的数据类。
Defines data classes used by the statistics system.

Requirements:
- 9.1: 页面浏览事件记录
- 10.1: 问答事件记录
- 11.1: 来源质量指标
- 12.1: 话题频率统计
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PageViewEvent:
    """
    页面浏览事件
    Page View Event
    
    记录单次页面浏览，用于统计热门文章。
    Records a single page view, used for hot article statistics.
    
    Attributes:
        article_id: 文章 ID
                    Article ID
        user_id: 用户标识（可选，用于去重）
                 User identifier (optional, for deduplication)
        session_id: 会话标识（可选，用于去重）
                    Session identifier (optional, for deduplication)
        timestamp: 浏览时间
                   View timestamp
        source: 来源（如 'web', 'api', 'feishu'）
                Source (e.g., 'web', 'api', 'feishu')
    
    Examples:
        >>> event = PageViewEvent(
        ...     article_id='123',
        ...     user_id='user_456',
        ...     timestamp=datetime.now(),
        ...     source='web'
        ... )
    
    Requirements: 9.1
    """
    article_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: str | None = None
    session_id: str | None = None
    source: str = 'unknown'


@dataclass
class QAEvent:
    """
    问答事件
    QA Event
    
    记录单次问答交互，用于统计热门问题和问答质量。
    Records a single QA interaction, used for hot query and QA quality statistics.
    
    Attributes:
        query: 用户查询
               User query
        answer: 系统回答
                System answer
        user_id: 用户标识（可选）
                 User identifier (optional)
        timestamp: 问答时间
                   QA timestamp
        relevance_score: 相关性分数（0-1）
                         Relevance score (0-1)
        sources_used: 使用的来源数量
                      Number of sources used
        response_time_ms: 响应时间（毫秒）
                          Response time in milliseconds
        feedback: 用户反馈（'positive', 'negative', None）
                  User feedback ('positive', 'negative', None)
    
    Examples:
        >>> event = QAEvent(
        ...     query='什么是 RAG？',
        ...     answer='RAG 是检索增强生成...',
        ...     relevance_score=0.85,
        ...     sources_used=3,
        ...     response_time_ms=1200
        ... )
    
    Requirements: 10.1
    """
    query: str
    answer: str = ''
    user_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    relevance_score: float = 0.0
    sources_used: int = 0
    response_time_ms: int = 0
    feedback: str | None = None


@dataclass
class SourceFetchEvent:
    """
    来源抓取事件
    Source Fetch Event
    
    记录单次来源抓取，用于评估来源质量。
    Records a single source fetch, used for source quality assessment.
    
    Attributes:
        source_type: 来源类型（如 'rss', 'arxiv', 'github'）
                     Source type (e.g., 'rss', 'arxiv', 'github')
        source_url: 来源 URL
                    Source URL
        timestamp: 抓取时间
                   Fetch timestamp
        success: 是否成功
                 Whether successful
        articles_count: 抓取的文章数量
                        Number of articles fetched
        content_length: 内容总长度（字符）
                        Total content length (characters)
        response_time_ms: 响应时间（毫秒）
                          Response time in milliseconds
        error_message: 错误信息（如果失败）
                       Error message (if failed)
    
    Examples:
        >>> event = SourceFetchEvent(
        ...     source_type='rss',
        ...     source_url='https://example.com/feed.xml',
        ...     success=True,
        ...     articles_count=10,
        ...     content_length=50000,
        ...     response_time_ms=500
        ... )
    
    Requirements: 11.1
    """
    source_type: str
    source_url: str
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    articles_count: int = 0
    content_length: int = 0
    response_time_ms: int = 0
    error_message: str | None = None


@dataclass
class SourceQuality:
    """
    来源质量指标
    Source Quality Metrics
    
    聚合的来源质量评估结果。
    Aggregated source quality assessment results.
    
    Attributes:
        source_type: 来源类型
                     Source type
        source_url: 来源 URL（可选，用于具体来源）
                    Source URL (optional, for specific source)
        total_fetches: 总抓取次数
                       Total fetch count
        successful_fetches: 成功抓取次数
                            Successful fetch count
        response_rate: 响应成功率（0-1）
                       Response success rate (0-1)
        avg_articles_per_fetch: 平均每次抓取文章数
                                Average articles per fetch
        avg_content_length: 平均内容长度
                            Average content length
        avg_response_time_ms: 平均响应时间（毫秒）
                              Average response time in milliseconds
        reliability_score: 可靠性评分（0-100）
                           Reliability score (0-100)
        is_low_quality: 是否为低质量来源
                        Whether it's a low quality source
        last_fetch: 最后抓取时间
                    Last fetch timestamp
    
    Examples:
        >>> quality = SourceQuality(
        ...     source_type='rss',
        ...     total_fetches=100,
        ...     successful_fetches=95,
        ...     response_rate=0.95,
        ...     reliability_score=85.0
        ... )
    
    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
    """
    source_type: str
    source_url: str | None = None
    total_fetches: int = 0
    successful_fetches: int = 0
    response_rate: float = 0.0
    avg_articles_per_fetch: float = 0.0
    avg_content_length: float = 0.0
    avg_response_time_ms: float = 0.0
    reliability_score: float = 0.0
    is_low_quality: bool = False
    last_fetch: datetime | None = None


@dataclass
class TopicFrequency:
    """
    话题频率
    Topic Frequency
    
    记录话题/关键词的出现频率。
    Records the frequency of a topic/keyword.
    
    Attributes:
        topic: 话题/关键词
               Topic/keyword
        frequency: 出现频率
                   Occurrence frequency
        trend: 趋势（'rising', 'stable', 'falling'）
               Trend ('rising', 'stable', 'falling')
        change_rate: 变化率（相对于上一周期）
                     Change rate (relative to previous period)
        first_seen: 首次出现时间
                    First seen timestamp
        last_seen: 最后出现时间
                   Last seen timestamp
        is_spike: 是否为突增话题
                  Whether it's a spike topic
    
    Examples:
        >>> topic = TopicFrequency(
        ...     topic='LLM',
        ...     frequency=150,
        ...     trend='rising',
        ...     change_rate=0.5,
        ...     is_spike=True
        ... )
    
    Requirements: 12.1, 12.2, 12.3, 12.4
    """
    topic: str
    frequency: int = 0
    trend: str = 'stable'
    change_rate: float = 0.0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    is_spike: bool = False


@dataclass
class HotArticle:
    """
    热门文章
    Hot Article
    
    热门文章统计结果。
    Hot article statistics result.
    
    Attributes:
        article_id: 文章 ID
                    Article ID
        title: 文章标题
               Article title
        view_count: 浏览次数
                    View count
        unique_viewers: 独立访客数
                        Unique viewer count
        rank: 排名
              Rank
        source_type: 来源类型
                     Source type
    
    Examples:
        >>> article = HotArticle(
        ...     article_id='123',
        ...     title='深入理解 RAG',
        ...     view_count=500,
        ...     unique_viewers=300,
        ...     rank=1
        ... )
    
    Requirements: 9.2, 9.3, 9.4
    """
    article_id: str
    title: str = ''
    view_count: int = 0
    unique_viewers: int = 0
    rank: int = 0
    source_type: str = ''


@dataclass
class HotQuery:
    """
    热门查询
    Hot Query
    
    热门查询统计结果。
    Hot query statistics result.
    
    Attributes:
        query: 查询文本
               Query text
        count: 查询次数
               Query count
        avg_relevance: 平均相关性分数
                       Average relevance score
        rank: 排名
              Rank
    
    Examples:
        >>> query = HotQuery(
        ...     query='什么是 RAG？',
        ...     count=50,
        ...     avg_relevance=0.85,
        ...     rank=1
        ... )
    
    Requirements: 10.2, 10.3
    """
    query: str
    count: int = 0
    avg_relevance: float = 0.0
    rank: int = 0


@dataclass
class QAStats:
    """
    问答统计
    QA Statistics
    
    问答系统的聚合统计数据。
    Aggregated statistics for the QA system.
    
    Attributes:
        total_queries: 总查询数
                       Total query count
        avg_relevance_score: 平均相关性分数
                             Average relevance score
        avg_response_time_ms: 平均响应时间（毫秒）
                              Average response time in milliseconds
        positive_feedback_rate: 正面反馈率
                                Positive feedback rate
        queries_with_sources: 有来源的查询数
                              Queries with sources count
        avg_sources_per_query: 平均每查询来源数
                               Average sources per query
        period_start: 统计周期开始时间
                      Statistics period start
        period_end: 统计周期结束时间
                    Statistics period end
    
    Examples:
        >>> stats = QAStats(
        ...     total_queries=1000,
        ...     avg_relevance_score=0.82,
        ...     avg_response_time_ms=1500,
        ...     positive_feedback_rate=0.75
        ... )
    
    Requirements: 10.4, 10.5
    """
    total_queries: int = 0
    avg_relevance_score: float = 0.0
    avg_response_time_ms: float = 0.0
    positive_feedback_rate: float = 0.0
    queries_with_sources: int = 0
    avg_sources_per_query: float = 0.0
    period_start: datetime | None = None
    period_end: datetime | None = None
