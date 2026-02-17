"""
AI Scorer - AI 实时评分器
AI Scorer - Real-time AI Scoring Module

基于三维评分系统对文章进行实时评分：
- relevance (相关性): 文章与目标领域的主题相关性
- quality (质量): 文章内容的质量和深度
- timeliness (时效性): 文章的新鲜度和时效价值

Features:
1. 三维评分: relevance, quality, timeliness
2. 批量评分: 支持一次调用评分多篇文章
3. 分类: ai-ml, security, engineering, tools, opinion, other
4. 关键词提取
5. 与现有系统兼容
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Union, List, Dict

logger = logging.getLogger(__name__)


# 分类常量
CATEGORIES = ['ai-ml', 'security', 'engineering', 'tools', 'opinion', 'other']

# 默认评分提示词模板
DEFAULT_SCORING_SYSTEM_PROMPT = """你是一名技术内容评估专家，擅长评估技术文章的重要性和质量。
你的任务是：
1. 对文章进行三维评分：相关性(relevance)、质量(quality)、时效性(timeliness)
2. 为文章分配合适的技术分类
3. 提取文章的核心关键词

请始终以有效的 JSON 格式输出结果。"""

DEFAULT_SCORING_PROMPT = """请对以下文章进行三维评分和分类。

文章信息：
- 标题: {title}
- 摘要: {summary}
- 来源: {source}
- 来源类型: {source_type}
- 发布日期: {published_date}

评分标准：
1. relevance (相关性, 0-100): 文章与AI/机器学习、安全、工程实践、工具等主题的相关程度
   - AI/ML相关: 85-100
   - 安全相关: 80-95
   - 工程实践: 70-90
   - 工具推荐: 65-85
   - 观点评论: 60-80
   - 其他: 40-60

2. quality (质量, 0-100): 文章内容的质量和深度
   - 学术论文/官方公告: 85-100
   - 技术博客/教程: 70-90
   - 新闻报道: 60-80
   - 社交媒体: 40-60

3. timeliness (时效性, 0-100): 文章的新鲜度和时效价值
   - 24小时内: 90-100
   - 7天内: 70-90
   - 30天内: 50-70
   - 30天前: 30-50

分类选项 (category):
- ai-ml: AI/机器学习相关
- security: 安全/隐私相关
- engineering: 工程实践/架构相关
- tools: 工具/产品相关
- opinion: 观点/评论相关
- other: 其他

关键词要求：
- 提取3-5个核心关键词
- 关键词应该反映文章的主要主题和技术点

请以JSON格式输出评分结果：
{{
    "relevance": 0-100的整数,
    "quality": 0-100的整数,
    "timeliness": 0-100的整数,
    "total_score": 0-100的整数 (三维度加权平均: relevance*0.4 + quality*0.35 + timeliness*0.25),
    "category": "分类名称",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "reasons": ["评分原因1", "评分原因2", ...]
}}

注意：所有分数必须是 0-100 之间的整数。"""


@dataclass
class AIScoreResult:
    """
    AI 评分结果数据类
    AI Score Result Data Class

    Attributes:
        url: 文章 URL
        relevance: 相关性评分 (0-100)
        quality: 质量评分 (0-100)
        timeliness: 时效性评分 (0-100)
        total_score: 总分 (0-100)
        category: 分类
        keywords: 关键词列表
        reasons: 评分原因列表
    """
    url: str = ""
    relevance: int = 50
    quality: int = 50
    timeliness: int = 50
    total_score: int = 50
    category: str = "other"
    keywords: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIScoreResult":
        """从字典创建"""
        return cls(**data)


class AIScorer:
    """
    AI 实时评分器
    Real-time AI Scorer

    三维评分系统：
    - relevance (相关性): 文章与目标领域的主题相关性 (权重 40%)
    - quality (质量): 文章内容的质量和深度 (权重 35%)
    - timeliness (时效性): 文章的新鲜度和时效价值 (权重 25%)

    Attributes:
        client: OpenAI 客户端
        model: 使用的模型
        batch_size: 批量评分大小
        timeout: API 超时时间
        scoring_prompt: 评分提示词模板
    """

    # 权重配置
    RELEVANCE_WEIGHT = 0.40
    QUALITY_WEIGHT = 0.35
    TIMELINESS_WEIGHT = 0.25

    def __init__(self, config: Dict[str, Any], openai_client: Any = None):
        """
        初始化 AI 评分器

        Args:
            config: 配置字典，包含以下字段：
                   - api_base: API 基础 URL
                   - api_key: API 密钥
                   - model: 模型名称
                   - batch_size: 批量大小 (默认 10)
                   - timeout: 超时时间 (默认 60)
                   - scoring_prompt: 自定义评分提示词 (可选)
            openai_client: OpenAI 客户端实例 (可选，用于测试)
        """
        if openai_client:
            self.client = openai_client
        else:
            from openai import OpenAI
            api_base = config.get('api_base', 'https://api.openai.com/v1')
            api_key = config.get('api_key', '')
            self.client = OpenAI(base_url=api_base, api_key=api_key)

        self.model = config.get('model', 'MiniMax-M2.5')
        self.batch_size = config.get('batch_size', 10)
        self.timeout = config.get('timeout', 60)
        self.scoring_prompt = config.get('scoring_prompt', DEFAULT_SCORING_PROMPT)
        self.system_prompt = config.get('system_prompt', DEFAULT_SCORING_SYSTEM_PROMPT)

        logger.info(f"AIScorer initialized: model={self.model}, batch_size={self.batch_size}")

    def _call_api(self, user_prompt: str) -> Optional[str]:
        """
        调用 OpenAI API

        Args:
            user_prompt: 用户提示词

        Returns:
            API 响应文本，失败返回 None
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                timeout=self.timeout
            )

            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                return content.strip() if content else None

            return None

        except Exception as e:
            logger.error(f"API call failed: {e}")
            return None

    def _parse_response(self, response: str, url: str) -> Optional[AIScoreResult]:
        """
        解析 API 响应

        Args:
            response: API 响应文本
            url: 文章 URL

        Returns:
            评分结果，解析失败返回 None
        """
        try:
            # 提取 JSON 部分
            json_start = response.find('{')
            json_end = response.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                logger.warning(f"No JSON found in API response")
                return None

            json_str = response[json_start:json_end]
            result = json.loads(json_str)

            # 验证必需字段
            required_fields = ['relevance', 'quality', 'timeliness', 'total_score', 'category']
            for field_name in required_fields:
                if field_name not in result:
                    logger.warning(f"Missing required field: {field_name}")
                    return None

            # 确保分数在有效范围内
            relevance = max(0, min(100, int(result.get('relevance', 50))))
            quality = max(0, min(100, int(result.get('quality', 50))))
            timeliness = max(0, min(100, int(result.get('timeliness', 50))))
            total_score = max(0, min(100, int(result.get('total_score', 50))))

            # 验证分类
            category = result.get('category', 'other')
            if category not in CATEGORIES:
                category = 'other'

            # 提取关键词
            keywords = result.get('keywords', [])
            if isinstance(keywords, list):
                keywords = [str(k) for k in keywords[:5]]
            else:
                keywords = []

            # 提取原因
            reasons = result.get('reasons', [])
            if not isinstance(reasons, list):
                reasons = []

            return AIScoreResult(
                url=url,
                relevance=relevance,
                quality=quality,
                timeliness=timeliness,
                total_score=total_score,
                category=category,
                keywords=keywords,
                reasons=reasons
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to parse response: {e}")
            return None

    def score_single(self, article: Dict[str, Any]) -> Optional[AIScoreResult]:
        """
        评分单篇文章

        Args:
            article: 文章数据字典，包含：
                    - title: 标题
                    - url: URL
                    - summary/zh_summary: 摘要
                    - source: 来源
                    - source_type: 来源类型
                    - published_date: 发布日期

        Returns:
            评分结果，失败返回 None
        """
        title = article.get('title', '')
        url = article.get('url', '')
        summary = article.get('zh_summary') or article.get('summary', '')
        source = article.get('source', '')
        source_type = article.get('source_type', '')
        published_date = article.get('published_date', '')

        if not title:
            logger.warning("Empty title for scoring")
            return None

        # 构建提示词
        user_prompt = self.scoring_prompt.format(
            title=title,
            summary=summary[:500] if summary else 'N/A',
            source=source or 'N/A',
            source_type=source_type or 'N/A',
            published_date=published_date or 'N/A'
        )

        logger.debug(f"Scoring article: {title[:50]}...")

        response = self._call_api(user_prompt)
        if not response:
            logger.warning(f"Failed to get AI response for: {title[:50]}")
            return None

        return self._parse_response(response, url)

    def score_batch(
        self,
        articles: List[Dict[str, Any]],
        progress_callback: Any = None
    ) -> List[AIScoreResult]:
        """
        批量评分多篇文章

        Args:
            articles: 文章列表
            progress_callback: 进度回调函数 (可选)

        Returns:
            评分结果列表
        """
        results: List[AIScoreResult] = []
        total = len(articles)

        logger.info(f"Starting batch scoring for {total} articles")

        for i, article in enumerate(articles):
            result = self.score_single(article)

            if result:
                results.append(result)
            else:
                # 评分失败时创建默认结果
                url = article.get('url', f'unknown_{i}')
                results.append(AIScoreResult(
                    url=url,
                    relevance=50,
                    quality=50,
                    timeliness=50,
                    total_score=50,
                    category='other',
                    keywords=[],
                    reasons=['AI评分失败，使用默认分数']
                ))

            # 进度回调
            if progress_callback:
                progress_callback(i + 1, total)

            # 避免 API 限流
            if i < total - 1:
                import time
                time.sleep(0.5)

        logger.info(f"Batch scoring completed: {len(results)}/{total} articles")
        return results

    def score_articles_with_fallback(
        self,
        articles: List[Dict[str, Any]],
        existing_scores: Dict[str, AIScoreResult] | None = None
    ) -> List[AIScoreResult]:
        """
        对文章进行评分，已有评分的文章复用

        Args:
            articles: 文章列表
            existing_scores: 已有的评分结果字典 {url: AIScoreResult}

        Returns:
            评分结果列表
        """
        existing_scores = existing_scores or {}
        new_articles = []
        results: List[AIScoreResult] = []

        # 分离已有评分和需要新评分的文章
        for article in articles:
            url = article.get('url', '')
            if url and url in existing_scores:
                results.append(existing_scores[url])
            else:
                new_articles.append(article)

        # 批量评分新文章
        if new_articles:
            new_results = self.score_batch(new_articles)
            results.extend(new_results)

        logger.info(
            f"Scored {len(articles)} articles: "
            f"{len(articles) - len(new_articles)} reused, {len(new_articles)} newly scored"
        )

        return results


def calculate_total_score(relevance: int, quality: int, timeliness: int) -> int:
    """
    计算总分

    权重: relevance 40%, quality 35%, timeliness 25%

    Args:
        relevance: 相关性评分
        quality: 质量评分
        timeliness: 时效性评分

    Returns:
        总分 (0-100)
    """
    total = (
        relevance * AIScorer.RELEVANCE_WEIGHT +
        quality * AIScorer.QUALITY_WEIGHT +
        timeliness * AIScorer.TIMELINESS_WEIGHT
    )
    return int(round(total))


def normalize_category(category: str) -> str:
    """
    规范化分类名称

    Args:
        category: 原始分类名称

    Returns:
        规范化后的分类名称
    """
    category_lower = category.lower().strip()

    # 分类映射
    category_mapping = {
        'ai': 'ai-ml',
        'ml': 'ai-ml',
        'machine learning': 'ai-ml',
        'artificial intelligence': 'ai-ml',
        'llm': 'ai-ml',
        'security': 'security',
        'security': 'security',
        'cybersecurity': 'security',
        'vulnerability': 'security',
        'engineering': 'engineering',
        'architecture': 'engineering',
        'devops': 'engineering',
        'tools': 'tools',
        'tool': 'tools',
        'opinion': 'opinion',
        'opinion': 'opinion',
        'commentary': 'opinion',
    }

    return category_mapping.get(category_lower, 'other')
