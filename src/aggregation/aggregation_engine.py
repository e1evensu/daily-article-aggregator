"""
话题聚合引擎模块

负责计算文章相似度并进行话题聚类。
本模块支持两种相似度计算方式：
1. AI Embedding 方式（推荐）：使用 AI 模型生成文本向量，计算余弦相似度
2. 传统方式（备选）：使用 jieba 分词提取关键词，计算 Jaccard 相似度

Requirements:
- 1.1: 计算每篇文章与现有文章的 Similarity_Score
- 1.4: 支持基于 CVE ID、技术术语和关键词的多维度相似度计算
- 1.5: 标题权重 0.6，关键词权重 0.4
"""

import json
import logging
import re
from collections import Counter
from typing import Any

from openai import OpenAI, APIError

from src.models import Article
from src.aggregation.models import TopicCluster

# 尝试导入 jieba 作为备选方案
try:
    import jieba
    import jieba.analyse
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_SIMILARITY_THRESHOLD = 0.7
DEFAULT_AGGREGATION_THRESHOLD = 3
DEFAULT_TIME_WINDOW_DAYS = 7
DEFAULT_TITLE_WEIGHT = 0.6
DEFAULT_KEYWORD_WEIGHT = 0.4

# AI similarity configuration
DEFAULT_USE_AI_SIMILARITY = True
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

# CVE ID pattern: CVE-YYYY-NNNNN (4 digits year, 4+ digits number)
CVE_PATTERN = re.compile(r'CVE-\d{4}-\d{4,}', re.IGNORECASE)

# Chinese stopwords for keyword extraction (used in fallback mode)
CHINESE_STOPWORDS = {
    '的', '了', '和', '是', '就', '都', '而', '及', '与', '着',
    '或', '一个', '没有', '我们', '你们', '他们', '它们', '这个',
    '那个', '这些', '那些', '什么', '怎么', '如何', '为什么',
    '可以', '可能', '应该', '需要', '使用', '通过', '进行',
    '其中', '之后', '之前', '以及', '但是', '然而', '因此',
    '所以', '如果', '虽然', '即使', '无论', '不仅', '而且',
    '一种', '一些', '这种', '那种', '各种', '某些', '任何',
}

# English stopwords
ENGLISH_STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
    'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are',
    'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must',
    'shall', 'can', 'need', 'dare', 'ought', 'used', 'this', 'that',
    'these', 'those', 'it', 'its', 'they', 'them', 'their', 'we',
    'our', 'you', 'your', 'he', 'she', 'him', 'her', 'his', 'hers',
    'which', 'who', 'whom', 'what', 'where', 'when', 'why', 'how',
    'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
    'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
    'than', 'too', 'very', 'just', 'also', 'now', 'here', 'there',
}

# Combined stopwords
STOPWORDS = CHINESE_STOPWORDS | ENGLISH_STOPWORDS


class AggregationEngine:
    """
    话题聚合引擎
    
    负责计算文章相似度并进行话题聚类。
    支持两种相似度计算方式：
    1. AI Embedding（推荐）：语义级别的相似度计算
    2. 传统 jieba 分词（备选）：基于关键词的相似度计算
    
    Attributes:
        similarity_threshold: 相似度阈值（默认 0.7）
        aggregation_threshold: 聚合阈值（默认 3）
        time_window_days: 时间窗口天数（默认 7）
        title_weight: 标题权重（默认 0.6）
        keyword_weight: 关键词权重（默认 0.4）
        use_ai_similarity: 是否使用 AI 计算相似度（默认 True）
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化聚合引擎
        
        Args:
            config: 配置字典，包含：
                - similarity_threshold: 相似度阈值（默认 0.7）
                - aggregation_threshold: 聚合阈值（默认 3）
                - time_window_days: 时间窗口天数（默认 7）
                - title_weight: 标题权重（默认 0.6）
                - keyword_weight: 关键词权重（默认 0.4）
                - use_ai_similarity: 是否使用 AI 计算相似度（默认 True）
                - ai_config: AI 配置（api_base, api_key, embedding_model）
        """
        config = config or {}
        
        self.similarity_threshold = config.get(
            'similarity_threshold', DEFAULT_SIMILARITY_THRESHOLD
        )
        self.aggregation_threshold = config.get(
            'aggregation_threshold', DEFAULT_AGGREGATION_THRESHOLD
        )
        self.time_window_days = config.get(
            'time_window_days', DEFAULT_TIME_WINDOW_DAYS
        )
        self.title_weight = config.get(
            'title_weight', DEFAULT_TITLE_WEIGHT
        )
        self.keyword_weight = config.get(
            'keyword_weight', DEFAULT_KEYWORD_WEIGHT
        )
        
        # AI 相似度配置
        self.use_ai_similarity = config.get(
            'use_ai_similarity', DEFAULT_USE_AI_SIMILARITY
        )
        
        # 初始化 AI 客户端（如果启用）
        self._ai_client: OpenAI | None = None
        self._embedding_model = DEFAULT_EMBEDDING_MODEL
        self._model = "deepseek-ai/DeepSeek-V3"  # 默认模型
        self._embedding_cache: dict[str, list[float]] = {}  # 缓存 embedding 结果

        ai_config = config.get('ai_config', {})
        if self.use_ai_similarity and ai_config:
            self._init_ai_client(ai_config)
        
        # Validate weights sum to 1.0
        total_weight = self.title_weight + self.keyword_weight
        if abs(total_weight - 1.0) > 0.001:
            # Normalize weights
            self.title_weight = self.title_weight / total_weight
            self.keyword_weight = self.keyword_weight / total_weight
        
        mode = "AI Embedding" if self._ai_client else "jieba 分词"
        logger.info(f"AggregationEngine 初始化完成，使用 {mode} 计算相似度")
    
    def _init_ai_client(self, ai_config: dict[str, Any]):
        """
        初始化 AI 客户端
        
        Args:
            ai_config: AI 配置字典
        """
        api_base = ai_config.get('api_base', 'https://api.openai.com/v1')
        api_key = ai_config.get('api_key', '')
        
        if not api_key:
            logger.warning("AI API key 未配置，将使用 jieba 分词作为备选")
            self.use_ai_similarity = False
            return
        
        try:
            self._ai_client = OpenAI(
                base_url=api_base,
                api_key=api_key
            )
            self._embedding_model = ai_config.get(
                'embedding_model', DEFAULT_EMBEDDING_MODEL
            )
            self._model = ai_config.get('model', 'deepseek-ai/DeepSeek-V3')
            logger.info(f"AI 客户端初始化成功，embedding 模型: {self._embedding_model}, chat 模型: {self._model}")
        except Exception as e:
            logger.error(f"AI 客户端初始化失败: {e}，将使用 jieba 分词作为备选")
            self._ai_client = None
            self.use_ai_similarity = False
    
    def _get_embedding(self, text: str) -> list[float] | None:
        """
        获取文本的 embedding 向量
        
        Args:
            text: 输入文本
        
        Returns:
            embedding 向量，失败返回 None
        """
        if not self._ai_client or not text:
            return None
        
        # 检查缓存
        cache_key = text[:500]  # 使用前 500 字符作为缓存键
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]
        
        try:
            # 限制文本长度（BAAI/bge-large-zh-v1.5 限制 512 tokens，约 500 字符）
            truncated_text = text[:500]
            
            response = self._ai_client.embeddings.create(
                model=self._embedding_model,
                input=truncated_text
            )
            
            if response.data and len(response.data) > 0:
                embedding = response.data[0].embedding
                # 缓存结果
                self._embedding_cache[cache_key] = embedding
                return embedding
            
            return None
        except APIError as e:
            logger.warning(f"获取 embedding 失败: {e}")
            return None
        except Exception as e:
            logger.error(f"获取 embedding 时发生错误: {e}")
            return None
    
    def _calculate_embedding_similarity(
        self, 
        embedding1: list[float], 
        embedding2: list[float]
    ) -> float:
        """
        计算两个 embedding 向量的余弦相似度
        
        Args:
            embedding1: 第一个 embedding 向量
            embedding2: 第二个 embedding 向量
        
        Returns:
            余弦相似度 (0.0 - 1.0)
        """
        if not embedding1 or not embedding2:
            return 0.0
        
        if len(embedding1) != len(embedding2):
            return 0.0
        
        # 计算点积
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        
        # 计算模长
        magnitude1 = sum(a * a for a in embedding1) ** 0.5
        magnitude2 = sum(b * b for b in embedding2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        # 余弦相似度
        similarity = dot_product / (magnitude1 * magnitude2)
        
        # 归一化到 0-1 范围（余弦相似度可能为负）
        return (similarity + 1) / 2
    
    def _calculate_ai_similarity(
        self, 
        article1: Article, 
        article2: Article
    ) -> float | None:
        """
        使用 AI embedding 计算两篇文章的相似度
        
        Args:
            article1: 第一篇文章
            article2: 第二篇文章
        
        Returns:
            相似度分数 (0.0 - 1.0)，失败返回 None
        """
        # 构建文章文本（标题 + 摘要）
        text1 = f"{article1.title}\n{article1.summary or ''}\n{article1.zh_summary or ''}"
        text2 = f"{article2.title}\n{article2.summary or ''}\n{article2.zh_summary or ''}"
        
        # 获取 embedding
        embedding1 = self._get_embedding(text1)
        embedding2 = self._get_embedding(text2)
        
        if embedding1 is None or embedding2 is None:
            return None
        
        # 计算相似度
        base_similarity = self._calculate_embedding_similarity(embedding1, embedding2)
        
        # CVE ID 匹配加成
        cve_boost = 0.0
        cves1 = set(self.extract_cve_ids(text1))
        cves2 = set(self.extract_cve_ids(text2))
        
        if article1.cve_id:
            cves1.add(article1.cve_id.upper())
        if article2.cve_id:
            cves2.add(article2.cve_id.upper())
        
        if cves1 and cves2 and (cves1 & cves2):
            cve_boost = 0.3  # CVE 匹配加成
        
        return min(1.0, base_similarity + cve_boost)
    
    def calculate_similarity_ai(
        self, 
        text1: str, 
        text2: str
    ) -> float:
        """
        使用 AI 计算两段文本的相似度（公开接口）
        
        Args:
            text1: 第一段文本
            text2: 第二段文本
        
        Returns:
            相似度分数 (0.0 - 1.0)
        """
        if not self._ai_client:
            logger.warning("AI 客户端未初始化，无法计算相似度")
            return 0.0
        
        embedding1 = self._get_embedding(text1)
        embedding2 = self._get_embedding(text2)
        
        if embedding1 is None or embedding2 is None:
            return 0.0
        
        return self._calculate_embedding_similarity(embedding1, embedding2)
    
    def extract_keywords(self, text: str, top_k: int = 20) -> list[str]:
        """
        从文本中提取关键词
        
        优先使用 AI 提取关键词，如果 AI 不可用则使用 jieba 分词。
        
        Args:
            text: 输入文本
            top_k: 返回的关键词数量上限（默认 20）
        
        Returns:
            关键词列表（已去重、去停用词）
        
        Requirements:
            - 1.4: 支持基于技术术语和关键词的多维度相似度计算
        """
        if not text or not text.strip():
            return []
        
        # 如果 AI 可用，使用 AI 提取关键词
        if self._ai_client:
            keywords = self._extract_keywords_ai(text, top_k)
            if keywords:
                return keywords
        
        # 备选：使用 jieba 分词
        return self._extract_keywords_jieba(text, top_k)
    
    def _extract_keywords_ai(self, text: str, top_k: int = 20) -> list[str]:
        """
        使用 AI 提取关键词
        
        Args:
            text: 输入文本
            top_k: 返回的关键词数量上限
        
        Returns:
            关键词列表
        """
        if not self._ai_client:
            return []
        
        try:
            prompt = f"""请从以下文本中提取 {top_k} 个最重要的关键词或技术术语。
只输出关键词，用逗号分隔，不要添加任何解释。

文本：
{text[:2000]}

关键词："""
            
            response = self._ai_client.chat.completions.create(
                model=self._model,  # 使用配置中的模型
                messages=[
                    {"role": "system", "content": "你是一个关键词提取专家，擅长从技术文章中提取核心术语。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content.strip()
                # 解析逗号分隔的关键词
                keywords = [kw.strip().lower() for kw in content.split(',')]
                # 过滤空字符串和停用词
                keywords = [kw for kw in keywords if kw and kw not in STOPWORDS]
                return keywords[:top_k]
            
            return []
        except Exception as e:
            logger.warning(f"AI 关键词提取失败: {e}")
            return []
    
    def _extract_keywords_jieba(self, text: str, top_k: int = 20) -> list[str]:
        """
        使用 jieba 分词提取关键词（备选方案）
        
        Args:
            text: 输入文本
            top_k: 返回的关键词数量上限
        
        Returns:
            关键词列表
        """
        if not JIEBA_AVAILABLE:
            logger.warning("jieba 未安装，无法提取关键词")
            return []
        
        # Use jieba's TF-IDF algorithm to extract keywords
        keywords = jieba.analyse.extract_tags(
            text, 
            topK=top_k * 2,
            withWeight=False
        )
        
        # Filter out stopwords and short words
        filtered_keywords = []
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in STOPWORDS:
                continue
            if len(keyword) < 2:
                continue
            if keyword.isascii() and len(keyword) < 3:
                continue
            filtered_keywords.append(keyword_lower)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in filtered_keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords[:top_k]
    
    def extract_cve_ids(self, text: str) -> list[str]:
        """
        从文本中提取 CVE ID
        
        使用正则表达式匹配 CVE-YYYY-NNNNN 格式的 CVE ID。
        
        Args:
            text: 输入文本
        
        Returns:
            CVE ID 列表（已去重，统一大写格式）
        
        Requirements:
            - 1.4: 支持基于 CVE ID 的多维度相似度计算
        """
        if not text:
            return []
        
        # Find all CVE IDs in the text
        matches = CVE_PATTERN.findall(text)
        
        # Normalize to uppercase and remove duplicates while preserving order
        seen = set()
        unique_cves = []
        for cve in matches:
            cve_upper = cve.upper()
            if cve_upper not in seen:
                seen.add(cve_upper)
                unique_cves.append(cve_upper)
        
        return unique_cves
    
    def _calculate_jaccard_similarity(
        self, 
        set1: set[str], 
        set2: set[str]
    ) -> float:
        """
        计算两个集合的 Jaccard 相似度
        
        Jaccard 相似度 = |A ∩ B| / |A ∪ B|
        
        Args:
            set1: 第一个集合
            set2: 第二个集合
        
        Returns:
            Jaccard 相似度 (0.0 - 1.0)
        """
        if not set1 and not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def _calculate_cosine_similarity(
        self, 
        tokens1: list[str], 
        tokens2: list[str]
    ) -> float:
        """
        计算两个词列表的余弦相似度
        
        余弦相似度 = (A · B) / (||A|| * ||B||)
        
        Args:
            tokens1: 第一个词列表
            tokens2: 第二个词列表
        
        Returns:
            余弦相似度 (0.0 - 1.0)
        """
        if not tokens1 or not tokens2:
            return 0.0
        
        # Create term frequency vectors
        counter1 = Counter(tokens1)
        counter2 = Counter(tokens2)
        
        # Get all unique terms
        all_terms = set(counter1.keys()) | set(counter2.keys())
        
        if not all_terms:
            return 0.0
        
        # Calculate dot product and magnitudes
        dot_product = 0.0
        magnitude1 = 0.0
        magnitude2 = 0.0
        
        for term in all_terms:
            freq1 = counter1.get(term, 0)
            freq2 = counter2.get(term, 0)
            dot_product += freq1 * freq2
            magnitude1 += freq1 * freq1
            magnitude2 += freq2 * freq2
        
        magnitude1 = magnitude1 ** 0.5
        magnitude2 = magnitude2 ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def _calculate_title_similarity(
        self, 
        title1: str, 
        title2: str
    ) -> float:
        """
        计算两个标题的相似度
        
        使用 Jaccard 相似度计算标题关键词的重叠程度。
        
        Args:
            title1: 第一个标题
            title2: 第二个标题
        
        Returns:
            标题相似度 (0.0 - 1.0)
        """
        # Extract keywords from titles
        keywords1 = set(self.extract_keywords(title1, top_k=10))
        keywords2 = set(self.extract_keywords(title2, top_k=10))
        
        # Also check for CVE ID matches (exact match gives high similarity)
        cves1 = set(self.extract_cve_ids(title1))
        cves2 = set(self.extract_cve_ids(title2))
        
        # If both titles contain the same CVE ID, boost similarity
        cve_match_boost = 0.0
        if cves1 and cves2 and (cves1 & cves2):
            cve_match_boost = 0.5  # Significant boost for CVE match
        
        # Calculate Jaccard similarity for keywords
        keyword_similarity = self._calculate_jaccard_similarity(keywords1, keywords2)
        
        # Combine with CVE match boost (capped at 1.0)
        return min(1.0, keyword_similarity + cve_match_boost)
    
    def _calculate_keyword_similarity(
        self, 
        article1: Article, 
        article2: Article
    ) -> float:
        """
        计算两篇文章关键词的相似度
        
        综合考虑文章的 keywords 字段、内容提取的关键词和 CVE ID。
        
        Args:
            article1: 第一篇文章
            article2: 第二篇文章
        
        Returns:
            关键词相似度 (0.0 - 1.0)
        """
        # Collect keywords from multiple sources
        keywords1 = set()
        keywords2 = set()
        
        # 1. Use existing keywords field
        if article1.keywords:
            keywords1.update(kw.lower() for kw in article1.keywords)
        if article2.keywords:
            keywords2.update(kw.lower() for kw in article2.keywords)
        
        # 2. Extract keywords from content/summary
        content1 = f"{article1.summary} {article1.zh_summary} {article1.content}"
        content2 = f"{article2.summary} {article2.zh_summary} {article2.content}"
        
        extracted1 = self.extract_keywords(content1, top_k=15)
        extracted2 = self.extract_keywords(content2, top_k=15)
        
        keywords1.update(extracted1)
        keywords2.update(extracted2)
        
        # 3. Check CVE ID matches
        all_text1 = f"{article1.title} {content1}"
        all_text2 = f"{article2.title} {content2}"
        
        cves1 = set(self.extract_cve_ids(all_text1))
        cves2 = set(self.extract_cve_ids(all_text2))
        
        # Also include CVE ID from article field
        if article1.cve_id:
            cves1.add(article1.cve_id.upper())
        if article2.cve_id:
            cves2.add(article2.cve_id.upper())
        
        # CVE match boost
        cve_match_boost = 0.0
        if cves1 and cves2 and (cves1 & cves2):
            cve_match_boost = 0.5
        
        # Calculate Jaccard similarity for keywords
        keyword_similarity = self._calculate_jaccard_similarity(keywords1, keywords2)
        
        return min(1.0, keyword_similarity + cve_match_boost)
    
    def calculate_similarity(self, article1: Article, article2: Article) -> float:
        """
        计算两篇文章的相似度
        
        优先使用 AI embedding 计算语义相似度，如果 AI 不可用则使用传统方法：
        - 标题相似度权重：0.6（默认）
        - 关键词相似度权重：0.4（默认）
        
        Args:
            article1: 第一篇文章
            article2: 第二篇文章
        
        Returns:
            相似度分数 (0.0 - 1.0)
        
        Requirements:
            - 1.1: 计算每篇文章与现有文章的 Similarity_Score
            - 1.4: 支持基于 CVE ID、技术术语和关键词的多维度相似度计算
            - 1.5: 标题权重 0.6，关键词权重 0.4
        """
        # 优先使用 AI 计算相似度
        if self.use_ai_similarity and self._ai_client:
            ai_similarity = self._calculate_ai_similarity(article1, article2)
            if ai_similarity is not None:
                return ai_similarity
            logger.debug("AI 相似度计算失败，回退到传统方法")
        
        # 传统方法：基于关键词的相似度计算
        # Calculate title similarity
        title_similarity = self._calculate_title_similarity(
            article1.title, 
            article2.title
        )
        
        # Calculate keyword similarity
        keyword_similarity = self._calculate_keyword_similarity(
            article1, 
            article2
        )
        
        # Weighted average
        # Requirements 1.5: title_weight=0.6, keyword_weight=0.4
        final_similarity = (
            self.title_weight * title_similarity + 
            self.keyword_weight * keyword_similarity
        )
        
        return final_similarity
    
    def cluster_articles(self, articles: list[Article]) -> list[TopicCluster]:
        """
        对文章进行话题聚类
        
        使用 Union-Find 算法将相似文章聚合到同一话题。
        
        Args:
            articles: 文章列表
        
        Returns:
            话题聚类列表
        
        Requirements:
            - 1.2: 相似度 >= 阈值时聚合到同一话题
            - 1.3: 同一话题文章数 >= 聚合阈值时触发综述生成
            - 1.6: 只聚合时间窗口内的文章
        """
        from datetime import datetime, timedelta
        
        if not articles:
            return []
        
        # 过滤时间窗口内的文章
        cutoff_date = datetime.now() - timedelta(days=self.time_window_days)
        filtered_articles = []
        
        for article in articles:
            # 尝试解析文章日期
            pub_date = None
            if article.published_date:
                try:
                    if isinstance(article.published_date, str):
                        # 尝试多种日期格式
                        for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                            try:
                                pub_date = datetime.strptime(article.published_date[:19], fmt)
                                break
                            except ValueError:
                                continue
                    elif isinstance(article.published_date, datetime):
                        pub_date = article.published_date
                except Exception:
                    pass
            
            # 如果无法解析日期，默认包含
            if pub_date is None or pub_date >= cutoff_date:
                filtered_articles.append(article)
        
        if not filtered_articles:
            return []
        
        n = len(filtered_articles)
        
        # Union-Find 数据结构
        parent = list(range(n))
        rank = [0] * n
        
        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(x: int, y: int):
            px, py = find(x), find(y)
            if px == py:
                return
            if rank[px] < rank[py]:
                px, py = py, px
            parent[py] = px
            if rank[px] == rank[py]:
                rank[px] += 1
        
        # 计算相似度并合并
        logger.info(f"开始聚类 {n} 篇文章...")
        
        for i in range(n):
            for j in range(i + 1, n):
                similarity = self.calculate_similarity(
                    filtered_articles[i], 
                    filtered_articles[j]
                )
                if similarity >= self.similarity_threshold:
                    union(i, j)
                    logger.debug(
                        f"合并文章: '{filtered_articles[i].title[:30]}...' 和 "
                        f"'{filtered_articles[j].title[:30]}...' (相似度: {similarity:.2f})"
                    )
        
        # 构建聚类
        clusters_dict: dict[int, list[Article]] = {}
        for i in range(n):
            root = find(i)
            if root not in clusters_dict:
                clusters_dict[root] = []
            clusters_dict[root].append(filtered_articles[i])
        
        # 转换为 TopicCluster 对象
        clusters = []
        for articles_in_cluster in clusters_dict.values():
            if len(articles_in_cluster) >= 1:  # 至少有一篇文章
                # 提取关键词作为话题标签
                all_text = " ".join(a.title for a in articles_in_cluster)
                keywords = self.extract_keywords(all_text, top_k=5)
                
                cluster = TopicCluster(
                    id=f"topic_{id(articles_in_cluster)}",
                    topic_keywords=keywords,
                    articles=articles_in_cluster,
                    created_at=datetime.now()
                )
                clusters.append(cluster)
        
        logger.info(f"聚类完成: {len(clusters)} 个话题")
        return clusters
    
    def get_pending_clusters(
        self, 
        clusters: list[TopicCluster] | None = None
    ) -> list[TopicCluster]:
        """
        获取待整合的话题聚类（文章数 >= 聚合阈值）
        
        Args:
            clusters: 话题聚类列表（可选，如果不提供则返回空列表）
        
        Returns:
            待整合的话题聚类列表
        
        Requirements:
            - 1.3: 同一话题文章数 >= 聚合阈值时触发综述生成
        """
        if not clusters:
            return []
        
        pending = [
            cluster for cluster in clusters 
            if cluster.is_ready_for_synthesis(self.aggregation_threshold)
        ]
        
        logger.info(
            f"待整合话题: {len(pending)}/{len(clusters)} "
            f"(阈值: {self.aggregation_threshold})"
        )
        
        return pending
    
    def clear_embedding_cache(self):
        """清除 embedding 缓存"""
        self._embedding_cache.clear()
        logger.debug("Embedding 缓存已清除")
