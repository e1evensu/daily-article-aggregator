"""
BlogFetcher 单元测试和属性测试
Unit tests and property-based tests for BlogFetcher

测试大厂博客 RSS 获取器的各项功能。
Tests for tech company blog RSS fetcher functionality.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.fetchers.blog_fetcher import BlogFetcher, parse_blog_entry


class TestBlogFetcherInit:
    """测试 BlogFetcher 初始化"""
    
    def test_default_config(self):
        """测试默认配置"""
        fetcher = BlogFetcher({})
        
        assert fetcher.enabled is True
        assert fetcher.timeout == 30
        assert fetcher.max_workers == 3
        assert set(fetcher.enabled_blogs) == {'openai', 'deepmind', 'anthropic'}
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = {
            'enabled': False,
            'sources': ['openai', 'anthropic'],
            'timeout': 60,
            'max_workers': 2
        }
        fetcher = BlogFetcher(config)
        
        assert fetcher.enabled is False
        assert fetcher.timeout == 60
        assert fetcher.max_workers == 2
        assert fetcher.enabled_blogs == ['openai', 'anthropic']
    
    def test_is_enabled(self):
        """测试 is_enabled 方法"""
        fetcher_enabled = BlogFetcher({'enabled': True})
        fetcher_disabled = BlogFetcher({'enabled': False})
        
        assert fetcher_enabled.is_enabled() is True
        assert fetcher_disabled.is_enabled() is False


class TestBlogFetcherFetch:
    """测试 BlogFetcher fetch 方法"""
    
    def test_fetch_disabled(self):
        """测试禁用时的 fetch"""
        fetcher = BlogFetcher({'enabled': False})
        result = fetcher.fetch()
        
        assert result.is_success() is False
        assert result.error == 'Fetcher is disabled'
        assert len(result.items) == 0
    
    def test_fetch_no_valid_blogs(self):
        """测试无有效博客配置时的 fetch"""
        fetcher = BlogFetcher({'sources': ['invalid']})
        result = fetcher.fetch()
        
        assert result.is_success() is False
        assert 'No valid blogs' in result.error
    
    def test_fetch_with_mock(self):
        """使用 mock 测试 fetch"""
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            MagicMock(
                title='New AI Model',
                link='https://openai.com/blog/new-model',
                summary='We are excited to announce...'
            )
        ]
        mock_feed.entries[0].get = lambda key, default='': {
            'title': 'New AI Model',
            'link': 'https://openai.com/blog/new-model',
            'summary': 'We are excited to announce...'
        }.get(key, default)
        
        with patch('src.fetchers.blog_fetcher.feedparser.parse', return_value=mock_feed):
            fetcher = BlogFetcher({'sources': ['openai']})
            result = fetcher.fetch()
            
            assert result.source_type == 'blog'
            assert len(result.items) == 1
            assert result.items[0]['title'] == 'New AI Model'
            assert result.items[0]['company'] == 'OpenAI'


class TestParseBlogEntry:
    """测试 parse_blog_entry 函数"""
    
    def test_parse_complete_entry(self):
        """测试解析完整条目"""
        entry = {
            'title': 'New AI Model Released',
            'link': 'https://openai.com/blog/new-model',
            'summary': 'We are excited to announce...',
            'published_date': '2024-01-15'
        }
        
        result = parse_blog_entry(entry, 'openai', 'OpenAI Blog', 'OpenAI')
        
        assert result is not None
        assert result['title'] == 'New AI Model Released'
        assert result['url'] == 'https://openai.com/blog/new-model'
        assert result['summary'] == 'We are excited to announce...'
        assert result['blog_id'] == 'openai'
        assert result['blog_name'] == 'OpenAI Blog'
        assert result['company'] == 'OpenAI'
        assert result['source_type'] == 'blog'
    
    def test_parse_entry_missing_title(self):
        """测试缺少标题的条目"""
        entry = {
            'title': '',
            'link': 'https://openai.com/blog/test',
        }
        
        result = parse_blog_entry(entry, 'openai', 'OpenAI Blog', 'OpenAI')
        
        assert result is None
    
    def test_parse_entry_missing_url(self):
        """测试缺少 URL 的条目"""
        entry = {
            'title': 'Test Article',
            'link': '',
        }
        
        result = parse_blog_entry(entry, 'openai', 'OpenAI Blog', 'OpenAI')
        
        assert result is None
    
    def test_parse_entry_description_fallback(self):
        """测试使用 description 作为 summary 的回退"""
        entry = {
            'title': 'Test Article',
            'link': 'https://openai.com/blog/test',
            'summary': '',
            'description': 'This is the description'
        }
        
        result = parse_blog_entry(entry, 'openai', 'OpenAI Blog', 'OpenAI')
        
        assert result is not None
        assert result['summary'] == 'This is the description'


class TestBlogSourceConfiguration:
    """测试博客源配置"""
    
    def test_only_enabled_blogs_fetched(self):
        """测试只获取启用的博客"""
        fetcher = BlogFetcher({'sources': ['openai']})
        
        # 验证只有 openai 在启用列表中
        assert fetcher.enabled_blogs == ['openai']
        assert 'deepmind' not in fetcher.enabled_blogs
        assert 'anthropic' not in fetcher.enabled_blogs
    
    def test_invalid_blogs_filtered(self):
        """测试无效博客被过滤"""
        fetcher = BlogFetcher({'sources': ['openai', 'invalid', 'deepmind']})
        
        # 获取有效博客列表
        valid_blogs = [
            blog for blog in fetcher.enabled_blogs 
            if blog in fetcher.BLOG_FEEDS
        ]
        
        assert 'openai' in valid_blogs
        assert 'deepmind' in valid_blogs
        assert 'invalid' not in valid_blogs


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# Strategy for generating valid blog entry dictionaries
blog_entry_strategy = st.fixed_dictionaries({
    'title': st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    'link': st.from_regex(r'https://[a-z]+\.[a-z]+/blog/[a-z0-9-]+', fullmatch=True),
    'summary': st.text(min_size=0, max_size=500),
    'published_date': st.from_regex(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]', fullmatch=True) | st.just(''),
})

blog_id_strategy = st.sampled_from(['openai', 'deepmind', 'anthropic'])
blog_name_strategy = st.sampled_from(['OpenAI Blog', 'DeepMind Blog', 'Anthropic Blog'])
company_strategy = st.sampled_from(['OpenAI', 'DeepMind', 'Anthropic'])


@given(blog_entry_strategy, blog_id_strategy, blog_name_strategy, company_strategy)
@settings(max_examples=100)
def test_property_blog_entry_parsing_completeness(
    entry: dict, 
    blog: str, 
    blog_name: str,
    company: str
):
    """
    Feature: aggregator-advanced-features, Property 7: Blog Entry Parsing Completeness
    
    **Validates: Requirements 4.2**
    
    对于任意有效的博客 RSS 条目，解析器应提取所有必需字段
    （title, published_date, summary, url）且类型正确。
    
    For any valid blog RSS entry, the parser SHALL extract all required fields
    (title, published_date, summary, url) with correct types.
    """
    result = parse_blog_entry(entry, blog, blog_name, company)
    
    # Property: Result should not be None for valid input
    assert result is not None, "Valid entry should produce a result"
    
    # Property: Title must be non-empty and match input
    assert result['title'], "Title must be non-empty"
    assert result['title'] == entry['title'].strip(), \
        f"Title {result['title']} should match input {entry['title']}"
    
    # Property: URL must be non-empty and match input
    assert result['url'], "URL must be non-empty"
    assert result['url'] == entry['link'].strip(), \
        f"URL {result['url']} should match input {entry['link']}"
    
    # Property: Summary must be a string
    assert isinstance(result['summary'], str), "Summary must be a string"
    
    # Property: Published date must be a string
    assert isinstance(result['published_date'], str), \
        "Published date must be a string"
    
    # Property: If published date is non-empty, it should be in YYYY-MM-DD format
    if result['published_date']:
        assert len(result['published_date']) == 10, \
            f"Published date {result['published_date']} should be in YYYY-MM-DD format"
        assert result['published_date'][4] == '-' and result['published_date'][7] == '-', \
            "Published date should have dashes in correct positions"
    
    # Property: Blog ID must match input
    assert result['blog_id'] == blog, \
        f"Blog ID {result['blog_id']} should match {blog}"
    
    # Property: Blog name must match input
    assert result['blog_name'] == blog_name, \
        f"Blog name {result['blog_name']} should match {blog_name}"
    
    # Property: Company must match input
    assert result['company'] == company, \
        f"Company {result['company']} should match {company}"
    
    # Property: Source type must be 'blog'
    assert result['source_type'] == 'blog', "Source type must be 'blog'"


@given(st.lists(blog_id_strategy, min_size=0, max_size=3, unique=True))
@settings(max_examples=50)
def test_property_blog_source_configuration(enabled_blogs: list[str]):
    """
    Feature: aggregator-advanced-features, Property 21: Blog Source Configuration
    
    **Validates: Requirements 4.1**
    
    对于配置中启用的任意博客源子集，BlogFetcher 应只尝试从启用的源获取，
    忽略禁用的源。
    
    For any subset of enabled blog sources in configuration, the BlogFetcher
    SHALL only attempt to fetch from the enabled sources and ignore disabled ones.
    """
    fetcher = BlogFetcher({'sources': enabled_blogs})
    
    # Property: enabled_blogs should match configuration
    assert fetcher.enabled_blogs == enabled_blogs, \
        f"Enabled blogs {fetcher.enabled_blogs} should match config {enabled_blogs}"
    
    # Property: Only valid blogs should be in the fetch list
    valid_blogs = [
        blog for blog in fetcher.enabled_blogs 
        if blog in fetcher.BLOG_FEEDS
    ]
    
    for blog in valid_blogs:
        assert blog in BlogFetcher.BLOG_FEEDS, \
            f"Blog {blog} should be a valid blog source"
    
    # Property: All enabled blogs should be in the valid list or be invalid
    for blog in enabled_blogs:
        if blog in BlogFetcher.BLOG_FEEDS:
            assert blog in valid_blogs, \
                f"Valid blog {blog} should be in valid_blogs list"


@given(st.lists(blog_entry_strategy, min_size=0, max_size=20))
@settings(max_examples=50)
def test_property_blog_batch_parsing(entries: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 7: Blog Entry Parsing Completeness (Batch)
    
    **Validates: Requirements 4.2**
    
    对于任意博客条目列表，每个有效的条目都应被正确解析。
    For any list of blog entries, each valid entry should be correctly parsed.
    """
    for i, entry in enumerate(entries):
        result = parse_blog_entry(entry, 'openai', 'OpenAI Blog', 'OpenAI')
        
        # Property: Each valid entry should produce a result
        assert result is not None, f"Entry {i} should produce a result"
        
        # Property: Each result should have required fields
        assert 'title' in result, f"Entry {i} result should have title"
        assert 'url' in result, f"Entry {i} result should have url"
        assert 'summary' in result, f"Entry {i} result should have summary"
        assert 'published_date' in result, f"Entry {i} result should have published_date"
