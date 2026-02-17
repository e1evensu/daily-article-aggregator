"""
综述生成器模块

负责从话题聚类中生成综述文档。
使用 AI 分析多篇相关文章，提取核心观点并生成结构化综述。

Requirements:
- 3.1: 从聚类文章中提取核心观点
- 3.2: 生成结构化综述（背景、影响分析、技术细节、缓解措施）
- 3.3: 保留所有原始文章的引用链接
- 3.5: AI 生成失败时保留原始文章列表
- 3.6: 综述标题反映话题核心内容
"""

import json
import logging
from datetime import datetime
from typing import Any

from openai import OpenAI, APIError

from src.aggregation.models import TopicCluster, Synthesis

logger = logging.getLogger(__name__)

# 默认综述生成提示词
DEFAULT_SYNTHESIS_SYSTEM_PROMPT = """你是一名专业的技术文档分析师，擅长从多篇相关文章中提取核心信息并生成综述。
你的任务是：
1. 分析多篇相关文章的核心观点
2. 生成结构化的综述文档
3. 确保综述涵盖所有重要信息
4. 保持客观、准确、专业的语言风格"""

DEFAULT_SYNTHESIS_PROMPT = """请根据以下 {article_count} 篇相关文章生成一篇综述。

文章列表：
{articles_text}

请生成一篇结构化的综述，包含以下部分：
1. **标题**：反映话题核心内容的标题
2. **背景**：简要介绍话题背景和重要性
3. **核心观点**：提取各文章的核心观点（列表形式）
4. **影响分析**：分析该话题的影响和意义
5. **技术细节**：如有技术内容，简要说明关键技术点
6. **总结**：简要总结和展望

请以 JSON 格式输出：
{{
    "title": "综述标题",
    "background": "背景介绍",
    "key_points": ["核心观点1", "核心观点2", ...],
    "impact_analysis": "影响分析",
    "technical_details": "技术细节（如无则为空字符串）",
    "summary": "总结"
}}"""


class SynthesisGenerator:
    """
    综述生成器
    
    从话题聚类中生成综述文档。
    
    Attributes:
        ai_client: OpenAI 客户端
        model: 使用的模型名称
        max_tokens: 最大生成 Token 数
        temperature: 生成温度参数
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化综述生成器
        
        Args:
            config: 配置字典，包含：
                - api_base: API 基础 URL
                - api_key: API 密钥
                - model: 模型名称
                - max_tokens: 最大 Token 数
                - temperature: 温度参数
        """
        config = config or {}
        
        api_base = config.get('api_base', 'https://api.openai.com/v1')
        api_key = config.get('api_key', '')
        
        self._ai_client: OpenAI | None = None
        if api_key:
            try:
                self._ai_client = OpenAI(
                    base_url=api_base,
                    api_key=api_key
                )
                logger.info(f"SynthesisGenerator AI 客户端初始化成功")
            except Exception as e:
                logger.error(f"AI 客户端初始化失败: {e}")
        
        self.model = config.get('model', 'MiniMax-M2.5')
        self.max_tokens = config.get('max_tokens', 4000)
        self.temperature = config.get('temperature', 0.7)
        
        self.system_prompt = config.get(
            'system_prompt', DEFAULT_SYNTHESIS_SYSTEM_PROMPT
        )
        self.synthesis_prompt = config.get(
            'synthesis_prompt', DEFAULT_SYNTHESIS_PROMPT
        )
    
    def extract_key_points(self, cluster: TopicCluster) -> list[str]:
        """
        从聚类文章中提取核心观点
        
        Args:
            cluster: 话题聚类
        
        Returns:
            核心观点列表
        
        Requirements:
            - 3.1: 从聚类文章中提取核心观点
        """
        if not cluster.articles:
            return []
        
        key_points = []
        
        for article in cluster.articles:
            # 优先使用中文摘要，其次英文摘要，最后标题
            point = article.zh_summary or article.summary or article.title
            if point:
                key_points.append(point)
        
        return key_points
    
    def generate_title(self, cluster: TopicCluster) -> str:
        """
        生成综述标题
        
        Args:
            cluster: 话题聚类
        
        Returns:
            综述标题
        
        Requirements:
            - 3.6: 综述标题反映话题核心内容
        """
        if not cluster.articles:
            return "综述"
        
        # 如果有关键词，使用关键词生成标题
        if cluster.topic_keywords:
            keywords_str = "、".join(cluster.topic_keywords[:3])
            return f"关于「{keywords_str}」的综述"
        
        # 否则使用第一篇文章的标题
        first_title = cluster.articles[0].title
        return f"关于「{first_title[:30]}」的综述"
    
    def format_references(self, cluster: TopicCluster) -> list[dict[str, str]]:
        """
        格式化参考来源列表
        
        Args:
            cluster: 话题聚类
        
        Returns:
            参考来源列表，每项包含 title 和 url
        
        Requirements:
            - 3.3: 保留所有原始文章的引用链接
        """
        references = []
        
        for article in cluster.articles:
            ref = {
                "title": article.title,
                "url": article.url,
                "source": article.source or "",
                "published_date": article.published_date or ""
            }
            references.append(ref)
        
        return references
    
    def _build_articles_text(self, cluster: TopicCluster) -> str:
        """
        构建文章列表文本
        
        Args:
            cluster: 话题聚类
        
        Returns:
            格式化的文章列表文本
        """
        articles_text = []
        
        for i, article in enumerate(cluster.articles, 1):
            summary = article.zh_summary or article.summary or ""
            text = f"""
【文章 {i}】
标题：{article.title}
来源：{article.source or '未知'}
摘要：{summary[:500] if summary else '无摘要'}
链接：{article.url}
"""
            articles_text.append(text)
        
        return "\n".join(articles_text)
    
    def generate_synthesis(self, cluster: TopicCluster) -> Synthesis:
        """
        生成综述
        
        Args:
            cluster: 话题聚类
        
        Returns:
            Synthesis 对象
        
        Requirements:
            - 3.2: 生成结构化综述
            - 3.5: AI 生成失败时保留原始文章列表
        """
        # 准备参考来源
        references = self.format_references(cluster)
        
        # 默认综述（AI 失败时使用）
        default_synthesis = Synthesis(
            id=f"synthesis_{cluster.id}",
            cluster_id=cluster.id,
            title=self.generate_title(cluster),
            content=self._generate_fallback_content(cluster),
            key_points=self.extract_key_points(cluster),
            references=references,
            generated_at=datetime.now()
        )
        
        # 如果 AI 不可用，返回默认综述
        if not self._ai_client:
            logger.warning("AI 客户端不可用，使用默认综述")
            return default_synthesis
        
        try:
            # 构建提示词
            articles_text = self._build_articles_text(cluster)
            user_prompt = self.synthesis_prompt.format(
                article_count=len(cluster.articles),
                articles_text=articles_text
            )
            
            # 调用 AI
            response = self._ai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            if not response.choices or not response.choices[0].message.content:
                logger.warning("AI 返回空响应，使用默认综述")
                return default_synthesis
            
            # 解析 JSON 响应
            content = response.choices[0].message.content
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("AI 响应中未找到 JSON，使用默认综述")
                return default_synthesis
            
            result = json.loads(content[json_start:json_end])
            
            # 构建综述内容
            synthesis_content = self._format_synthesis_content(result)
            
            synthesis = Synthesis(
                id=f"synthesis_{cluster.id}",
                cluster_id=cluster.id,
                title=result.get('title', default_synthesis.title),
                content=synthesis_content,
                key_points=result.get('key_points', default_synthesis.key_points),
                references=references,
                generated_at=datetime.now()
            )
            
            logger.info(f"综述生成成功: {synthesis.title}")
            return synthesis
            
        except json.JSONDecodeError as e:
            logger.warning(f"解析 AI 响应失败: {e}，使用默认综述")
            return default_synthesis
        except APIError as e:
            logger.error(f"AI API 调用失败: {e}，使用默认综述")
            return default_synthesis
        except Exception as e:
            logger.error(f"生成综述时发生错误: {e}，使用默认综述")
            return default_synthesis
    
    def _format_synthesis_content(self, result: dict) -> str:
        """
        格式化综述内容为 Markdown
        
        Args:
            result: AI 返回的结构化结果
        
        Returns:
            Markdown 格式的综述内容
        """
        sections = []
        
        # 背景
        if result.get('background'):
            sections.append(f"## 背景\n\n{result['background']}")
        
        # 核心观点
        if result.get('key_points'):
            points = "\n".join(f"- {p}" for p in result['key_points'])
            sections.append(f"## 核心观点\n\n{points}")
        
        # 影响分析
        if result.get('impact_analysis'):
            sections.append(f"## 影响分析\n\n{result['impact_analysis']}")
        
        # 技术细节
        if result.get('technical_details'):
            sections.append(f"## 技术细节\n\n{result['technical_details']}")
        
        # 总结
        if result.get('summary'):
            sections.append(f"## 总结\n\n{result['summary']}")
        
        return "\n\n".join(sections)
    
    def _generate_fallback_content(self, cluster: TopicCluster) -> str:
        """
        生成备用综述内容（AI 失败时使用）
        
        Args:
            cluster: 话题聚类
        
        Returns:
            Markdown 格式的备用内容
        """
        sections = []
        
        # 标题
        title = self.generate_title(cluster)
        sections.append(f"# {title}")
        
        # 关键词
        if cluster.topic_keywords:
            keywords_str = "、".join(cluster.topic_keywords)
            sections.append(f"**关键词**: {keywords_str}")
        
        # 文章列表
        sections.append("## 相关文章")
        for i, article in enumerate(cluster.articles, 1):
            summary = article.zh_summary or article.summary or "无摘要"
            sections.append(f"""
### {i}. {article.title}

- **来源**: {article.source or '未知'}
- **链接**: [{article.url}]({article.url})
- **摘要**: {summary[:200]}...
""")
        
        return "\n".join(sections)
