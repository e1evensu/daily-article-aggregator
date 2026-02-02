"""
数据模型模块

定义系统中使用的数据模型类。
"""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Article:
    """
    文章数据模型
    
    用于表示从arXiv或RSS订阅源获取的文章数据。
    
    Attributes:
        id: 数据库ID，新文章为None
        title: 文章标题
        url: 原文URL
        source: 来源（订阅源名称或arXiv分类）
        source_type: 来源类型：arxiv/rss/dblp/nvd/kev/huggingface/pwc/blog
        published_date: 发布日期（ISO格式字符串）
        fetched_at: 爬取时间（ISO格式字符串）
        content: Markdown格式的文章内容
        summary: AI生成的摘要
        zh_summary: 中文摘要
        category: 文章分类
        is_pushed: 是否已推送到飞书
        pushed_at: 推送时间（ISO格式字符串），未推送为None
        
        # 新增字段 - 优先级和推送相关
        priority_score: 优先级评分 0-100
        push_level: 推送级别 1/2/3
        brief_summary: 简要摘要（1-2句话）
        keywords: 关键词列表
        
        # 新增字段 - 漏洞特有
        cve_id: CVE ID
        cvss_score: CVSS 评分
        github_stars: 关联项目 GitHub star 数
        ip_asset_count: 影响 IP 资产数
        ai_assessment: AI 危害评估
        is_filtered: 是否被过滤
        filter_reasons: 过滤原因列表
    """
    # 现有字段
    id: int | None = None
    title: str = ""
    url: str = ""
    source: str = ""
    source_type: str = ""
    published_date: str = ""
    fetched_at: str = ""
    content: str = ""
    summary: str = ""
    zh_summary: str = ""
    category: str = ""
    is_pushed: bool = False
    pushed_at: str | None = None
    
    # 新增字段 - 优先级和推送相关
    priority_score: int = 0
    push_level: int = 3
    brief_summary: str = ""
    keywords: list[str] = field(default_factory=list)
    
    # 新增字段 - 漏洞特有
    cve_id: str | None = None
    cvss_score: float | None = None
    github_stars: int | None = None
    ip_asset_count: int | None = None
    ai_assessment: str | None = None
    is_filtered: bool = False
    filter_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        将Article对象转换为字典
        
        Returns:
            包含所有字段的字典
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Article":
        """
        从字典创建Article对象
        
        Args:
            data: 包含文章数据的字典
            
        Returns:
            Article对象
            
        Note:
            字典中不存在的字段将使用默认值
            支持向后兼容，旧数据中不存在的新字段将使用默认值
        """
        # 只提取Article类定义的字段，忽略额外字段
        valid_fields = {
            # 现有字段
            'id', 'title', 'url', 'source', 'source_type',
            'published_date', 'fetched_at', 'content', 'summary',
            'zh_summary', 'category', 'is_pushed', 'pushed_at',
            # 新增字段 - 优先级和推送相关
            'priority_score', 'push_level', 'brief_summary', 'keywords',
            # 新增字段 - 漏洞特有
            'cve_id', 'cvss_score', 'github_stars', 'ip_asset_count',
            'ai_assessment', 'is_filtered', 'filter_reasons'
        }
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
