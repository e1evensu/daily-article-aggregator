"""
话题聚合系统数据模型模块

定义话题聚类、综述、过滤结果、发布结果和 RSS 条目的数据模型。
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

# Import Article from the main models module for compatibility
from src.models import Article


# Default aggregation threshold for is_ready_for_synthesis
DEFAULT_AGGREGATION_THRESHOLD = 3


@dataclass
class TopicCluster:
    """
    话题聚类数据模型
    
    表示一组讨论相同主题的文章集合。
    
    Attributes:
        id: 聚类唯一标识
        topic_keywords: 话题关键词列表
        cve_ids: 相关 CVE ID 列表（如有）
        articles: 聚类中的文章列表
        created_at: 创建时间
        updated_at: 更新时间
        status: 状态：pending/processing/completed/failed
        similarity_matrix: 文章间相似度矩阵 {(article_url1, article_url2): score}
        aggregation_threshold: 聚合阈值，用于判断是否准备好进行综述
    """
    id: str
    topic_keywords: list[str] = field(default_factory=list)
    cve_ids: list[str] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"
    similarity_matrix: dict = field(default_factory=dict)
    aggregation_threshold: int = DEFAULT_AGGREGATION_THRESHOLD
    
    @property
    def article_count(self) -> int:
        """返回聚类中的文章数量"""
        return len(self.articles)
    
    @property
    def is_ready_for_synthesis(self) -> bool:
        """
        判断是否达到整合阈值，准备好进行综述生成
        
        Returns:
            当文章数量达到或超过聚合阈值时返回 True
        
        Validates: Requirements 1.3
        """
        return self.article_count >= self.aggregation_threshold
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 TopicCluster 对象转换为字典
        
        Returns:
            包含所有字段的字典，datetime 转换为 ISO 格式字符串，
            Article 对象转换为字典
        
        Validates: Requirements 6.6
        """
        return {
            "id": self.id,
            "topic_keywords": self.topic_keywords,
            "cve_ids": self.cve_ids,
            "articles": [article.to_dict() for article in self.articles],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status,
            "similarity_matrix": {
                # Convert tuple keys to string for JSON serialization
                f"{k[0]}|{k[1]}" if isinstance(k, tuple) else str(k): v
                for k, v in self.similarity_matrix.items()
            },
            "aggregation_threshold": self.aggregation_threshold,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TopicCluster":
        """
        从字典创建 TopicCluster 对象
        
        Args:
            data: 包含聚类数据的字典
            
        Returns:
            TopicCluster 对象
        
        Validates: Requirements 6.6
        """
        # Parse datetime fields
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
            
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now()
        
        # Parse articles
        articles_data = data.get("articles", [])
        articles = [
            Article.from_dict(a) if isinstance(a, dict) else a
            for a in articles_data
        ]
        
        # Parse similarity matrix - convert string keys back to tuples
        raw_matrix = data.get("similarity_matrix", {})
        similarity_matrix = {}
        for k, v in raw_matrix.items():
            if isinstance(k, str) and "|" in k:
                parts = k.split("|", 1)
                similarity_matrix[(parts[0], parts[1])] = v
            else:
                similarity_matrix[k] = v
        
        return cls(
            id=data.get("id", ""),
            topic_keywords=data.get("topic_keywords", []),
            cve_ids=data.get("cve_ids", []),
            articles=articles,
            created_at=created_at,
            updated_at=updated_at,
            status=data.get("status", "pending"),
            similarity_matrix=similarity_matrix,
            aggregation_threshold=data.get("aggregation_threshold", DEFAULT_AGGREGATION_THRESHOLD),
        )


@dataclass
class Synthesis:
    """
    综述数据模型
    
    表示从多篇文章生成的结构化综述。
    
    Attributes:
        id: 综述唯一标识
        title: 综述标题
        cluster_id: 关联的话题聚类 ID
        background: 背景介绍
        impact_analysis: 影响分析
        technical_details: 技术细节
        mitigation: 缓解措施（可选）
        keywords: 关键词列表
        source_articles: 来源文章列表
        additional_sources: 补充参考来源 URL 列表
        created_at: 创建时间
        published_at: 发布时间（可选）
        feishu_doc_url: 飞书文档 URL（可选）
        feishu_doc_token: 飞书文档 token（可选）
    """
    id: str
    title: str
    cluster_id: str
    background: str = ""
    impact_analysis: str = ""
    technical_details: str = ""
    mitigation: str = ""
    keywords: list[str] = field(default_factory=list)
    source_articles: list[Article] = field(default_factory=list)
    additional_sources: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    published_at: datetime | None = None
    feishu_doc_url: str | None = None
    feishu_doc_token: str | None = None
    
    def to_markdown(self) -> str:
        """
        将综述转换为 Markdown 格式
        
        Returns:
            Markdown 格式的综述文本
        
        Validates: Requirements 3.2
        """
        sections = []
        
        # Title
        sections.append(f"# {self.title}\n")
        
        # Keywords
        if self.keywords:
            sections.append(f"**关键词**: {', '.join(self.keywords)}\n")
        
        # Background
        sections.append("## 背景介绍\n")
        sections.append(f"{self.background}\n")
        
        # Impact Analysis
        sections.append("## 影响分析\n")
        sections.append(f"{self.impact_analysis}\n")
        
        # Technical Details
        sections.append("## 技术细节\n")
        sections.append(f"{self.technical_details}\n")
        
        # Mitigation (if applicable)
        if self.mitigation:
            sections.append("## 缓解措施\n")
            sections.append(f"{self.mitigation}\n")
        
        # References
        sections.append("## 参考来源\n")
        
        # Source articles
        for i, article in enumerate(self.source_articles, 1):
            sections.append(f"{i}. [{article.title}]({article.url})\n")
        
        # Additional sources
        if self.additional_sources:
            sections.append("\n### 补充参考\n")
            for i, url in enumerate(self.additional_sources, 1):
                sections.append(f"{i}. {url}\n")
        
        return "\n".join(sections)
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 Synthesis 对象转换为字典
        
        Returns:
            包含所有字段的字典
        
        Validates: Requirements 6.6
        """
        return {
            "id": self.id,
            "title": self.title,
            "cluster_id": self.cluster_id,
            "background": self.background,
            "impact_analysis": self.impact_analysis,
            "technical_details": self.technical_details,
            "mitigation": self.mitigation,
            "keywords": self.keywords,
            "source_articles": [article.to_dict() for article in self.source_articles],
            "additional_sources": self.additional_sources,
            "created_at": self.created_at.isoformat(),
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "feishu_doc_url": self.feishu_doc_url,
            "feishu_doc_token": self.feishu_doc_token,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Synthesis":
        """
        从字典创建 Synthesis 对象
        
        Args:
            data: 包含综述数据的字典
            
        Returns:
            Synthesis 对象
        
        Validates: Requirements 6.6
        """
        # Parse datetime fields
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
            
        published_at = data.get("published_at")
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at)
        
        # Parse source articles
        articles_data = data.get("source_articles", [])
        source_articles = [
            Article.from_dict(a) if isinstance(a, dict) else a
            for a in articles_data
        ]
        
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            cluster_id=data.get("cluster_id", ""),
            background=data.get("background", ""),
            impact_analysis=data.get("impact_analysis", ""),
            technical_details=data.get("technical_details", ""),
            mitigation=data.get("mitigation", ""),
            keywords=data.get("keywords", []),
            source_articles=source_articles,
            additional_sources=data.get("additional_sources", []),
            created_at=created_at,
            published_at=published_at,
            feishu_doc_url=data.get("feishu_doc_url"),
            feishu_doc_token=data.get("feishu_doc_token"),
        )


@dataclass
class FilterResult:
    """
    过滤结果数据模型
    
    表示质量过滤器的处理结果。
    
    Attributes:
        passed: 通过过滤的文章列表
        filtered: 被过滤的文章列表
        filter_reasons: URL 到过滤原因的映射
    """
    passed: list[Article] = field(default_factory=list)
    filtered: list[Article] = field(default_factory=list)
    filter_reasons: dict[str, str] = field(default_factory=dict)
    
    @property
    def passed_count(self) -> int:
        """返回通过过滤的文章数量"""
        return len(self.passed)
    
    @property
    def filtered_count(self) -> int:
        """返回被过滤的文章数量"""
        return len(self.filtered)
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 FilterResult 对象转换为字典
        
        Returns:
            包含所有字段的字典
        
        Validates: Requirements 6.6
        """
        return {
            "passed": [article.to_dict() for article in self.passed],
            "filtered": [article.to_dict() for article in self.filtered],
            "filter_reasons": self.filter_reasons,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FilterResult":
        """
        从字典创建 FilterResult 对象
        
        Args:
            data: 包含过滤结果数据的字典
            
        Returns:
            FilterResult 对象
        
        Validates: Requirements 6.6
        """
        passed_data = data.get("passed", [])
        passed = [
            Article.from_dict(a) if isinstance(a, dict) else a
            for a in passed_data
        ]
        
        filtered_data = data.get("filtered", [])
        filtered = [
            Article.from_dict(a) if isinstance(a, dict) else a
            for a in filtered_data
        ]
        
        return cls(
            passed=passed,
            filtered=filtered,
            filter_reasons=data.get("filter_reasons", {}),
        )


@dataclass
class PublishResult:
    """
    发布结果数据模型
    
    表示飞书文档发布的结果。
    
    Attributes:
        success: 是否成功
        doc_url: 文档 URL（成功时）
        doc_token: 文档 token（成功时）
        error: 错误信息（失败时）
        local_backup_path: 本地备份路径（失败时）
    """
    success: bool
    doc_url: str | None = None
    doc_token: str | None = None
    error: str | None = None
    local_backup_path: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 PublishResult 对象转换为字典
        
        Returns:
            包含所有字段的字典
        
        Validates: Requirements 6.6
        """
        return {
            "success": self.success,
            "doc_url": self.doc_url,
            "doc_token": self.doc_token,
            "error": self.error,
            "local_backup_path": self.local_backup_path,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublishResult":
        """
        从字典创建 PublishResult 对象
        
        Args:
            data: 包含发布结果数据的字典
            
        Returns:
            PublishResult 对象
        
        Validates: Requirements 6.6
        """
        return cls(
            success=data.get("success", False),
            doc_url=data.get("doc_url"),
            doc_token=data.get("doc_token"),
            error=data.get("error"),
            local_backup_path=data.get("local_backup_path"),
        )


@dataclass
class RSSItem:
    """
    RSS 条目数据模型
    
    表示知识库 RSS feed 中的一个条目。
    
    Attributes:
        title: 标题
        link: 链接（飞书文档 URL）
        description: 描述/摘要
        pub_date: 发布时间
        guid: 唯一标识
        categories: 分类标签列表
    """
    title: str
    link: str
    description: str
    pub_date: datetime
    guid: str
    categories: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """
        将 RSSItem 对象转换为字典
        
        Returns:
            包含所有字段的字典
        
        Validates: Requirements 6.6
        """
        return {
            "title": self.title,
            "link": self.link,
            "description": self.description,
            "pub_date": self.pub_date.isoformat(),
            "guid": self.guid,
            "categories": self.categories,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RSSItem":
        """
        从字典创建 RSSItem 对象
        
        Args:
            data: 包含 RSS 条目数据的字典
            
        Returns:
            RSSItem 对象
        
        Validates: Requirements 6.6
        """
        pub_date = data.get("pub_date")
        if isinstance(pub_date, str):
            pub_date = datetime.fromisoformat(pub_date)
        elif pub_date is None:
            pub_date = datetime.now()
        
        return cls(
            title=data.get("title", ""),
            link=data.get("link", ""),
            description=data.get("description", ""),
            pub_date=pub_date,
            guid=data.get("guid", ""),
            categories=data.get("categories", []),
        )
