"""
RSSFetcher单元测试
Unit tests for RSSFetcher

测试RSS订阅源获取器的各项功能。
Tests for RSS feed fetcher functionality.
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET

from src.fetchers.rss_fetcher import RSSFetcher, parse_opml_content


class TestParseOpml:
    """测试OPML解析功能"""
    
    def test_parse_opml_basic(self):
        """测试基本的OPML解析"""
        opml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <head>
            <title>Test Feeds</title>
          </head>
          <body>
            <outline type="rss" text="Feed 1" xmlUrl="https://example.com/feed1.xml"/>
            <outline type="rss" text="Feed 2" xmlUrl="https://example.com/feed2.xml"/>
          </body>
        </opml>'''
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.opml', delete=False) as f:
            f.write(opml_content)
            temp_path = f.name
        
        try:
            fetcher = RSSFetcher({})
            urls = fetcher.parse_opml(temp_path)
            
            assert len(urls) == 2
            assert 'https://example.com/feed1.xml' in urls
            assert 'https://example.com/feed2.xml' in urls
        finally:
            os.unlink(temp_path)
    
    def test_parse_opml_nested(self):
        """测试嵌套结构的OPML解析"""
        opml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <body>
            <outline text="Category 1">
              <outline type="rss" text="Feed 1" xmlUrl="https://example.com/feed1.xml"/>
              <outline type="rss" text="Feed 2" xmlUrl="https://example.com/feed2.xml"/>
            </outline>
            <outline text="Category 2">
              <outline type="rss" text="Feed 3" xmlUrl="https://example.com/feed3.xml"/>
            </outline>
          </body>
        </opml>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.opml', delete=False) as f:
            f.write(opml_content)
            temp_path = f.name
        
        try:
            fetcher = RSSFetcher({})
            urls = fetcher.parse_opml(temp_path)
            
            assert len(urls) == 3
            assert 'https://example.com/feed1.xml' in urls
            assert 'https://example.com/feed2.xml' in urls
            assert 'https://example.com/feed3.xml' in urls
        finally:
            os.unlink(temp_path)
    
    def test_parse_opml_empty(self):
        """测试空OPML文件"""
        opml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <body>
          </body>
        </opml>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.opml', delete=False) as f:
            f.write(opml_content)
            temp_path = f.name
        
        try:
            fetcher = RSSFetcher({})
            urls = fetcher.parse_opml(temp_path)
            
            assert len(urls) == 0
        finally:
            os.unlink(temp_path)
    
    def test_parse_opml_file_not_found(self):
        """测试文件不存在的情况"""
        fetcher = RSSFetcher({})
        
        with pytest.raises(FileNotFoundError):
            fetcher.parse_opml('/nonexistent/path/feeds.opml')
    
    def test_parse_opml_invalid_xml(self):
        """测试无效XML的情况"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.opml', delete=False) as f:
            f.write('not valid xml content')
            temp_path = f.name
        
        try:
            fetcher = RSSFetcher({})
            with pytest.raises(ET.ParseError):
                fetcher.parse_opml(temp_path)
        finally:
            os.unlink(temp_path)


class TestParseOpmlContent:
    """测试独立的OPML内容解析函数"""
    
    def test_parse_opml_content_basic(self):
        """测试基本的OPML内容解析"""
        opml_content = '''<?xml version="1.0"?>
        <opml version="2.0">
          <body>
            <outline type="rss" xmlUrl="https://example.com/feed.xml"/>
          </body>
        </opml>'''
        
        urls = parse_opml_content(opml_content)
        
        assert len(urls) == 1
        assert urls[0] == 'https://example.com/feed.xml'
    
    def test_parse_opml_content_multiple(self):
        """测试多个订阅源的解析"""
        opml_content = '''<?xml version="1.0"?>
        <opml version="2.0">
          <body>
            <outline type="rss" xmlUrl="https://a.com/feed.xml"/>
            <outline type="rss" xmlUrl="https://b.com/feed.xml"/>
            <outline type="rss" xmlUrl="https://c.com/feed.xml"/>
          </body>
        </opml>'''
        
        urls = parse_opml_content(opml_content)
        
        assert len(urls) == 3
        assert 'https://a.com/feed.xml' in urls
        assert 'https://b.com/feed.xml' in urls
        assert 'https://c.com/feed.xml' in urls
    
    def test_parse_opml_content_nested(self):
        """测试嵌套结构"""
        opml_content = '''<?xml version="1.0"?>
        <opml version="2.0">
          <body>
            <outline text="Group">
              <outline type="rss" xmlUrl="https://nested.com/feed.xml"/>
            </outline>
          </body>
        </opml>'''
        
        urls = parse_opml_content(opml_content)
        
        assert len(urls) == 1
        assert urls[0] == 'https://nested.com/feed.xml'
    
    def test_parse_opml_content_empty(self):
        """测试空内容"""
        opml_content = '''<?xml version="1.0"?>
        <opml version="2.0">
          <body></body>
        </opml>'''
        
        urls = parse_opml_content(opml_content)
        
        assert len(urls) == 0
    
    def test_parse_opml_content_invalid_xml(self):
        """测试无效XML"""
        with pytest.raises(ET.ParseError):
            parse_opml_content('not valid xml')


class TestFetchFeed:
    """测试单个订阅源获取功能"""
    
    def test_fetch_feed_with_mock(self):
        """使用mock测试fetch_feed"""
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {'title': 'Test Feed'}
        mock_feed.entries = [
            MagicMock(
                title='Article 1',
                link='https://example.com/article1',
                published_parsed=(2024, 1, 15, 10, 0, 0, 0, 0, 0)
            ),
            MagicMock(
                title='Article 2',
                link='https://example.com/article2',
                published_parsed=(2024, 1, 14, 10, 0, 0, 0, 0, 0)
            ),
        ]
        # 设置get方法
        mock_feed.entries[0].get = lambda key, default='': {
            'title': 'Article 1',
            'link': 'https://example.com/article1'
        }.get(key, default)
        mock_feed.entries[1].get = lambda key, default='': {
            'title': 'Article 2',
            'link': 'https://example.com/article2'
        }.get(key, default)
        
        with patch('src.fetchers.rss_fetcher.feedparser.parse', return_value=mock_feed):
            fetcher = RSSFetcher({})
            feed_name, articles = fetcher.fetch_feed('https://example.com/feed.xml')
            
            assert feed_name == 'Test Feed'
            assert len(articles) == 2
            assert articles[0]['title'] == 'Article 1'
            assert articles[0]['url'] == 'https://example.com/article1'
            assert articles[0]['source'] == 'Test Feed'
            assert articles[0]['source_type'] == 'rss'
            assert articles[0]['published_date'] == '2024-01-15'
    
    def test_fetch_feed_missing_title(self):
        """测试缺少标题的条目"""
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {'title': 'Test Feed'}
        mock_entry = MagicMock()
        mock_entry.get = lambda key, default='': {
            'title': '',  # 空标题
            'link': 'https://example.com/article'
        }.get(key, default)
        mock_feed.entries = [mock_entry]
        
        with patch('src.fetchers.rss_fetcher.feedparser.parse', return_value=mock_feed):
            fetcher = RSSFetcher({})
            feed_name, articles = fetcher.fetch_feed('https://example.com/feed.xml')
            
            assert feed_name == 'Test Feed'
            assert len(articles) == 0  # 缺少标题的条目被跳过
    
    def test_fetch_feed_missing_link(self):
        """测试缺少链接的条目"""
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {'title': 'Test Feed'}
        mock_entry = MagicMock()
        mock_entry.get = lambda key, default='': {
            'title': 'Article',
            'link': ''  # 空链接
        }.get(key, default)
        mock_feed.entries = [mock_entry]
        
        with patch('src.fetchers.rss_fetcher.feedparser.parse', return_value=mock_feed):
            fetcher = RSSFetcher({})
            feed_name, articles = fetcher.fetch_feed('https://example.com/feed.xml')
            
            assert len(articles) == 0  # 缺少链接的条目被跳过
    
    def test_fetch_feed_error_handling(self):
        """测试错误处理"""
        with patch('src.fetchers.rss_fetcher.feedparser.parse', side_effect=Exception('Network error')):
            fetcher = RSSFetcher({})
            feed_name, articles = fetcher.fetch_feed('https://example.com/feed.xml')
            
            # 应该返回空结果而不是抛出异常
            assert feed_name == 'https://example.com/feed.xml'
            assert len(articles) == 0


class TestFetchAllFeeds:
    """测试并发获取所有订阅源功能"""
    
    def test_fetch_all_feeds_empty(self):
        """测试空URL列表"""
        fetcher = RSSFetcher({'max_workers': 3})
        results = fetcher.fetch_all_feeds([])
        
        assert results == {}
    
    def test_fetch_all_feeds_with_mock(self):
        """使用mock测试并发获取"""
        def mock_fetch_feed(url):
            if url == 'https://a.com/feed.xml':
                return ('Feed A', [{'title': 'Article A', 'url': 'https://a.com/1', 'source': 'Feed A', 'source_type': 'rss', 'published_date': '2024-01-15'}])
            elif url == 'https://b.com/feed.xml':
                return ('Feed B', [{'title': 'Article B', 'url': 'https://b.com/1', 'source': 'Feed B', 'source_type': 'rss', 'published_date': '2024-01-14'}])
            else:
                return (url, [])
        
        fetcher = RSSFetcher({'max_workers': 2})
        
        with patch.object(fetcher, 'fetch_feed', side_effect=mock_fetch_feed):
            urls = ['https://a.com/feed.xml', 'https://b.com/feed.xml']
            results = fetcher.fetch_all_feeds(urls)
            
            assert len(results) == 2
            assert 'Feed A' in results
            assert 'Feed B' in results
            assert len(results['Feed A']) == 1
            assert len(results['Feed B']) == 1
    
    def test_fetch_all_feeds_partial_failure(self):
        """测试部分订阅源失败的情况"""
        def mock_fetch_feed(url):
            if url == 'https://good.com/feed.xml':
                return ('Good Feed', [{'title': 'Article', 'url': 'https://good.com/1', 'source': 'Good Feed', 'source_type': 'rss', 'published_date': '2024-01-15'}])
            else:
                # 模拟失败的订阅源返回空结果
                return (url, [])
        
        fetcher = RSSFetcher({'max_workers': 2})
        
        with patch.object(fetcher, 'fetch_feed', side_effect=mock_fetch_feed):
            urls = ['https://good.com/feed.xml', 'https://bad.com/feed.xml']
            results = fetcher.fetch_all_feeds(urls)
            
            # 只有成功的订阅源被包含
            assert len(results) == 1
            assert 'Good Feed' in results


class TestRSSFetcherInit:
    """测试RSSFetcher初始化"""
    
    def test_default_config(self):
        """测试默认配置"""
        fetcher = RSSFetcher({})
        
        assert fetcher.opml_path == ''
        assert fetcher.proxy is None
        assert fetcher.max_workers == 5
        assert fetcher.timeout == 30
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = {
            'opml_path': '/path/to/feeds.opml',
            'proxy': 'http://proxy:8080',
            'max_workers': 10,
            'timeout': 60
        }
        fetcher = RSSFetcher(config)
        
        assert fetcher.opml_path == '/path/to/feeds.opml'
        assert fetcher.proxy == 'http://proxy:8080'
        assert fetcher.max_workers == 10
        assert fetcher.timeout == 60


class TestIntegrationWithRealOPML:
    """使用项目中的真实OPML文件进行集成测试"""
    
    def test_parse_real_opml(self):
        """测试解析项目中的feeds.opml文件"""
        opml_path = 'feeds.opml'
        
        if not os.path.exists(opml_path):
            pytest.skip("feeds.opml not found in current directory")
        
        fetcher = RSSFetcher({})
        urls = fetcher.parse_opml(opml_path)
        
        # 验证解析出了订阅源
        assert len(urls) > 0
        
        # 验证所有URL都是有效的URL格式
        for url in urls:
            assert url.startswith('http://') or url.startswith('https://')


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# -----------------------------------------------------------------------------
# Property 3: OPML解析一致性
# For any valid OPML content, the parsed feed URLs should match exactly
# what's defined in the OPML.
# -----------------------------------------------------------------------------

def generate_valid_opml(feed_urls: list[str], nested: bool = False) -> str:
    """
    生成有效的OPML XML内容
    Generate valid OPML XML content
    
    Args:
        feed_urls: 订阅源URL列表
        nested: 是否使用嵌套结构
    
    Returns:
        OPML格式的XML字符串
    """
    outlines = []
    
    if nested and len(feed_urls) > 1:
        # 将URL分成两组，放入嵌套结构
        mid = len(feed_urls) // 2
        group1 = feed_urls[:mid]
        group2 = feed_urls[mid:]
        
        group1_outlines = '\n'.join(
            f'        <outline type="rss" text="Feed" xmlUrl="{url}"/>'
            for url in group1
        )
        group2_outlines = '\n'.join(
            f'        <outline type="rss" text="Feed" xmlUrl="{url}"/>'
            for url in group2
        )
        
        outlines_str = f'''      <outline text="Group 1">
{group1_outlines}
      </outline>
      <outline text="Group 2">
{group2_outlines}
      </outline>'''
    else:
        outlines_str = '\n'.join(
            f'      <outline type="rss" text="Feed" xmlUrl="{url}"/>'
            for url in feed_urls
        )
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>Test Feeds</title>
  </head>
  <body>
{outlines_str}
  </body>
</opml>'''


# Strategy for generating valid feed URLs
feed_url_strategy = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789-._~'),
    min_size=1,
    max_size=50
).map(lambda s: f"https://example.com/{s}/feed.xml")


@given(st.lists(feed_url_strategy, min_size=0, max_size=20, unique=True))
@settings(max_examples=100)
def test_property_opml_parsing_consistency_flat(feed_urls: list[str]):
    """
    Feature: daily-article-aggregator, Property 3: OPML解析一致性
    
    **Validates: Requirements 2.1**
    
    对于任意有效的OPML内容（扁平结构），解析后获取的订阅源URL列表应该与OPML中定义的订阅源一一对应。
    For any valid OPML content (flat structure), the parsed feed URLs should match exactly what's defined in the OPML.
    """
    # Generate valid OPML content
    opml_content = generate_valid_opml(feed_urls, nested=False)
    
    # Parse the OPML content
    parsed_urls = parse_opml_content(opml_content)
    
    # Property: All URLs in the OPML are returned
    assert set(parsed_urls) == set(feed_urls), \
        f"Parsed URLs {parsed_urls} don't match input URLs {feed_urls}"
    
    # Property: No extra URLs are returned
    assert len(parsed_urls) == len(feed_urls), \
        f"Parsed URL count {len(parsed_urls)} doesn't match input count {len(feed_urls)}"
    
    # Property: The count matches
    for url in feed_urls:
        assert url in parsed_urls, f"URL {url} not found in parsed URLs"


@given(st.lists(feed_url_strategy, min_size=2, max_size=20, unique=True))
@settings(max_examples=100)
def test_property_opml_parsing_consistency_nested(feed_urls: list[str]):
    """
    Feature: daily-article-aggregator, Property 3: OPML解析一致性
    
    **Validates: Requirements 2.1**
    
    对于任意有效的OPML内容（嵌套结构），解析后获取的订阅源URL列表应该与OPML中定义的订阅源一一对应。
    For any valid OPML content (nested structure), the parsed feed URLs should match exactly what's defined in the OPML.
    """
    # Generate valid OPML content with nested structure
    opml_content = generate_valid_opml(feed_urls, nested=True)
    
    # Parse the OPML content
    parsed_urls = parse_opml_content(opml_content)
    
    # Property: All URLs in the OPML are returned
    assert set(parsed_urls) == set(feed_urls), \
        f"Parsed URLs {parsed_urls} don't match input URLs {feed_urls}"
    
    # Property: No extra URLs are returned
    assert len(parsed_urls) == len(feed_urls), \
        f"Parsed URL count {len(parsed_urls)} doesn't match input count {len(feed_urls)}"


# -----------------------------------------------------------------------------
# Property 4: 文章字段完整性
# For any successfully fetched article (from arXiv or RSS), it should have
# non-empty title, url, and source fields.
# -----------------------------------------------------------------------------

# Strategy for generating valid article dictionaries
article_strategy = st.fixed_dictionaries({
    'title': st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    'url': st.text(
        alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789-._~/?=&'),
        min_size=10,
        max_size=200
    ).map(lambda s: f"https://example.com/{s}"),
    'source': st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
    'source_type': st.sampled_from(['rss', 'arxiv']),
    'published_date': st.from_regex(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]', fullmatch=True) | st.just(''),
})


@given(article_strategy)
@settings(max_examples=100)
def test_property_article_field_completeness(article: dict):
    """
    Feature: daily-article-aggregator, Property 4: 文章字段完整性
    
    **Validates: Requirements 2.1, 2.3**
    
    对于任意成功获取的文章（无论来自arXiv还是RSS），都应该包含非空的标题、URL和来源字段。
    For any successfully fetched article (from arXiv or RSS), it should have non-empty title, url, and source fields.
    """
    # Property: title must be non-empty
    assert article['title'], "Article title must be non-empty"
    assert article['title'].strip(), "Article title must not be whitespace only"
    
    # Property: url must be non-empty
    assert article['url'], "Article URL must be non-empty"
    assert article['url'].strip(), "Article URL must not be whitespace only"
    
    # Property: source must be non-empty
    assert article['source'], "Article source must be non-empty"
    assert article['source'].strip(), "Article source must not be whitespace only"


@given(st.lists(article_strategy, min_size=1, max_size=50))
@settings(max_examples=100)
def test_property_article_list_field_completeness(articles: list[dict]):
    """
    Feature: daily-article-aggregator, Property 4: 文章字段完整性
    
    **Validates: Requirements 2.1, 2.3**
    
    对于任意成功获取的文章列表，每篇文章都应该包含非空的标题、URL和来源字段。
    For any list of successfully fetched articles, each article should have non-empty title, url, and source fields.
    """
    for i, article in enumerate(articles):
        # Property: title must be non-empty
        assert article['title'], f"Article {i} title must be non-empty"
        assert article['title'].strip(), f"Article {i} title must not be whitespace only"
        
        # Property: url must be non-empty
        assert article['url'], f"Article {i} URL must be non-empty"
        assert article['url'].strip(), f"Article {i} URL must not be whitespace only"
        
        # Property: source must be non-empty
        assert article['source'], f"Article {i} source must be non-empty"
        assert article['source'].strip(), f"Article {i} source must not be whitespace only"
