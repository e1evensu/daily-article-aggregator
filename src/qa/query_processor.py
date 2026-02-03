"""
查询处理器模块

负责解析用户查询，检测查询类型，提取关键词和构建搜索过滤器。

Requirements:
    - 4.1: 支持查询最新漏洞（如"最近有什么高危漏洞"）
    - 4.2: 支持查询特定话题（如"LLM安全相关的论文"）
    - 4.3: 支持查询特定来源（如"arXiv上关于RAG的论文"）
    - 4.4: 支持时间范围查询（如"这周的安全新闻"）
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class ParsedQuery:
    """
    解析后的查询结果
    
    Attributes:
        query_type: 查询类型 (general/vulnerability/topic/source/time_range)
        keywords: 提取的关键词列表
        filters: 过滤条件字典
        original_query: 原始查询文本
        cve_ids: 检测到的 CVE ID 列表
        time_range: 时间范围元组 (start_date, end_date)
    
    Requirements: 4.1, 4.2, 4.3, 4.4
    """
    query_type: str = "general"
    keywords: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    original_query: str = ""
    cve_ids: list[str] = field(default_factory=list)
    time_range: tuple[datetime, datetime] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {
            "type": self.query_type,
            "keywords": self.keywords,
            "filters": self.filters,
            "original_query": self.original_query,
        }
        if self.cve_ids:
            result["cve_ids"] = self.cve_ids
        if self.time_range:
            result["time_range"] = {
                "start": self.time_range[0].isoformat(),
                "end": self.time_range[1].isoformat(),
            }
        return result


class QueryProcessor:
    """
    查询预处理器，处理特殊查询
    
    负责：
    - 检测查询类型（漏洞/话题/来源/时间范围/通用）
    - 提取关键词
    - 构建搜索过滤器
    
    支持中英文查询。
    
    Requirements: 4.1, 4.2, 4.3, 4.4
    """
    
    # CVE ID 正则表达式
    CVE_PATTERN = re.compile(r'CVE-\d{4}-\d{4,}', re.IGNORECASE)
    
    # 来源类型关键词映射（中英文）
    SOURCE_KEYWORDS: dict[str, list[str]] = {
        "arxiv": ["arxiv", "arXiv", "论文", "paper", "papers", "预印本"],
        "rss": ["rss", "博客", "blog", "blogs", "新闻", "news", "资讯"],
        "nvd": ["nvd", "NVD", "漏洞库", "漏洞数据库", "vulnerability database"],
        "kev": ["kev", "KEV", "已知漏洞", "known exploited", "cisa"],
        "blog": ["blog", "博客", "技术博客", "tech blog"],
        "pwc": ["pwc", "papers with code", "paperswithcode"],
        "huggingface": ["huggingface", "hf", "hugging face", "模型"],
        "dblp": ["dblp", "DBLP", "学术论文", "academic"],
    }
    
    # 漏洞相关关键词（中英文）
    VULNERABILITY_KEYWORDS: list[str] = [
        # 中文
        "漏洞", "安全漏洞", "高危漏洞", "严重漏洞", "紧急漏洞",
        "0day", "零日", "远程代码执行", "RCE", "提权", "权限提升",
        "注入", "SQL注入", "XSS", "跨站脚本", "CSRF",
        "缓冲区溢出", "内存泄漏", "拒绝服务", "DoS", "DDoS",
        # 英文
        "vulnerability", "vulnerabilities", "exploit", "exploits",
        "security flaw", "security issue", "security bug",
        "zero-day", "zeroday", "remote code execution",
        "privilege escalation", "injection", "buffer overflow",
        "denial of service", "critical vulnerability", "high severity",
    ]
    
    # 时间范围关键词映射
    TIME_KEYWORDS: dict[str, int] = {
        # 中文
        "今天": 0,
        "昨天": 1,
        "前天": 2,
        "这周": 7,
        "本周": 7,
        "上周": 14,
        "这个月": 30,
        "本月": 30,
        "上个月": 60,
        "最近": 7,
        "近期": 14,
        "最新": 3,
        # 英文
        "today": 0,
        "yesterday": 1,
        "this week": 7,
        "last week": 14,
        "this month": 30,
        "last month": 60,
        "recent": 7,
        "recently": 7,
        "latest": 3,
    }
    
    # 话题/分类关键词
    TOPIC_KEYWORDS: dict[str, list[str]] = {
        "AI/机器学习": [
            "AI", "人工智能", "机器学习", "深度学习", "神经网络",
            "LLM", "大模型", "大语言模型", "GPT", "transformer",
            "machine learning", "deep learning", "neural network",
            "artificial intelligence", "language model",
        ],
        "安全/隐私": [
            "安全", "隐私", "加密", "认证", "授权",
            "security", "privacy", "encryption", "authentication",
            "cybersecurity", "信息安全", "网络安全",
        ],
        "系统/架构": [
            "系统", "架构", "分布式", "微服务", "容器",
            "kubernetes", "docker", "云原生", "cloud native",
            "system", "architecture", "distributed",
        ],
    }
    
    # 停用词（用于关键词提取时过滤）
    STOP_WORDS: set[str] = {
        # 中文停用词
        "的", "了", "是", "在", "有", "和", "与", "或", "等",
        "这", "那", "什么", "怎么", "如何", "为什么", "哪些",
        "请", "帮", "我", "你", "他", "她", "它", "们",
        "吗", "呢", "吧", "啊", "呀", "哦", "嗯",
        "关于", "关于", "相关", "有关",
        # 英文停用词
        "the", "a", "an", "is", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may",
        "might", "must", "shall", "can", "need", "dare",
        "to", "of", "in", "for", "on", "with", "at", "by",
        "from", "as", "into", "through", "during", "before",
        "after", "above", "below", "between", "under", "again",
        "further", "then", "once", "here", "there", "when",
        "where", "why", "how", "all", "each", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not",
        "only", "own", "same", "so", "than", "too", "very",
        "just", "and", "but", "if", "or", "because", "until",
        "while", "about", "against", "any", "both", "what",
        "which", "who", "whom", "this", "that", "these", "those",
        "am", "i", "me", "my", "myself", "we", "our", "ours",
        "ourselves", "you", "your", "yours", "yourself",
        "yourselves", "he", "him", "his", "himself", "she",
        "her", "hers", "herself", "it", "its", "itself",
        "they", "them", "their", "theirs", "themselves",
    }
    
    def __init__(self):
        """
        初始化查询处理器
        
        Requirements: 4.1, 4.2, 4.3, 4.4
        """
        logger.info("QueryProcessor initialized")
    
    def parse_query(self, query: str) -> ParsedQuery:
        """
        解析查询，提取意图和参数
        
        Args:
            query: 用户查询文本
        
        Returns:
            ParsedQuery 对象，包含：
                - type: 查询类型
                - keywords: 关键词列表
                - filters: 过滤条件
                - original_query: 原始查询
        
        Examples:
            >>> processor = QueryProcessor()
            >>> result = processor.parse_query("CVE-2024-1234 漏洞详情")
            >>> result.query_type
            'vulnerability'
            >>> result.cve_ids
            ['CVE-2024-1234']
            
            >>> result = processor.parse_query("arXiv上关于RAG的论文")
            >>> result.query_type
            'source'
            >>> result.filters.get('source_type')
            'arxiv'
        
        Requirements: 4.1, 4.2, 4.3, 4.4
        """
        if not query or not query.strip():
            return ParsedQuery(original_query=query)
        
        query = query.strip()
        result = ParsedQuery(original_query=query)
        
        # 1. 检测 CVE ID（最高优先级）
        cve_ids = self._extract_cve_ids(query)
        if cve_ids:
            result.cve_ids = cve_ids
            result.query_type = "vulnerability"
            result.keywords = cve_ids + self._extract_keywords(query)
            result.filters = {"cve_ids": cve_ids}
            return result
        
        # 2. 检测漏洞相关查询
        if self._is_vulnerability_query(query):
            result.query_type = "vulnerability"
            result.keywords = self._extract_keywords(query)
            # 检测时间范围
            time_range = self._detect_time_range(query)
            if time_range:
                result.time_range = time_range
                result.filters["time_range"] = {
                    "start": time_range[0].isoformat(),
                    "end": time_range[1].isoformat(),
                }
            return result
        
        # 3. 检测来源类型查询
        source_type = self._detect_source_type(query)
        if source_type:
            result.query_type = "source"
            result.filters["source_type"] = source_type
            result.keywords = self._extract_keywords(query)
            # 检测时间范围
            time_range = self._detect_time_range(query)
            if time_range:
                result.time_range = time_range
                result.filters["time_range"] = {
                    "start": time_range[0].isoformat(),
                    "end": time_range[1].isoformat(),
                }
            return result
        
        # 4. 检测时间范围查询
        time_range = self._detect_time_range(query)
        if time_range:
            result.query_type = "time_range"
            result.time_range = time_range
            result.filters["time_range"] = {
                "start": time_range[0].isoformat(),
                "end": time_range[1].isoformat(),
            }
            result.keywords = self._extract_keywords(query)
            return result
        
        # 5. 检测话题查询
        topic = self._detect_topic(query)
        if topic:
            result.query_type = "topic"
            result.filters["category"] = topic
            result.keywords = self._extract_keywords(query)
            return result
        
        # 6. 通用查询
        result.query_type = "general"
        result.keywords = self._extract_keywords(query)
        return result
    
    def _extract_cve_ids(self, query: str) -> list[str]:
        """
        从查询中提取 CVE ID
        
        Args:
            query: 查询文本
        
        Returns:
            CVE ID 列表（大写格式）
        
        Requirements: 4.1
        """
        matches = self.CVE_PATTERN.findall(query)
        # 转换为大写并去重
        return list(dict.fromkeys(cve.upper() for cve in matches))
    
    def _is_vulnerability_query(self, query: str) -> bool:
        """
        检测是否为漏洞相关查询
        
        Args:
            query: 查询文本
        
        Returns:
            是否为漏洞查询
        
        Requirements: 4.1
        """
        query_lower = query.lower()
        for keyword in self.VULNERABILITY_KEYWORDS:
            if keyword.lower() in query_lower:
                return True
        return False
    
    def _detect_source_type(self, query: str) -> str | None:
        """
        检测查询中的来源类型
        
        Args:
            query: 查询文本
        
        Returns:
            来源类型字符串，如果未检测到则返回 None
        
        Requirements: 4.3
        """
        query_lower = query.lower()
        for source_type, keywords in self.SOURCE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    return source_type
        return None
    
    def _detect_time_range(self, query: str) -> tuple[datetime, datetime] | None:
        """
        检测查询中的时间范围
        
        Args:
            query: 查询文本
        
        Returns:
            时间范围元组 (start_date, end_date)，如果未检测到则返回 None
        
        Requirements: 4.4
        """
        query_lower = query.lower()
        now = datetime.now()
        
        # 检查时间关键词
        for keyword, days_back in self.TIME_KEYWORDS.items():
            if keyword.lower() in query_lower:
                if days_back == 0:
                    # 今天
                    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    end = now
                else:
                    start = now - timedelta(days=days_back)
                    end = now
                return (start, end)
        
        # 检查数字+时间单位模式（如"3天内"、"7天前"、"last 3 days"）
        patterns = [
            # 中文模式
            (r'(\d+)\s*天[内前]?', 'days'),
            (r'(\d+)\s*周[内前]?', 'weeks'),
            (r'(\d+)\s*个?月[内前]?', 'months'),
            # 英文模式
            (r'(?:last|past)\s*(\d+)\s*days?', 'days'),
            (r'(?:last|past)\s*(\d+)\s*weeks?', 'weeks'),
            (r'(?:last|past)\s*(\d+)\s*months?', 'months'),
            (r'(\d+)\s*days?\s*(?:ago|back)', 'days'),
        ]
        
        for pattern, unit in patterns:
            match = re.search(pattern, query_lower)
            if match:
                num = int(match.group(1))
                if unit == 'days':
                    delta = timedelta(days=num)
                elif unit == 'weeks':
                    delta = timedelta(weeks=num)
                elif unit == 'months':
                    delta = timedelta(days=num * 30)  # 近似
                else:
                    continue
                
                start = now - delta
                return (start, now)
        
        return None
    
    def _detect_topic(self, query: str) -> str | None:
        """
        检测查询中的话题/分类
        
        Args:
            query: 查询文本
        
        Returns:
            话题/分类字符串，如果未检测到则返回 None
        
        Requirements: 4.2
        """
        query_lower = query.lower()
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    return topic
        return None
    
    def _extract_keywords(self, query: str) -> list[str]:
        """
        从查询中提取关键词
        
        移除停用词和常见查询词，保留有意义的关键词。
        
        Args:
            query: 查询文本
        
        Returns:
            关键词列表
        
        Requirements: 4.1, 4.2, 4.3, 4.4
        """
        # 移除 CVE ID（已单独处理）
        text = self.CVE_PATTERN.sub('', query)
        
        # 分词（简单的中英文混合分词）
        # 英文按空格和标点分割
        # 中文按字符处理（简化处理，实际可用 jieba 等分词库）
        tokens = []
        
        # 先按空格和标点分割
        parts = re.split(r'[\s,，.。!！?？;；:：\'""\'\"\(\)（）\[\]【】<>《》]+', text)
        
        for part in parts:
            if not part:
                continue
            
            # 检查是否为纯英文
            if re.match(r'^[a-zA-Z0-9\-_]+$', part):
                tokens.append(part)
            else:
                # 混合文本，尝试分离中英文
                # 提取英文单词
                english_words = re.findall(r'[a-zA-Z0-9\-_]+', part)
                tokens.extend(english_words)
                
                # 提取中文部分（简单处理：连续中文字符作为一个词）
                chinese_parts = re.findall(r'[\u4e00-\u9fff]+', part)
                for cp in chinese_parts:
                    # 对于较长的中文，尝试按2-4字分词
                    if len(cp) <= 4:
                        tokens.append(cp)
                    else:
                        # 简单的 n-gram 分词
                        for i in range(0, len(cp) - 1, 2):
                            tokens.append(cp[i:i+2])
                        if len(cp) >= 3:
                            for i in range(0, len(cp) - 2, 2):
                                tokens.append(cp[i:i+3])
        
        # 过滤停用词和短词
        keywords = []
        seen = set()
        for token in tokens:
            token_lower = token.lower()
            if (
                token_lower not in self.STOP_WORDS
                and len(token) >= 2
                and token_lower not in seen
            ):
                keywords.append(token)
                seen.add(token_lower)
        
        return keywords
    
    def build_search_filters(self, parsed: ParsedQuery) -> dict[str, Any]:
        """
        根据解析结果构建搜索过滤器
        
        将 ParsedQuery 中的过滤条件转换为 KnowledgeBase.search() 可用的格式。
        
        Args:
            parsed: 解析后的查询结果
        
        Returns:
            搜索过滤器字典
        
        Examples:
            >>> processor = QueryProcessor()
            >>> parsed = processor.parse_query("arXiv上关于RAG的论文")
            >>> filters = processor.build_search_filters(parsed)
            >>> filters.get('source_type')
            'arxiv'
        
        Requirements: 1.4, 4.1, 4.2, 4.3, 4.4
        """
        filters: dict[str, Any] = {}
        
        # 来源类型过滤
        if "source_type" in parsed.filters:
            filters["source_type"] = parsed.filters["source_type"]
        
        # 分类过滤
        if "category" in parsed.filters:
            filters["category"] = parsed.filters["category"]
        
        # 时间范围过滤（需要知识库支持）
        if "time_range" in parsed.filters:
            filters["time_range"] = parsed.filters["time_range"]
        
        # CVE ID 过滤（特殊处理）
        if "cve_ids" in parsed.filters:
            filters["cve_ids"] = parsed.filters["cve_ids"]
        
        return filters
    
    def get_query_description(self, parsed: ParsedQuery) -> str:
        """
        生成查询的人类可读描述
        
        用于日志记录和调试。
        
        Args:
            parsed: 解析后的查询结果
        
        Returns:
            查询描述字符串
        """
        parts = [f"类型: {parsed.query_type}"]
        
        if parsed.cve_ids:
            parts.append(f"CVE: {', '.join(parsed.cve_ids)}")
        
        if parsed.keywords:
            parts.append(f"关键词: {', '.join(parsed.keywords[:5])}")
        
        if parsed.filters.get("source_type"):
            parts.append(f"来源: {parsed.filters['source_type']}")
        
        if parsed.filters.get("category"):
            parts.append(f"分类: {parsed.filters['category']}")
        
        if parsed.time_range:
            start, end = parsed.time_range
            parts.append(f"时间: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        
        return " | ".join(parts)
