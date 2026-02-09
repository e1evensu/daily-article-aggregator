"""
话题追踪器
Topic Tracker

追踪和分析热门话题，检测话题突增。
Tracks and analyzes hot topics, detects topic spikes.

Requirements:
- 12.1: 关键词提取
- 12.2: 频率聚合
- 12.3: 趋势计算
- 12.4: 突增检测
- 12.5: 话题排名
"""

import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from src.stats.models import TopicFrequency
from src.stats.store import StatsStore

logger = logging.getLogger(__name__)


# 停用词列表（中英文常见停用词）
STOP_WORDS = {
    # 中文停用词
    '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
    '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
    '自己', '这', '那', '什么', '怎么', '如何', '为什么', '可以', '能', '吗', '呢',
    '啊', '哦', '嗯', '这个', '那个', '这些', '那些', '他', '她', '它', '他们',
    # 英文停用词
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
    'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'under', 'again', 'further', 'then', 'once', 'here',
    'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
    'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or',
    'because', 'until', 'while', 'about', 'against', 'this', 'that',
    'these', 'those', 'what', 'which', 'who', 'whom', 'i', 'me', 'my',
    'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours',
    'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her',
    'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their',
    'theirs', 'themselves',
}


class TopicTracker:
    """
    话题追踪器
    Topic Tracker
    
    从问答查询中提取关键词，追踪话题频率和趋势。
    Extracts keywords from QA queries, tracks topic frequency and trends.
    
    Attributes:
        store: 统计数据存储
               Statistics data store
        min_keyword_length: 最小关键词长度
                            Minimum keyword length
        spike_threshold: 突增检测阈值（相对于平均值的倍数）
                         Spike detection threshold (multiple of average)
    
    Examples:
        >>> tracker = TopicTracker()
        >>> topics = tracker.get_trending_topics(days=7)
        >>> for topic in topics:
        ...     print(f"{topic.topic}: {topic.frequency} ({topic.trend})")
    
    Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
    """
    
    def __init__(
        self,
        store: StatsStore | None = None,
        db_path: str = 'data/stats.db',
        min_keyword_length: int = 2,
        spike_threshold: float = 3.0
    ):
        """
        初始化话题追踪器
        Initialize Topic Tracker
        
        Args:
            store: 统计数据存储（可选，用于依赖注入）
                   Statistics data store (optional, for dependency injection)
            db_path: 数据库路径（当 store 为 None 时使用）
                     Database path (used when store is None)
            min_keyword_length: 最小关键词长度
                                Minimum keyword length
            spike_threshold: 突增检测阈值
                             Spike detection threshold
        """
        self.store = store or StatsStore(db_path)
        self.min_keyword_length = min_keyword_length
        self.spike_threshold = spike_threshold
        
        # 尝试加载 jieba（可选）
        self._jieba = None
        try:
            import jieba
            self._jieba = jieba
            logger.info("jieba loaded for Chinese word segmentation")
        except ImportError:
            logger.info("jieba not available, using simple tokenization")
    
    def extract_keywords(self, text: str) -> list[str]:
        """
        从文本中提取关键词
        Extract keywords from text
        
        Args:
            text: 输入文本
                  Input text
        
        Returns:
            关键词列表
            List of keywords
        
        Examples:
            >>> tracker.extract_keywords("什么是 RAG 检索增强生成？")
            ['RAG', '检索', '增强', '生成']
        
        Requirements: 12.1
        """
        if not text:
            return []
        
        keywords = []
        
        # 使用 jieba 分词（如果可用）
        if self._jieba:
            words = self._jieba.cut(text)
            for word in words:
                word = word.strip()
                if self._is_valid_keyword(word):
                    keywords.append(word)
        else:
            # 简单分词：按空格和标点分割
            keywords = self._simple_tokenize(text)
        
        return keywords
    
    def _simple_tokenize(self, text: str) -> list[str]:
        """
        简单分词
        Simple tokenization
        
        Args:
            text: 输入文本
                  Input text
        
        Returns:
            词列表
            List of words
        """
        # 分割中英文
        # 匹配中文词（连续中文字符）和英文词（连续字母数字）
        pattern = r'[\u4e00-\u9fff]+|[a-zA-Z][a-zA-Z0-9]*'
        matches = re.findall(pattern, text)
        
        keywords = []
        for word in matches:
            word = word.strip()
            if self._is_valid_keyword(word):
                keywords.append(word)
        
        return keywords
    
    def _is_valid_keyword(self, word: str) -> bool:
        """
        检查是否为有效关键词
        Check if it's a valid keyword
        
        Args:
            word: 词
                  Word
        
        Returns:
            True 如果是有效关键词
            True if it's a valid keyword
        """
        if not word:
            return False
        
        # 长度检查
        if len(word) < self.min_keyword_length:
            return False
        
        # 停用词检查
        if word.lower() in STOP_WORDS:
            return False
        
        # 纯数字检查
        if word.isdigit():
            return False
        
        return True
    
    def get_topic_frequencies(
        self,
        days: int = 7,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100
    ) -> list[TopicFrequency]:
        """
        获取话题频率
        Get topic frequencies
        
        从问答查询中提取关键词并统计频率。
        Extracts keywords from QA queries and counts frequencies.
        
        Args:
            days: 统计天数（当 start_time/end_time 未指定时使用）
                  Number of days (used when start_time/end_time not specified)
            start_time: 开始时间（可选）
                        Start time (optional)
            end_time: 结束时间（可选）
                      End time (optional)
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            话题频率列表（按频率降序）
            List of topic frequencies (sorted by frequency descending)
        
        Examples:
            >>> topics = tracker.get_topic_frequencies(days=7, limit=20)
            >>> for topic in topics:
            ...     print(f"{topic.topic}: {topic.frequency}")
        
        Requirements: 12.2
        """
        # 计算时间范围
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(days=days)
        
        # 获取问答事件
        events = self.store.get_qa_events(
            start_time=start_time,
            end_time=end_time,
            limit=100000
        )
        
        # 提取关键词并统计
        keyword_counter: Counter = Counter()
        keyword_first_seen: dict[str, datetime] = {}
        keyword_last_seen: dict[str, datetime] = {}
        
        for event in events:
            keywords = self.extract_keywords(event.query)
            for keyword in keywords:
                keyword_counter[keyword] += 1
                
                # 记录首次和最后出现时间
                if keyword not in keyword_first_seen:
                    keyword_first_seen[keyword] = event.timestamp
                keyword_last_seen[keyword] = event.timestamp
        
        # 构建话题频率列表
        topics = []
        for keyword, frequency in keyword_counter.most_common(limit):
            topics.append(TopicFrequency(
                topic=keyword,
                frequency=frequency,
                first_seen=keyword_first_seen.get(keyword),
                last_seen=keyword_last_seen.get(keyword)
            ))
        
        return topics
    
    def get_trending_topics(
        self,
        days: int = 7,
        compare_days: int = 7,
        limit: int = 20
    ) -> list[TopicFrequency]:
        """
        获取趋势话题
        Get trending topics
        
        比较当前周期和上一周期的话题频率，计算趋势。
        Compares topic frequencies between current and previous periods,
        calculates trends.
        
        Args:
            days: 当前周期天数
                  Current period days
            compare_days: 对比周期天数
                          Comparison period days
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            趋势话题列表（包含趋势信息）
            List of trending topics (with trend information)
        
        Examples:
            >>> topics = tracker.get_trending_topics(days=7)
            >>> for topic in topics:
            ...     print(f"{topic.topic}: {topic.trend} ({topic.change_rate:+.1%})")
        
        Requirements: 12.3
        """
        now = datetime.now()
        
        # 当前周期
        current_start = now - timedelta(days=days)
        current_topics = self.get_topic_frequencies(
            start_time=current_start,
            end_time=now,
            limit=1000
        )
        current_freq = {t.topic: t.frequency for t in current_topics}
        
        # 上一周期
        prev_end = current_start
        prev_start = prev_end - timedelta(days=compare_days)
        prev_topics = self.get_topic_frequencies(
            start_time=prev_start,
            end_time=prev_end,
            limit=1000
        )
        prev_freq = {t.topic: t.frequency for t in prev_topics}
        
        # 计算趋势
        trending = []
        for topic in current_topics[:limit]:
            current = current_freq.get(topic.topic, 0)
            previous = prev_freq.get(topic.topic, 0)
            
            # 计算变化率
            if previous > 0:
                change_rate = (current - previous) / previous
            elif current > 0:
                change_rate = 1.0  # 新话题
            else:
                change_rate = 0.0
            
            # 判断趋势
            if change_rate > 0.2:
                trend = 'rising'
            elif change_rate < -0.2:
                trend = 'falling'
            else:
                trend = 'stable'
            
            # 检测突增
            avg_freq = (current + previous) / 2 if previous > 0 else current / 2
            is_spike = current > avg_freq * self.spike_threshold if avg_freq > 0 else False
            
            trending.append(TopicFrequency(
                topic=topic.topic,
                frequency=topic.frequency,
                trend=trend,
                change_rate=change_rate,
                first_seen=topic.first_seen,
                last_seen=topic.last_seen,
                is_spike=is_spike
            ))
        
        return trending
    
    def detect_spikes(
        self,
        days: int = 1,
        baseline_days: int = 7,
        limit: int = 10
    ) -> list[TopicFrequency]:
        """
        检测话题突增
        Detect topic spikes
        
        检测相对于基线周期频率突增的话题。
        Detects topics with frequency spikes relative to baseline period.
        
        Args:
            days: 检测周期天数
                  Detection period days
            baseline_days: 基线周期天数
                           Baseline period days
            limit: 返回数量限制
                   Return count limit
        
        Returns:
            突增话题列表
            List of spike topics
        
        Examples:
            >>> spikes = tracker.detect_spikes(days=1, baseline_days=7)
            >>> for topic in spikes:
            ...     print(f"🔥 {topic.topic}: {topic.frequency} ({topic.change_rate:+.1%})")
        
        Requirements: 12.4
        """
        trending = self.get_trending_topics(
            days=days,
            compare_days=baseline_days,
            limit=100
        )
        
        # 过滤出突增话题
        spikes = [t for t in trending if t.is_spike]
        
        # 按变化率降序排序
        spikes.sort(key=lambda x: x.change_rate, reverse=True)
        
        return spikes[:limit]
    
    def get_topic_history(
        self,
        topic: str,
        days: int = 30
    ) -> list[tuple[str, int]]:
        """
        获取话题历史频率
        Get topic history frequency
        
        Args:
            topic: 话题/关键词
                   Topic/keyword
            days: 统计天数
                  Number of days
        
        Returns:
            (日期, 频率) 元组列表
            List of (date, frequency) tuples
        
        Requirements: 13.2
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # 获取问答事件
        events = self.store.get_qa_events(
            start_time=start_time,
            end_time=end_time,
            limit=100000
        )
        
        # 按日期统计话题出现次数
        daily_counts: dict[str, int] = {}
        for event in events:
            keywords = self.extract_keywords(event.query)
            if topic in keywords:
                date_str = event.timestamp.strftime('%Y-%m-%d')
                daily_counts[date_str] = daily_counts.get(date_str, 0) + 1
        
        # 填充缺失日期
        result = []
        current = start_time
        while current <= end_time:
            date_str = current.strftime('%Y-%m-%d')
            result.append((date_str, daily_counts.get(date_str, 0)))
            current += timedelta(days=1)
        
        return result
