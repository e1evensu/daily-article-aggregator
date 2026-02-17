"""
去重功能测试
Deduplication Tests

测试基于 URL 的去重功能。
Tests for URL-based deduplication functionality.
"""

import pytest

from src.utils.deduplication import (
    deduplicate_by_url,
    deduplicate_articles,
    normalize_url,
    merge_and_deduplicate,
)


class TestNormalizeUrl:
    """测试 URL 标准化"""
    
    def test_basic_normalization(self):
        """测试基本标准化"""
        assert normalize_url('https://example.com/path') == 'https://example.com/path'
    
    def test_lowercase_scheme(self):
        """测试 scheme 小写化"""
        assert normalize_url('HTTPS://example.com/path') == 'https://example.com/path'
    
    def test_lowercase_domain(self):
        """测试域名小写化"""
        assert normalize_url('https://EXAMPLE.COM/path') == 'https://example.com/path'
    
    def test_remove_query_params(self):
        """测试移除查询参数"""
        assert normalize_url('https://example.com/path?query=1') == 'https://example.com/path'
    
    def test_remove_fragment(self):
        """测试移除片段标识符"""
        assert normalize_url('https://example.com/path#section') == 'https://example.com/path'
    
    def test_empty_url(self):
        """测试空 URL"""
        assert normalize_url('') == ''
        assert normalize_url(None) == ''
    
    def test_preserve_path(self):
        """测试保留路径"""
        assert normalize_url('https://example.com/a/b/c') == 'https://example.com/a/b/c'


class TestDeduplicateByUrl:
    """测试 deduplicate_by_url 函数"""
    
    def test_no_duplicates(self):
        """测试没有重复的情况"""
        items = [
            {'title': 'A', 'url': 'https://example.com/1'},
            {'title': 'B', 'url': 'https://example.com/2'},
        ]
        
        result = deduplicate_by_url(items)
        
        assert len(result) == 2
    
    def test_with_duplicates(self):
        """测试有重复的情况"""
        items = [
            {'title': 'A', 'url': 'https://example.com/1'},
            {'title': 'B', 'url': 'https://example.com/2'},
            {'title': 'A Duplicate', 'url': 'https://example.com/1'},
        ]
        
        result = deduplicate_by_url(items)
        
        assert len(result) == 2
        assert result[0]['title'] == 'A'  # 保留首次出现
    
    def test_case_insensitive(self):
        """测试大小写不敏感"""
        items = [
            {'title': 'A', 'url': 'https://example.com/path'},
            {'title': 'B', 'url': 'https://EXAMPLE.COM/path'},
        ]
        
        result = deduplicate_by_url(items, normalize=True)
        
        assert len(result) == 1
    
    def test_query_params_ignored(self):
        """测试忽略查询参数"""
        items = [
            {'title': 'A', 'url': 'https://example.com/path'},
            {'title': 'B', 'url': 'https://example.com/path?query=1'},
        ]
        
        result = deduplicate_by_url(items, normalize=True)
        
        assert len(result) == 1
    
    def test_empty_list(self):
        """测试空列表"""
        result = deduplicate_by_url([])
        
        assert result == []
    
    def test_items_without_url(self):
        """测试没有 URL 的条目"""
        items = [
            {'title': 'A'},
            {'title': 'B', 'url': 'https://example.com/1'},
            {'title': 'C'},
        ]
        
        result = deduplicate_by_url(items)
        
        # 没有 URL 的条目应该被保留
        assert len(result) == 3
    
    def test_custom_url_key(self):
        """测试自定义 URL 键名"""
        items = [
            {'title': 'A', 'link': 'https://example.com/1'},
            {'title': 'B', 'link': 'https://example.com/2'},
            {'title': 'A Dup', 'link': 'https://example.com/1'},
        ]
        
        result = deduplicate_by_url(items, url_key='link')
        
        assert len(result) == 2


class TestDeduplicateArticles:
    """测试 deduplicate_articles 函数"""
    
    def test_basic_deduplication(self):
        """测试基本去重"""
        articles = [
            {'title': 'Paper 1', 'url': 'https://arxiv.org/abs/2401.00001'},
            {'title': 'Paper 2', 'url': 'https://arxiv.org/abs/2401.00002'},
            {'title': 'Paper 1 Copy', 'url': 'https://arxiv.org/abs/2401.00001'},
        ]
        
        result = deduplicate_articles(articles)
        
        assert len(result) == 2


class TestMergeAndDeduplicate:
    """测试 merge_and_deduplicate 函数"""
    
    def test_merge_multiple_lists(self):
        """测试合并多个列表"""
        list1 = [{'title': 'A', 'url': 'https://example.com/1'}]
        list2 = [{'title': 'B', 'url': 'https://example.com/2'}]
        list3 = [{'title': 'C', 'url': 'https://example.com/3'}]
        
        result = merge_and_deduplicate(list1, list2, list3)
        
        assert len(result) == 3
    
    def test_merge_with_duplicates(self):
        """测试合并时去重"""
        list1 = [{'title': 'A', 'url': 'https://example.com/1'}]
        list2 = [{'title': 'B', 'url': 'https://example.com/2'}]
        list3 = [{'title': 'A Copy', 'url': 'https://example.com/1'}]
        
        result = merge_and_deduplicate(list1, list2, list3)
        
        assert len(result) == 2


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# Strategy for generating valid URLs
url_strategy = st.from_regex(
    r'https://[a-z]+\.[a-z]+/[a-z0-9]+',
    fullmatch=True
)

# Strategy for generating items with URLs
item_strategy = st.fixed_dictionaries({
    'title': st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
    'url': url_strategy,
})


@given(st.lists(item_strategy, min_size=0, max_size=50))
@settings(max_examples=100)
def test_property_url_deduplication_preserves_unique(items: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 2: URL-based Deduplication Preserves Unique Entries
    
    **Validates: Requirements 1.4**
    
    对于任意包含可能重复 URL 的文章列表，去重后：
    - 结果中所有 URL 都是唯一的
    - 输入中的每个唯一 URL 在输出中恰好出现一次
    - 唯一 URL 的总数被保留
    
    For any list of articles with potentially duplicate URLs, after deduplication:
    - All URLs in the result are unique
    - Every unique URL from the input appears exactly once in the output
    - The total count of unique URLs is preserved
    """
    result = deduplicate_by_url(items)
    
    # Property: All URLs in result are unique
    result_urls = [item['url'] for item in result]
    assert len(result_urls) == len(set(result_urls)), \
        "All URLs in result should be unique"
    
    # Property: Every unique URL from input appears in output
    input_unique_urls = set(normalize_url(item['url']) for item in items)
    output_urls = set(normalize_url(item['url']) for item in result)
    assert input_unique_urls == output_urls, \
        "Every unique URL from input should appear in output"
    
    # Property: Count of unique URLs is preserved
    assert len(result) == len(input_unique_urls), \
        f"Result count {len(result)} should match unique URL count {len(input_unique_urls)}"


@given(st.lists(item_strategy, min_size=0, max_size=30))
@settings(max_examples=100)
def test_property_deduplication_preserves_first_occurrence(items: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 2: URL-based Deduplication Preserves Unique Entries
    
    **Validates: Requirements 1.4**
    
    去重应保留首次出现的条目。
    Deduplication should preserve the first occurrence.
    """
    result = deduplicate_by_url(items)
    
    # 构建 URL 到首次出现条目的映射
    # Build mapping from URL to first occurrence
    first_occurrence: dict[str, dict] = {}
    for item in items:
        normalized = normalize_url(item['url'])
        if normalized not in first_occurrence:
            first_occurrence[normalized] = item
    
    # Property: 结果中的每个条目应该是首次出现的条目
    for result_item in result:
        normalized = normalize_url(result_item['url'])
        expected = first_occurrence[normalized]
        assert result_item['title'] == expected['title'], \
            f"Result item should be the first occurrence"


@given(
    st.lists(item_strategy, min_size=0, max_size=20),
    st.lists(item_strategy, min_size=0, max_size=20),
)
@settings(max_examples=50)
def test_property_merge_deduplication(list1: list[dict], list2: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 2: URL-based Deduplication Preserves Unique Entries
    
    **Validates: Requirements 1.4**
    
    合并多个列表后去重应该保留所有唯一 URL。
    Merging multiple lists and deduplicating should preserve all unique URLs.
    """
    result = merge_and_deduplicate(list1, list2)
    
    # 计算所有唯一 URL
    all_urls = set()
    for item in list1 + list2:
        all_urls.add(normalize_url(item['url']))
    
    # Property: 结果中的 URL 数量应等于唯一 URL 数量
    assert len(result) == len(all_urls), \
        f"Result count {len(result)} should match unique URL count {len(all_urls)}"
    
    # Property: 结果中的所有 URL 都是唯一的
    result_urls = [normalize_url(item['url']) for item in result]
    assert len(result_urls) == len(set(result_urls)), \
        "All URLs in result should be unique"
