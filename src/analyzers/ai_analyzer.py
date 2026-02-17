"""
AI分析器模块
AI Analyzer Module

使用OpenAI兼容API进行文章分析，包括摘要生成、分类和翻译。
Uses OpenAI-compatible API for article analysis including summary generation, 
categorization, and translation.

需求 4.1: 调用OpenAI兼容API生成文章摘要
需求 4.2: 根据摘要内容生成文章分类
需求 4.3: 支持自定义系统提示词和用户提示词模板
需求 4.4: 支持配置API地址、模型名称、最大Token数和温度参数
需求 4.5: AI API调用失败时记录错误并返回空结果
需求 4.6: 将英文摘要翻译为中文（如果配置了翻译功能）
"""

import json
import logging
from typing import Any

from openai import OpenAI, APIError, APITimeoutError, APIConnectionError

# 配置日志
logger = logging.getLogger(__name__)


# 默认提示词模板
DEFAULT_SYSTEM_PROMPT = """你是一名专业的技术文档分析师，擅长阅读和总结技术文章。
你的任务是：
1. 提取文章的核心观点和关键信息
2. 生成简洁准确的摘要
3. 为文章分配合适的技术分类

请确保摘要简洁明了，突出文章的主要贡献和价值。"""

DEFAULT_SUMMARY_PROMPT = """请为以下文章生成一个简洁的摘要（不超过200字）：

标题：{title}

内容：
{content}

请直接输出摘要内容，不要添加任何前缀或解释。"""

DEFAULT_CATEGORY_PROMPT = """请根据以下文章信息，为其分配一个最合适的技术分类。

标题：{title}
摘要：{summary}

可选分类：
- AI/机器学习
- 安全/隐私
- 系统/架构
- 编程语言
- 数据库/存储
- 网络/分布式
- 前端/移动端
- DevOps/云计算
- 其他

请只输出分类名称，不要添加任何解释。"""

DEFAULT_TRANSLATE_PROMPT = """请将以下英文文本翻译为中文，保持专业术语的准确性：

{text}

请直接输出翻译结果，不要添加任何前缀或解释。"""


DEFAULT_VULNERABILITY_ASSESSMENT_PROMPT = """请评估以下漏洞的实际危害程度，判断是否为"水洞"（低实际影响的漏洞）。

漏洞信息：
- CVE ID: {cve_id}
- 描述: {description}
- CVSS 评分: {cvss_score}
- 影响产品: {affected_products}

请从以下几个维度评估：
1. 利用难度：是否需要特殊条件或权限
2. 实际影响：是否能造成实质性危害
3. 影响范围：受影响系统的普遍程度
4. 利用价值：攻击者是否有动机利用

请以JSON格式输出评估结果：
{{
    "is_significant": true/false,
    "assessment": "简要评估说明（1-2句话）",
    "reasons": ["原因1", "原因2", ...]
}}

注意：如果漏洞具有实际危害价值，is_significant 应为 true；如果是"水洞"，应为 false。"""


class AIAnalyzer:
    """
    AI分析器：生成摘要、分类
    AI Analyzer: Generate summaries and categories
    
    使用OpenAI兼容API进行文章分析。
    Uses OpenAI-compatible API for article analysis.
    
    Attributes:
        client: OpenAI客户端实例
        model: 使用的模型名称
        max_tokens: 最大生成Token数
        temperature: 生成温度参数
        timeout: API调用超时时间（秒）
        translate_enabled: 是否启用翻译功能
        system_prompt: 系统提示词
        summary_prompt: 摘要生成提示词模板
        category_prompt: 分类生成提示词模板
        translate_prompt: 翻译提示词模板
    """
    
    def __init__(self, config: dict):
        """
        初始化分析器
        Initialize the analyzer
        
        Args:
            config: AI配置字典，包含以下字段：
                   AI config dict containing:
                   - api_base: API基础URL (e.g., https://api.siliconflow.cn/v1)
                   - api_key: API密钥
                   - model: 模型名称 (e.g., deepseek-ai/DeepSeek-V3)
                   - max_tokens: 最大Token数（可选，为空或0表示不限制）
                   - temperature: 温度参数（默认0.7）
                   - timeout: 超时时间秒数（默认60）
                   - translate: 是否启用翻译（默认True）
                   - system_prompt: 自定义系统提示词（可选）
                   - summary_prompt: 自定义摘要提示词模板（可选）
                   - category_prompt: 自定义分类提示词模板（可选）
                   - translate_prompt: 自定义翻译提示词模板（可选）
        
        Examples:
            >>> config = {
            ...     'api_base': 'https://api.siliconflow.cn/v1',
            ...     'api_key': 'sk-xxx',
            ...     'model': 'deepseek-ai/DeepSeek-V3',
            ...     'temperature': 0.7,
            ...     'timeout': 60,
            ...     'translate': True
            ... }
            >>> analyzer = AIAnalyzer(config)
        """
        # 提取配置参数
        api_base = config.get('api_base', 'https://api.openai.com/v1')
        api_key = config.get('api_key', '')
        
        # 初始化OpenAI客户端
        self.client = OpenAI(
            base_url=api_base,
            api_key=api_key
        )
        
        # 模型配置
        self.model = config.get('model', 'MiniMax-M2.5')
        
        # max_tokens处理：空字符串、None、0都表示不限制
        max_tokens_value = config.get('max_tokens')
        if max_tokens_value is None or max_tokens_value == '' or max_tokens_value == 0:
            self.max_tokens = None
        else:
            self.max_tokens = int(max_tokens_value)
        
        self.temperature = float(config.get('temperature', 0.7))
        self.timeout = float(config.get('timeout', 60))
        
        # 翻译功能开关
        self.translate_enabled = config.get('translate', True)
        
        # 提示词配置（支持自定义）
        self.system_prompt = config.get('system_prompt', DEFAULT_SYSTEM_PROMPT)
        self.summary_prompt = config.get('summary_prompt', DEFAULT_SUMMARY_PROMPT)
        self.category_prompt = config.get('category_prompt', DEFAULT_CATEGORY_PROMPT)
        self.translate_prompt = config.get('translate_prompt', DEFAULT_TRANSLATE_PROMPT)
        
        logger.info(f"AIAnalyzer initialized with model: {self.model}, api_base: {api_base}")
    
    def _call_api(self, user_prompt: str, system_prompt: str | None = None) -> str | None:
        """
        调用OpenAI API
        Call OpenAI API
        
        Args:
            user_prompt: 用户提示词
            system_prompt: 系统提示词（可选，默认使用实例的system_prompt）
        
        Returns:
            API响应文本，失败返回None
            API response text, returns None on failure
        """
        if system_prompt is None:
            system_prompt = self.system_prompt
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # 构建API调用参数
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "timeout": self.timeout
            }
            
            # 只有在设置了max_tokens时才添加该参数
            if self.max_tokens is not None:
                kwargs["max_tokens"] = self.max_tokens
            
            response = self.client.chat.completions.create(**kwargs)
            
            # 提取响应内容
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                return content.strip() if content else None
            
            logger.warning("API response has no choices")
            return None
            
        except APITimeoutError as e:
            logger.error(f"API call timeout: {e}")
            return None
        except APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            return None
        except APIError as e:
            logger.error(f"API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling API: {e}")
            return None
    
    def generate_summary(self, title: str, content: str) -> str | None:
        """
        生成文章摘要
        Generate article summary
        
        Args:
            title: 文章标题
                   Article title
            content: 文章内容（Markdown格式）
                     Article content (Markdown format)
        
        Returns:
            摘要文本，失败返回None
            Summary text, returns None on failure
        
        Examples:
            >>> analyzer = AIAnalyzer(config)
            >>> summary = analyzer.generate_summary(
            ...     "深度学习入门",
            ...     "本文介绍了深度学习的基本概念..."
            ... )
            >>> print(summary)
            "本文介绍了深度学习的基础知识，包括神经网络结构..."
        """
        if not title or not content:
            logger.warning("Empty title or content provided for summary generation")
            return None
        
        # 使用提示词模板生成用户提示词
        user_prompt = self.summary_prompt.format(title=title, content=content)
        
        logger.debug(f"Generating summary for article: {title[:50]}...")
        summary = self._call_api(user_prompt)
        
        if summary:
            logger.info(f"Successfully generated summary for: {title[:50]}...")
        else:
            logger.warning(f"Failed to generate summary for: {title[:50]}...")
        
        return summary
    
    def generate_category(self, title: str, summary: str) -> str:
        """
        生成文章分类
        Generate article category
        
        Args:
            title: 文章标题
                   Article title
            summary: 文章摘要
                     Article summary
        
        Returns:
            分类名称，失败返回"其他"
            Category name, returns "其他" on failure
        
        Examples:
            >>> analyzer = AIAnalyzer(config)
            >>> category = analyzer.generate_category(
            ...     "深度学习入门",
            ...     "本文介绍了深度学习的基础知识..."
            ... )
            >>> print(category)
            "AI/机器学习"
        """
        if not title:
            logger.warning("Empty title provided for category generation")
            return "其他"
        
        # 如果没有摘要，使用空字符串
        summary = summary or ""
        
        # 使用提示词模板生成用户提示词
        user_prompt = self.category_prompt.format(title=title, summary=summary)
        
        logger.debug(f"Generating category for article: {title[:50]}...")
        category = self._call_api(user_prompt)
        
        if category:
            logger.info(f"Generated category '{category}' for: {title[:50]}...")
            return category
        else:
            logger.warning(f"Failed to generate category for: {title[:50]}..., using default")
            return "其他"
    
    def translate_text(self, text: str) -> str | None:
        """
        翻译文本为中文
        Translate text to Chinese
        
        Args:
            text: 待翻译文本
                  Text to translate
        
        Returns:
            中文翻译，失败返回None
            Chinese translation, returns None on failure
        
        Examples:
            >>> analyzer = AIAnalyzer(config)
            >>> zh_text = analyzer.translate_text(
            ...     "This article introduces deep learning basics."
            ... )
            >>> print(zh_text)
            "本文介绍了深度学习的基础知识。"
        """
        if not text:
            logger.warning("Empty text provided for translation")
            return None
        
        # 使用提示词模板生成用户提示词
        user_prompt = self.translate_prompt.format(text=text)
        
        # 使用简单的翻译系统提示词
        translate_system_prompt = "你是一名专业的技术翻译，擅长将英文技术文档翻译为准确流畅的中文。"
        
        logger.debug(f"Translating text: {text[:50]}...")
        translation = self._call_api(user_prompt, system_prompt=translate_system_prompt)
        
        if translation:
            logger.info(f"Successfully translated text: {text[:30]}...")
        else:
            logger.warning(f"Failed to translate text: {text[:30]}...")
        
        return translation
    
    def analyze_article(self, title: str, content: str) -> dict:
        """
        完整分析文章
        Complete article analysis
        
        执行完整的分析流程：
        1. 生成摘要
        2. 生成分类
        3. 翻译摘要为中文（如果启用）
        
        Performs complete analysis workflow:
        1. Generate summary
        2. Generate category
        3. Translate summary to Chinese (if enabled)
        
        Args:
            title: 文章标题
                   Article title
            content: 文章内容
                     Article content
        
        Returns:
            分析结果字典，包含：
            Analysis result dict containing:
            - summary: 英文摘要（可能为None）
            - category: 分类（默认"其他"）
            - zh_summary: 中文摘要（可能为None）
        
        Examples:
            >>> analyzer = AIAnalyzer(config)
            >>> result = analyzer.analyze_article(
            ...     "Deep Learning Introduction",
            ...     "This article introduces deep learning basics..."
            ... )
            >>> print(result)
            {
                'summary': 'This article covers deep learning fundamentals...',
                'category': 'AI/机器学习',
                'zh_summary': '本文介绍了深度学习的基础知识...'
            }
        """
        result = {
            'summary': None,
            'category': '其他',
            'zh_summary': None
        }
        
        logger.info(f"Starting full analysis for article: {title[:50]}...")
        
        # 步骤1：生成摘要
        summary = self.generate_summary(title, content)
        result['summary'] = summary
        
        # 步骤2：生成分类（使用摘要，如果摘要失败则使用内容的前500字）
        if summary:
            category = self.generate_category(title, summary)
        else:
            # 如果摘要生成失败，使用内容的前500字作为参考
            truncated_content = content[:500] if content else ""
            category = self.generate_category(title, truncated_content)
        result['category'] = category
        
        # 步骤3：翻译摘要为中文（如果启用翻译且摘要存在）
        if self.translate_enabled and summary:
            zh_summary = self.translate_text(summary)
            result['zh_summary'] = zh_summary
        
        logger.info(f"Completed analysis for article: {title[:50]}... "
                   f"(summary: {'✓' if result['summary'] else '✗'}, "
                   f"category: {result['category']}, "
                   f"zh_summary: {'✓' if result['zh_summary'] else '✗'})")
        
        return result
    
    def assess_vulnerability(self, vuln: dict[str, Any]) -> dict[str, Any] | None:
        """
        评估漏洞实际危害
        Assess vulnerability actual impact
        
        使用 AI 评估漏洞是否为"水洞"（低实际影响的漏洞）。
        Uses AI to assess whether a vulnerability is a "water hole" (low actual impact).
        
        需求 Requirements:
        - 7.1: 漏洞通过基础过滤后使用 AI 评估
        - 7.2: AI 评估漏洞实际危害
        - 7.3: AI 判定为"水洞"时标记为低优先级
        - 7.4: 返回结构化评估结果
        - 7.5: AI 评估失败时保留该漏洞
        
        Args:
            vuln: 漏洞数据字典，包含以下字段：
                  Vulnerability data dict containing:
                  - cve_id: CVE ID (e.g., CVE-2024-1234)
                  - description: 漏洞描述
                  - cvss_score: CVSS 评分（可选）
                  - affected_products: 影响产品列表（可选）
        
        Returns:
            评估结果字典，包含：
            Assessment result dict containing:
            - is_significant: 是否具有实际危害 (bool)
            - assessment: 评估说明 (str)
            - reasons: 评估原因列表 (list[str])
            
            失败时返回 None
            Returns None on failure
        
        Examples:
            >>> analyzer = AIAnalyzer(config)
            >>> result = analyzer.assess_vulnerability({
            ...     'cve_id': 'CVE-2024-1234',
            ...     'description': 'Remote code execution in...',
            ...     'cvss_score': 9.8
            ... })
            >>> print(result)
            {
                'is_significant': True,
                'assessment': '该漏洞允许远程代码执行，具有高危害性',
                'reasons': ['利用难度低', '影响范围广', '可造成完全系统控制']
            }
        """
        # 提取漏洞信息
        cve_id = vuln.get('cve_id', 'Unknown')
        description = vuln.get('description', '') or vuln.get('short_description', '')
        cvss_score = vuln.get('cvss_score', 'N/A')
        affected_products = vuln.get('affected_products', [])
        
        if not description:
            logger.warning(f"Empty description for vulnerability {cve_id}")
            return None
        
        # 格式化影响产品
        if isinstance(affected_products, list):
            affected_products_str = ', '.join(affected_products[:5])  # 最多显示5个
            if len(affected_products) > 5:
                affected_products_str += f' 等 {len(affected_products)} 个产品'
        else:
            affected_products_str = str(affected_products) if affected_products else 'N/A'
        
        # 构建提示词
        user_prompt = DEFAULT_VULNERABILITY_ASSESSMENT_PROMPT.format(
            cve_id=cve_id,
            description=description[:1000],  # 限制描述长度
            cvss_score=cvss_score,
            affected_products=affected_products_str
        )
        
        # 使用专门的系统提示词
        system_prompt = """你是一名资深的网络安全分析师，擅长评估漏洞的实际危害程度。
你的任务是判断漏洞是否具有实际利用价值，还是仅仅是理论上的风险（"水洞"）。
请基于漏洞的利用难度、实际影响、影响范围和利用价值进行客观评估。
请始终以有效的 JSON 格式输出结果。"""
        
        logger.debug(f"Assessing vulnerability: {cve_id}")
        
        try:
            response = self._call_api(user_prompt, system_prompt=system_prompt)
            
            if not response:
                logger.warning(f"AI assessment returned empty response for {cve_id}")
                return None
            
            # 解析 JSON 响应
            # 尝试提取 JSON 部分（处理可能的额外文本）
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning(f"No JSON found in AI response for {cve_id}: {response[:100]}")
                return None
            
            json_str = response[json_start:json_end]
            result = json.loads(json_str)
            
            # 验证结果结构
            if 'is_significant' not in result:
                logger.warning(f"Missing 'is_significant' in AI response for {cve_id}")
                return None
            
            # 确保字段类型正确
            assessment_result = {
                'is_significant': bool(result.get('is_significant', True)),
                'assessment': str(result.get('assessment', '')),
                'reasons': list(result.get('reasons', []))
            }
            
            logger.info(f"AI assessment for {cve_id}: is_significant={assessment_result['is_significant']}")
            return assessment_result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response as JSON for {cve_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in AI assessment for {cve_id}: {e}")
            return None

    def score_article_priority(self, article: dict[str, Any]) -> dict[str, Any] | None:
        """
        评估文章优先级
        Score article priority
        
        使用 AI 评估文章的优先级，考虑来源权威性、内容相关性和时效性。
        Uses AI to score article priority considering source authority, 
        content relevance, and timeliness.
        
        需求 Requirements:
        - 8.1: 对文章进行优先级评分 (0-100)
        - 8.2: 考虑来源权威性、相关性、时效性
        - 8.3: 返回评分和评分理由
        
        Args:
            article: 文章数据字典，包含以下字段：
                    Article data dict containing:
                    - title: 文章标题
                    - summary: 文章摘要（可选）
                    - source: 数据源
                    - source_type: 数据源类型
                    - published_date: 发布日期（可选）
        
        Returns:
            评分结果字典，包含：
            Score result dict containing:
            - score: 优先级评分 (int, 0-100)
            - reasons: 评分原因列表 (list[str])
            
            失败时返回 None
            Returns None on failure
        
        Examples:
            >>> analyzer = AIAnalyzer(config)
            >>> result = analyzer.score_article_priority({
            ...     'title': 'Critical Security Vulnerability',
            ...     'summary': 'A critical RCE vulnerability...',
            ...     'source_type': 'kev'
            ... })
            >>> print(result)
            {
                'score': 85,
                'reasons': ['高危漏洞', '来源权威', '时效性强']
            }
        """
        title = article.get('title', '')
        summary = article.get('summary', '') or article.get('zh_summary', '')
        source = article.get('source', '')
        source_type = article.get('source_type', '')
        published_date = article.get('published_date', '')
        
        if not title:
            logger.warning("Empty title for priority scoring")
            return None
        
        # 构建提示词
        user_prompt = f"""请评估以下文章的优先级，给出 0-100 的评分。

文章信息：
- 标题: {title}
- 摘要: {summary[:500] if summary else 'N/A'}
- 来源: {source}
- 来源类型: {source_type}
- 发布日期: {published_date or 'N/A'}

评分标准：
1. 来源权威性 (0-30分)：顶会论文、官方安全公告、知名博客等权威来源得分更高
2. 内容相关性 (0-40分)：与安全、AI、技术前沿相关的内容得分更高
3. 时效性 (0-30分)：最新发布的内容得分更高

请以JSON格式输出评分结果：
{{
    "score": 0-100的整数,
    "reasons": ["原因1", "原因2", ...]
}}

注意：score 必须是 0-100 之间的整数。"""

        system_prompt = """你是一名技术内容评估专家，擅长评估技术文章的重要性和优先级。
请基于来源权威性、内容相关性和时效性进行客观评估。
请始终以有效的 JSON 格式输出结果。"""
        
        logger.debug(f"Scoring priority for article: {title[:50]}...")
        
        try:
            response = self._call_api(user_prompt, system_prompt=system_prompt)
            
            if not response:
                logger.warning(f"AI scoring returned empty response for: {title[:50]}")
                return None
            
            # 解析 JSON 响应
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning(f"No JSON found in AI response for: {title[:50]}")
                return None
            
            json_str = response[json_start:json_end]
            result = json.loads(json_str)
            
            # 验证结果结构
            if 'score' not in result:
                logger.warning(f"Missing 'score' in AI response for: {title[:50]}")
                return None
            
            # 确保分数在 0-100 范围内
            score = int(result.get('score', 50))
            score = max(0, min(100, score))
            
            score_result = {
                'score': score,
                'reasons': list(result.get('reasons', []))
            }
            
            logger.info(f"AI priority score for '{title[:30]}...': {score}")
            return score_result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in AI priority scoring: {e}")
            return None

    def generate_brief_summary(self, article: dict[str, Any]) -> str:
        """
        生成简要摘要（1-2句话）
        Generate brief summary (1-2 sentences)
        
        为 Level 2 推送生成简短摘要。
        Generates short summary for Level 2 push.
        
        需求 Requirements:
        - 9.2: Level 1 详细摘要
        - 10.2: Level 2 简要摘要
        
        Args:
            article: 文章数据字典
        
        Returns:
            简要摘要字符串，失败返回空字符串
        
        Examples:
            >>> analyzer = AIAnalyzer(config)
            >>> brief = analyzer.generate_brief_summary({
            ...     'title': 'New AI Model',
            ...     'summary': 'This paper introduces a new...'
            ... })
            >>> print(brief)
            "介绍了一种新的AI模型，显著提升了性能。"
        """
        title = article.get('title', '')
        summary = article.get('summary', '') or article.get('zh_summary', '')
        content = article.get('content', '')
        
        if not title:
            return ""
        
        # 如果已有摘要，基于摘要生成简要版本
        source_text = summary if summary else content[:500]
        
        if not source_text:
            return ""
        
        user_prompt = f"""请为以下文章生成一个简要摘要（1-2句话，不超过50字）：

标题：{title}
内容：{source_text[:500]}

请直接输出简要摘要，不要添加任何前缀或解释。"""

        logger.debug(f"Generating brief summary for: {title[:50]}...")
        
        try:
            result = self._call_api(user_prompt)
            if result:
                # 确保不超过100字
                return result[:100].strip()
            return ""
        except Exception as e:
            logger.warning(f"Failed to generate brief summary: {e}")
            return ""

    def extract_keywords(self, article: dict[str, Any]) -> list[str]:
        """
        提取关键词
        Extract keywords
        
        从文章中提取关键词用于 Level 1 推送。
        Extracts keywords from article for Level 1 push.
        
        需求 Requirements:
        - 9.2: Level 1 包含关键词
        
        Args:
            article: 文章数据字典
        
        Returns:
            关键词列表，失败返回空列表
        
        Examples:
            >>> analyzer = AIAnalyzer(config)
            >>> keywords = analyzer.extract_keywords({
            ...     'title': 'Deep Learning for NLP',
            ...     'summary': 'This paper presents...'
            ... })
            >>> print(keywords)
            ['深度学习', 'NLP', '自然语言处理']
        """
        title = article.get('title', '')
        summary = article.get('summary', '') or article.get('zh_summary', '')
        
        if not title:
            return []
        
        source_text = summary if summary else title
        
        user_prompt = f"""请从以下文章中提取3-5个关键词：

标题：{title}
摘要：{source_text[:300]}

请以JSON数组格式输出关键词，例如：["关键词1", "关键词2", "关键词3"]

只输出JSON数组，不要添加任何其他内容。"""

        logger.debug(f"Extracting keywords for: {title[:50]}...")
        
        try:
            result = self._call_api(user_prompt)
            if not result:
                return []
            
            # 尝试解析 JSON 数组
            json_start = result.find('[')
            json_end = result.rfind(']') + 1
            
            if json_start == -1 or json_end == 0:
                return []
            
            json_str = result[json_start:json_end]
            keywords = json.loads(json_str)
            
            if isinstance(keywords, list):
                return [str(k) for k in keywords[:5]]  # 最多5个关键词
            return []
            
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse keywords JSON")
            return []
        except Exception as e:
            logger.warning(f"Failed to extract keywords: {e}")
            return []
