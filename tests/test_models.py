"""
Article数据模型的单元测试
"""

import pytest
from src.models import Article


class TestArticle:
    """Article数据模型测试"""

    def test_default_values(self):
        """测试Article的默认值"""
        article = Article()
        
        # 现有字段默认值
        assert article.id is None
        assert article.title == ""
        assert article.url == ""
        assert article.source == ""
        assert article.source_type == ""
        assert article.published_date == ""
        assert article.fetched_at == ""
        assert article.content == ""
        assert article.summary == ""
        assert article.zh_summary == ""
        assert article.category == ""
        assert article.is_pushed is False
        assert article.pushed_at is None
        
        # 新增字段默认值 - 优先级和推送相关
        assert article.priority_score == 0
        assert article.push_level == 3
        assert article.brief_summary == ""
        assert article.keywords == []
        
        # 新增字段默认值 - 漏洞特有
        assert article.cve_id is None
        assert article.cvss_score is None
        assert article.github_stars is None
        assert article.ip_asset_count is None
        assert article.ai_assessment is None
        assert article.is_filtered is False
        assert article.filter_reasons == []

    def test_create_with_values(self):
        """测试使用值创建Article"""
        article = Article(
            id=1,
            title="Test Article",
            url="https://example.com/article",
            source="Test Source",
            source_type="rss",
            published_date="2024-01-15",
            fetched_at="2024-01-16T10:00:00",
            content="# Test Content",
            summary="This is a test summary",
            zh_summary="这是测试摘要",
            category="Technology",
            is_pushed=True,
            pushed_at="2024-01-16T12:00:00"
        )
        
        assert article.id == 1
        assert article.title == "Test Article"
        assert article.url == "https://example.com/article"
        assert article.source == "Test Source"
        assert article.source_type == "rss"
        assert article.published_date == "2024-01-15"
        assert article.fetched_at == "2024-01-16T10:00:00"
        assert article.content == "# Test Content"
        assert article.summary == "This is a test summary"
        assert article.zh_summary == "这是测试摘要"
        assert article.category == "Technology"
        assert article.is_pushed is True
        assert article.pushed_at == "2024-01-16T12:00:00"

    def test_create_with_new_fields(self):
        """测试使用新字段创建Article"""
        article = Article(
            id=2,
            title="CVE Article",
            url="https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
            source="NVD",
            source_type="nvd",
            priority_score=85,
            push_level=1,
            brief_summary="Critical vulnerability in popular library",
            keywords=["security", "vulnerability", "critical"],
            cve_id="CVE-2024-1234",
            cvss_score=9.8,
            github_stars=50000,
            ip_asset_count=1500,
            ai_assessment="High impact vulnerability affecting widely used library",
            is_filtered=False,
            filter_reasons=[]
        )
        
        # 验证新字段
        assert article.priority_score == 85
        assert article.push_level == 1
        assert article.brief_summary == "Critical vulnerability in popular library"
        assert article.keywords == ["security", "vulnerability", "critical"]
        assert article.cve_id == "CVE-2024-1234"
        assert article.cvss_score == 9.8
        assert article.github_stars == 50000
        assert article.ip_asset_count == 1500
        assert article.ai_assessment == "High impact vulnerability affecting widely used library"
        assert article.is_filtered is False
        assert article.filter_reasons == []

    def test_create_filtered_vulnerability(self):
        """测试创建被过滤的漏洞文章"""
        article = Article(
            title="Low Priority CVE",
            url="https://nvd.nist.gov/vuln/detail/CVE-2024-9999",
            source="NVD",
            source_type="nvd",
            cve_id="CVE-2024-9999",
            cvss_score=4.5,
            github_stars=50,
            ip_asset_count=10,
            is_filtered=True,
            filter_reasons=["GitHub stars below threshold", "IP asset count below threshold"]
        )
        
        assert article.is_filtered is True
        assert len(article.filter_reasons) == 2
        assert "GitHub stars below threshold" in article.filter_reasons
        assert "IP asset count below threshold" in article.filter_reasons

    def test_to_dict(self):
        """测试to_dict方法"""
        article = Article(
            id=1,
            title="Test Article",
            url="https://example.com/article",
            source="Test Source",
            source_type="arxiv",
            is_pushed=False
        )
        
        result = article.to_dict()
        
        assert isinstance(result, dict)
        assert result["id"] == 1
        assert result["title"] == "Test Article"
        assert result["url"] == "https://example.com/article"
        assert result["source"] == "Test Source"
        assert result["source_type"] == "arxiv"
        assert result["is_pushed"] is False
        assert result["pushed_at"] is None
        # 验证所有字段都存在（包括新字段）
        expected_keys = {
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
        assert set(result.keys()) == expected_keys

    def test_to_dict_with_new_fields(self):
        """测试to_dict方法包含新字段"""
        article = Article(
            id=1,
            title="CVE Test",
            url="https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
            source="NVD",
            source_type="nvd",
            priority_score=90,
            push_level=1,
            brief_summary="Critical vulnerability",
            keywords=["security", "critical"],
            cve_id="CVE-2024-1234",
            cvss_score=9.5,
            github_stars=10000,
            ip_asset_count=500,
            ai_assessment="High impact",
            is_filtered=False,
            filter_reasons=[]
        )
        
        result = article.to_dict()
        
        # 验证新字段正确序列化
        assert result["priority_score"] == 90
        assert result["push_level"] == 1
        assert result["brief_summary"] == "Critical vulnerability"
        assert result["keywords"] == ["security", "critical"]
        assert result["cve_id"] == "CVE-2024-1234"
        assert result["cvss_score"] == 9.5
        assert result["github_stars"] == 10000
        assert result["ip_asset_count"] == 500
        assert result["ai_assessment"] == "High impact"
        assert result["is_filtered"] is False
        assert result["filter_reasons"] == []

    def test_from_dict(self):
        """测试from_dict类方法"""
        data = {
            "id": 2,
            "title": "Another Article",
            "url": "https://example.com/another",
            "source": "RSS Feed",
            "source_type": "rss",
            "published_date": "2024-01-20",
            "fetched_at": "2024-01-21T08:00:00",
            "content": "Article content here",
            "summary": "Summary text",
            "zh_summary": "中文摘要",
            "category": "AI",
            "is_pushed": True,
            "pushed_at": "2024-01-21T10:00:00"
        }
        
        article = Article.from_dict(data)
        
        assert article.id == 2
        assert article.title == "Another Article"
        assert article.url == "https://example.com/another"
        assert article.source == "RSS Feed"
        assert article.source_type == "rss"
        assert article.published_date == "2024-01-20"
        assert article.fetched_at == "2024-01-21T08:00:00"
        assert article.content == "Article content here"
        assert article.summary == "Summary text"
        assert article.zh_summary == "中文摘要"
        assert article.category == "AI"
        assert article.is_pushed is True
        assert article.pushed_at == "2024-01-21T10:00:00"
        # 新字段应使用默认值
        assert article.priority_score == 0
        assert article.push_level == 3
        assert article.keywords == []
        assert article.cve_id is None

    def test_from_dict_with_new_fields(self):
        """测试from_dict类方法处理新字段"""
        data = {
            "id": 3,
            "title": "CVE Article",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2024-5678",
            "source": "NVD",
            "source_type": "nvd",
            "priority_score": 75,
            "push_level": 2,
            "brief_summary": "Medium severity vulnerability",
            "keywords": ["security", "medium"],
            "cve_id": "CVE-2024-5678",
            "cvss_score": 6.5,
            "github_stars": 5000,
            "ip_asset_count": 350,
            "ai_assessment": "Moderate impact",
            "is_filtered": False,
            "filter_reasons": []
        }
        
        article = Article.from_dict(data)
        
        assert article.priority_score == 75
        assert article.push_level == 2
        assert article.brief_summary == "Medium severity vulnerability"
        assert article.keywords == ["security", "medium"]
        assert article.cve_id == "CVE-2024-5678"
        assert article.cvss_score == 6.5
        assert article.github_stars == 5000
        assert article.ip_asset_count == 350
        assert article.ai_assessment == "Moderate impact"
        assert article.is_filtered is False
        assert article.filter_reasons == []

    def test_from_dict_with_partial_data(self):
        """测试from_dict处理部分数据"""
        data = {
            "title": "Partial Article",
            "url": "https://example.com/partial"
        }
        
        article = Article.from_dict(data)
        
        assert article.id is None
        assert article.title == "Partial Article"
        assert article.url == "https://example.com/partial"
        assert article.source == ""
        assert article.is_pushed is False

    def test_from_dict_ignores_extra_fields(self):
        """测试from_dict忽略额外字段"""
        data = {
            "title": "Test",
            "url": "https://example.com",
            "extra_field": "should be ignored",
            "another_extra": 123
        }
        
        article = Article.from_dict(data)
        
        assert article.title == "Test"
        assert article.url == "https://example.com"
        assert not hasattr(article, "extra_field")
        assert not hasattr(article, "another_extra")

    def test_roundtrip_dict_conversion(self):
        """测试字典转换的往返一致性"""
        original = Article(
            id=5,
            title="Roundtrip Test",
            url="https://example.com/roundtrip",
            source="Test Source",
            source_type="rss",
            published_date="2024-02-01",
            fetched_at="2024-02-02T09:00:00",
            content="Content for roundtrip test",
            summary="Summary for roundtrip",
            zh_summary="往返测试摘要",
            category="Testing",
            is_pushed=True,
            pushed_at="2024-02-02T11:00:00"
        )
        
        # 转换为字典再转回Article
        dict_data = original.to_dict()
        restored = Article.from_dict(dict_data)
        
        # 验证所有字段一致
        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.url == original.url
        assert restored.source == original.source
        assert restored.source_type == original.source_type
        assert restored.published_date == original.published_date
        assert restored.fetched_at == original.fetched_at
        assert restored.content == original.content
        assert restored.summary == original.summary
        assert restored.zh_summary == original.zh_summary
        assert restored.category == original.category
        assert restored.is_pushed == original.is_pushed
        assert restored.pushed_at == original.pushed_at

    def test_roundtrip_dict_conversion_with_new_fields(self):
        """测试包含新字段的字典转换往返一致性"""
        original = Article(
            id=6,
            title="CVE Roundtrip Test",
            url="https://nvd.nist.gov/vuln/detail/CVE-2024-9876",
            source="NVD",
            source_type="nvd",
            published_date="2024-03-01",
            fetched_at="2024-03-02T09:00:00",
            content="CVE content",
            summary="CVE summary",
            zh_summary="CVE中文摘要",
            category="Security",
            is_pushed=False,
            pushed_at=None,
            # 新字段
            priority_score=95,
            push_level=1,
            brief_summary="Critical vulnerability in widely used library",
            keywords=["critical", "security", "library"],
            cve_id="CVE-2024-9876",
            cvss_score=9.9,
            github_stars=100000,
            ip_asset_count=2000,
            ai_assessment="Extremely high impact vulnerability",
            is_filtered=False,
            filter_reasons=[]
        )
        
        # 转换为字典再转回Article
        dict_data = original.to_dict()
        restored = Article.from_dict(dict_data)
        
        # 验证新字段一致
        assert restored.priority_score == original.priority_score
        assert restored.push_level == original.push_level
        assert restored.brief_summary == original.brief_summary
        assert restored.keywords == original.keywords
        assert restored.cve_id == original.cve_id
        assert restored.cvss_score == original.cvss_score
        assert restored.github_stars == original.github_stars
        assert restored.ip_asset_count == original.ip_asset_count
        assert restored.ai_assessment == original.ai_assessment
        assert restored.is_filtered == original.is_filtered
        assert restored.filter_reasons == original.filter_reasons

    def test_backward_compatibility_from_dict(self):
        """测试from_dict向后兼容性 - 旧数据不包含新字段"""
        # 模拟旧版本数据（不包含新字段）
        old_data = {
            "id": 10,
            "title": "Old Article",
            "url": "https://example.com/old",
            "source": "Old Source",
            "source_type": "rss",
            "published_date": "2023-01-01",
            "fetched_at": "2023-01-02T10:00:00",
            "content": "Old content",
            "summary": "Old summary",
            "zh_summary": "旧摘要",
            "category": "Old Category",
            "is_pushed": True,
            "pushed_at": "2023-01-02T12:00:00"
        }
        
        # 应该能正常创建Article，新字段使用默认值
        article = Article.from_dict(old_data)
        
        # 验证旧字段正确加载
        assert article.id == 10
        assert article.title == "Old Article"
        assert article.is_pushed is True
        
        # 验证新字段使用默认值
        assert article.priority_score == 0
        assert article.push_level == 3
        assert article.brief_summary == ""
        assert article.keywords == []
        assert article.cve_id is None
        assert article.cvss_score is None
        assert article.github_stars is None
        assert article.ip_asset_count is None
        assert article.ai_assessment is None
        assert article.is_filtered is False
        assert article.filter_reasons == []

    def test_list_fields_are_independent(self):
        """测试列表字段在不同实例间是独立的"""
        article1 = Article()
        article2 = Article()
        
        # 修改article1的列表字段
        article1.keywords.append("test")
        article1.filter_reasons.append("reason")
        
        # article2的列表字段应该不受影响
        assert article2.keywords == []
        assert article2.filter_reasons == []
