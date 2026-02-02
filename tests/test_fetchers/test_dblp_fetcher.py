"""
DBLPFetcher 单元测试和属性测试
Unit tests and property-based tests for DBLPFetcher

测试 DBLP RSS 获取器的各项功能。
Tests for DBLP RSS fetcher functionality.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.fetchers.dblp_fetcher import DBLPFetcher, parse_dblp_entry


class TestDBLPFetcherInit:
    """测试 DBLPFetcher 初始化"""
    
    def test_default_config(self):
        """测试默认配置"""
        fetcher = DBLPFetcher({})
        
        assert fetcher.enabled is True
        assert fetcher.timeout == 30
        assert fetcher.max_workers == 4
        assert set(fetcher.enabled_conferences) == {'sp', 'ccs', 'uss', 'ndss'}
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = {
            'enabled': False,
            'conferences': ['sp', 'ccs'],
            'timeout': 60,
            'max_workers': 2
        }
        fetcher = DBLPFetcher(config)
        
        assert fetcher.enabled is False
        assert fetcher.timeout == 60
        assert fetcher.max_workers == 2
        assert fetcher.enabled_conferences == ['sp', 'ccs']
    
    def test_is_enabled(self):
        """测试 is_enabled 方法"""
        fetcher_enabled = DBLPFetcher({'enabled': True})
        fetcher_disabled = DBLPFetcher({'enabled': False})
        
        assert fetcher_enabled.is_enabled() is True
        assert fetcher_disabled.is_enabled() is False


class TestDBLPFetcherFetch:
    """测试 DBLPFetcher fetch 方法"""
    
    def test_fetch_disabled(self):
        """测试禁用时的 fetch"""
        fetcher = DBLPFetcher({'enabled': False})
        result = fetcher.fetch()
        
        assert result.is_success() is False
        assert result.error == 'Fetcher is disabled'
        assert len(result.items) == 0
    
    def test_fetch_no_valid_conferences(self):
        """测试无有效会议配置时的 fetch"""
        fetcher = DBLPFetcher({'conferences': ['invalid']})
        result = fetcher.fetch()
        
        assert result.is_success() is False
        assert 'No valid conferences' in result.error
    
    def test_fetch_with_mock(self):
        """使用 mock 测试 fetch"""
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            MagicMock(
                title='Security Paper 1',
                link='https://dblp.org/rec/conf/sp/2024/paper1',
                authors=[{'name': 'Alice'}, {'name': 'Bob'}]
            )
        ]
        mock_feed.entries[0].get = lambda key, default='': {
            'title': 'Security Paper 1',
            'link': 'https://dblp.org/rec/conf/sp/2024/paper1',
        }.get(key, default)
        
        with patch('src.fetchers.dblp_fetcher.feedparser.parse', return_value=mock_feed):
            fetcher = DBLPFetcher({'conferences': ['sp']})
            result = fetcher.fetch()
            
            assert result.source_type == 'dblp'
            assert len(result.items) == 1
            assert result.items[0]['title'] == 'Security Paper 1'
            assert result.items[0]['conference'] == 'IEEE S&P'


class TestParseDblpEntry:
    """测试 parse_dblp_entry 函数"""
    
    def test_parse_complete_entry(self):
        """测试解析完整条目"""
        entry = {
            'title': 'A Security Paper',
            'link': 'https://dblp.org/rec/conf/sp/2024/paper1',
            'authors': [{'name': 'Alice'}, {'name': 'Bob'}],
            'published_date': '2024-01-15'
        }
        
        result = parse_dblp_entry(entry, 'sp', 'IEEE S&P')
        
        assert result is not None
        assert result['title'] == 'A Security Paper'
        assert result['url'] == 'https://dblp.org/rec/conf/sp/2024/paper1'
        assert result['authors'] == ['Alice', 'Bob']
        assert result['conference'] == 'IEEE S&P'
        assert result['conference_id'] == 'sp'
        assert result['year'] == 2024
        assert result['source_type'] == 'dblp'
    
    def test_parse_entry_missing_title(self):
        """测试缺少标题的条目"""
        entry = {
            'title': '',
            'link': 'https://dblp.org/rec/conf/sp/2024/paper1',
        }
        
        result = parse_dblp_entry(entry, 'sp', 'IEEE S&P')
        
        assert result is None
    
    def test_parse_entry_missing_url(self):
        """测试缺少 URL 的条目"""
        entry = {
            'title': 'A Paper',
            'link': '',
        }
        
        result = parse_dblp_entry(entry, 'sp', 'IEEE S&P')
        
        assert result is None
    
    def test_parse_entry_with_id_fallback(self):
        """测试使用 id 作为 URL 的回退"""
        entry = {
            'title': 'A Paper',
            'link': '',
            'id': 'https://dblp.org/rec/conf/ccs/2023/paper2',
        }
        
        result = parse_dblp_entry(entry, 'ccs', 'ACM CCS')
        
        assert result is not None
        assert result['url'] == 'https://dblp.org/rec/conf/ccs/2023/paper2'
        assert result['year'] == 2023
    
    def test_parse_entry_author_string(self):
        """测试作者为字符串格式"""
        entry = {
            'title': 'A Paper',
            'link': 'https://dblp.org/rec/conf/uss/2024/paper1',
            'author': 'Alice, Bob, Charlie',
        }
        
        result = parse_dblp_entry(entry, 'uss', 'USENIX Security')
        
        assert result is not None
        assert result['authors'] == ['Alice', 'Bob', 'Charlie']


class TestDeduplication:
    """测试去重功能"""
    
    def test_deduplicate_by_url(self):
        """测试 URL 去重"""
        fetcher = DBLPFetcher({})
        
        items = [
            {'title': 'Paper 1', 'url': 'https://example.com/1'},
            {'title': 'Paper 2', 'url': 'https://example.com/2'},
            {'title': 'Paper 1 Duplicate', 'url': 'https://example.com/1'},
            {'title': 'Paper 3', 'url': 'https://example.com/3'},
        ]
        
        result = fetcher._deduplicate_by_url(items)
        
        assert len(result) == 3
        urls = [item['url'] for item in result]
        assert urls == [
            'https://example.com/1',
            'https://example.com/2',
            'https://example.com/3'
        ]
        # 保留首次出现的条目
        assert result[0]['title'] == 'Paper 1'


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# Strategy for generating valid DBLP entry dictionaries
dblp_entry_strategy = st.fixed_dictionaries({
    'title': st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    'link': st.from_regex(
        r'https://dblp\.org/rec/conf/(sp|ccs|uss|ndss)/20[0-9]{2}/[a-z0-9]+',
        fullmatch=True
    ),
    'authors': st.lists(
        st.fixed_dictionaries({
            'name': st.text(min_size=1, max_size=50).filter(lambda s: s.strip())
        }),
        min_size=0,
        max_size=10
    ),
    'published_date': st.from_regex(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]', fullmatch=True) | st.just(''),
})

conference_strategy = st.sampled_from(['sp', 'ccs', 'uss', 'ndss'])
conf_name_strategy = st.sampled_from(['IEEE S&P', 'ACM CCS', 'USENIX Security', 'NDSS'])


@given(dblp_entry_strategy, conference_strategy, conf_name_strategy)
@settings(max_examples=100)
def test_property_dblp_entry_parsing_completeness(
    entry: dict, 
    conference: str, 
    conf_name: str
):
    """
    Feature: aggregator-advanced-features, Property 3: DBLP Entry Parsing Completeness
    
    **Validates: Requirements 1.2**
    
    对于任意有效的 DBLP RSS 条目，解析器应提取所有必需字段（title, authors, conference, year, URL），
    且这些字段对于有效输入不应为空。
    
    For any valid DBLP RSS entry, the parser SHALL extract all required fields
    (title, authors, conference, year, URL) and none of these fields shall be
    empty for valid input.
    """
    result = parse_dblp_entry(entry, conference, conf_name)
    
    # Property: Result should not be None for valid input
    assert result is not None, "Valid entry should produce a result"
    
    # Property: Title must be non-empty
    assert result['title'], "Title must be non-empty"
    assert result['title'].strip(), "Title must not be whitespace only"
    
    # Property: URL must be non-empty
    assert result['url'], "URL must be non-empty"
    assert result['url'].strip(), "URL must not be whitespace only"
    
    # Property: Conference must match input
    assert result['conference'] == conf_name, \
        f"Conference {result['conference']} should match {conf_name}"
    
    # Property: Conference ID must match input
    assert result['conference_id'] == conference, \
        f"Conference ID {result['conference_id']} should match {conference}"
    
    # Property: Year should be extracted from URL (valid URLs contain year)
    assert result['year'] is not None, "Year should be extracted from valid URL"
    assert 2000 <= result['year'] <= 2099, f"Year {result['year']} should be valid"
    
    # Property: Source type must be 'dblp'
    assert result['source_type'] == 'dblp', "Source type must be 'dblp'"
    
    # Property: Authors list should match input count
    expected_author_count = len([a for a in entry.get('authors', []) 
                                  if isinstance(a, dict) and a.get('name', '').strip()])
    assert len(result['authors']) == expected_author_count, \
        f"Author count {len(result['authors'])} should match {expected_author_count}"


@given(st.lists(
    st.fixed_dictionaries({
        'title': st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
        'url': st.from_regex(r'https://example\.com/[a-z0-9]+', fullmatch=True),
    }),
    min_size=0,
    max_size=50
))
@settings(max_examples=100)
def test_property_url_deduplication_preserves_unique(items: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 2: URL-based Deduplication Preserves Unique Entries
    
    **Validates: Requirements 1.4**
    
    对于任意论文列表，去重后：
    - 所有 URL 都是唯一的
    - 输入中的每个唯一 URL 在输出中恰好出现一次
    - 唯一 URL 的总数被保留
    
    For any list of articles with potentially duplicate URLs, after deduplication:
    - All URLs in the result are unique
    - Every unique URL from the input appears exactly once in the output
    - The total count of unique URLs is preserved
    """
    fetcher = DBLPFetcher({})
    result = fetcher._deduplicate_by_url(items)
    
    # Property: All URLs in result are unique
    result_urls = [item['url'] for item in result]
    assert len(result_urls) == len(set(result_urls)), \
        "All URLs in result should be unique"
    
    # Property: Every unique URL from input appears in output
    input_unique_urls = set(item['url'] for item in items)
    output_urls = set(item['url'] for item in result)
    assert input_unique_urls == output_urls, \
        "Every unique URL from input should appear in output"
    
    # Property: Count of unique URLs is preserved
    assert len(result) == len(input_unique_urls), \
        f"Result count {len(result)} should match unique URL count {len(input_unique_urls)}"
