"""
PWCFetcher 单元测试和属性测试
Unit tests and property-based tests for PWCFetcher

测试 Papers With Code 获取器的各项功能。
Tests for Papers With Code fetcher functionality.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.fetchers.pwc_fetcher import PWCFetcher, parse_pwc_paper


class TestPWCFetcherInit:
    """测试 PWCFetcher 初始化"""
    
    def test_default_config(self):
        """测试默认配置"""
        fetcher = PWCFetcher({})
        
        assert fetcher.enabled is True
        assert fetcher.timeout == 30
        assert fetcher.limit == 50
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = {
            'enabled': False,
            'timeout': 60,
            'limit': 100
        }
        fetcher = PWCFetcher(config)
        
        assert fetcher.enabled is False
        assert fetcher.timeout == 60
        assert fetcher.limit == 100
    
    def test_is_enabled(self):
        """测试 is_enabled 方法"""
        fetcher_enabled = PWCFetcher({'enabled': True})
        fetcher_disabled = PWCFetcher({'enabled': False})
        
        assert fetcher_enabled.is_enabled() is True
        assert fetcher_disabled.is_enabled() is False


class TestPWCFetcherFetch:
    """测试 PWCFetcher fetch 方法"""
    
    def test_fetch_disabled(self):
        """测试禁用时的 fetch"""
        fetcher = PWCFetcher({'enabled': False})
        result = fetcher.fetch()
        
        assert result.is_success() is False
        assert result.error == 'Fetcher is disabled'
        assert len(result.items) == 0
    
    def test_fetch_with_mock(self):
        """使用 mock 测试 fetch"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'results': [
                {
                    'title': 'A New AI Paper',
                    'abstract': 'This paper presents a new approach...',
                    'url_abs': 'https://arxiv.org/abs/2401.12345',
                    'published': '2024-01-15',
                    'repository': {
                        'url': 'https://github.com/user/repo',
                        'stars': 500
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('src.fetchers.pwc_fetcher.requests.get', return_value=mock_response):
            fetcher = PWCFetcher({})
            result = fetcher.fetch()
            
            assert result.is_success() is True
            assert result.source_type == 'pwc'
            assert len(result.items) == 1
            assert result.items[0]['title'] == 'A New AI Paper'
            assert result.items[0]['github_stars'] == 500


class TestParsePwcPaper:
    """测试 parse_pwc_paper 函数"""
    
    def test_parse_complete_paper(self):
        """测试解析完整论文"""
        paper = {
            'title': 'A New AI Paper',
            'abstract': 'This paper presents a new approach...',
            'url_abs': 'https://arxiv.org/abs/2401.12345',
            'published': '2024-01-15',
            'repository': {
                'url': 'https://github.com/user/repo',
                'stars': 500
            },
            'authors': ['Alice', 'Bob']
        }
        
        result = parse_pwc_paper(paper)
        
        assert result is not None
        assert result['title'] == 'A New AI Paper'
        assert result['abstract'] == 'This paper presents a new approach...'
        assert result['url'] == 'https://arxiv.org/abs/2401.12345'
        assert result['github_url'] == 'https://github.com/user/repo'
        assert result['github_stars'] == 500
        assert result['source_type'] == 'pwc'
    
    def test_parse_paper_missing_title(self):
        """测试缺少标题的论文"""
        paper = {
            'title': '',
            'abstract': 'Test abstract',
        }
        
        result = parse_pwc_paper(paper)
        
        assert result is None
    
    def test_parse_paper_with_repositories_list(self):
        """测试使用 repositories 列表"""
        paper = {
            'title': 'Test Paper',
            'abstract': 'Test abstract',
            'url_abs': 'https://arxiv.org/abs/2401.99999',
            'repositories': [
                {'url': 'https://github.com/user/repo1', 'stars': 100},
                {'url': 'https://github.com/user/repo2', 'stars': 200}
            ]
        }
        
        result = parse_pwc_paper(paper)
        
        assert result is not None
        assert result['github_url'] == 'https://github.com/user/repo1'
        assert result['github_stars'] == 100
    
    def test_parse_paper_no_github(self):
        """测试没有 GitHub 信息的论文"""
        paper = {
            'title': 'Test Paper',
            'abstract': 'Test abstract',
            'url_abs': 'https://arxiv.org/abs/2401.11111',
        }
        
        result = parse_pwc_paper(paper)
        
        assert result is not None
        assert result['github_url'] is None
        assert result['github_stars'] is None
    
    def test_parse_paper_with_id_fallback(self):
        """测试使用 ID 构建 URL"""
        paper = {
            'title': 'Test Paper',
            'id': 'test-paper-id',
        }
        
        result = parse_pwc_paper(paper)
        
        assert result is not None
        assert result['url'] == 'https://paperswithcode.com/paper/test-paper-id'


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# Strategy for generating valid GitHub stars
github_stars_strategy = st.integers(min_value=0, max_value=1000000) | st.none()

# Strategy for generating valid PWC paper entries
pwc_paper_strategy = st.fixed_dictionaries({
    'title': st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    'abstract': st.text(min_size=0, max_size=1000),
    'url_abs': st.from_regex(r'https://arxiv\.org/abs/[0-9]{4}\.[0-9]{5}', fullmatch=True) | st.just(''),
    'published': st.from_regex(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]', fullmatch=True) | st.just(''),
    'repository': st.fixed_dictionaries({
        'url': st.from_regex(r'https://github\.com/[a-z]+/[a-z]+', fullmatch=True) | st.just(''),
        'stars': github_stars_strategy,
    }) | st.none(),
    'authors': st.lists(st.text(min_size=1, max_size=50).filter(lambda s: s.strip()), min_size=0, max_size=5),
})


@given(pwc_paper_strategy)
@settings(max_examples=100)
def test_property_pwc_paper_parsing_completeness(paper: dict):
    """
    Feature: aggregator-advanced-features, Property 6: PWC Paper Parsing Completeness
    
    **Validates: Requirements 3.3**
    
    对于任意有效的 Papers With Code API 响应，解析器应提取所有必需字段
    （title, abstract, url, github_url, github_stars）且类型正确。
    
    For any valid Papers With Code API response, the parser SHALL extract all
    required fields (title, abstract, url, github_url, github_stars) with correct types.
    """
    result = parse_pwc_paper(paper)
    
    # Property: Result should not be None for valid input (has title)
    assert result is not None, "Valid paper should produce a result"
    
    # Property: Title must be non-empty and match input
    assert result['title'], "Title must be non-empty"
    assert result['title'] == paper['title'].strip(), \
        f"Title {result['title']} should match input {paper['title']}"
    
    # Property: Abstract must be a string
    assert isinstance(result['abstract'], str), "Abstract must be a string"
    
    # Property: URL must be a string (can be empty if no URL provided)
    assert isinstance(result['url'], str), "URL must be a string"
    
    # Property: GitHub URL must be None or a string
    assert result['github_url'] is None or isinstance(result['github_url'], str), \
        "GitHub URL must be None or a string"
    
    # Property: GitHub stars must be None or a non-negative integer
    if result['github_stars'] is not None:
        assert isinstance(result['github_stars'], int), \
            "GitHub stars must be an integer"
        assert result['github_stars'] >= 0, \
            f"GitHub stars {result['github_stars']} must be non-negative"
    
    # Property: If repository is provided with URL, github_url should be set
    if paper.get('repository') and paper['repository'].get('url'):
        assert result['github_url'] == paper['repository']['url'], \
            "GitHub URL should match repository URL"
    
    # Property: If repository is provided with stars, github_stars should be set
    if paper.get('repository') and paper['repository'].get('stars') is not None:
        assert result['github_stars'] == paper['repository']['stars'], \
            "GitHub stars should match repository stars"
    
    # Property: Published date must be a string
    assert isinstance(result['published_date'], str), \
        "Published date must be a string"
    
    # Property: If published date is non-empty, it should be in YYYY-MM-DD format
    if result['published_date']:
        assert len(result['published_date']) == 10, \
            f"Published date {result['published_date']} should be in YYYY-MM-DD format"
    
    # Property: Source type must be 'pwc'
    assert result['source_type'] == 'pwc', "Source type must be 'pwc'"
    
    # Property: Authors must be a list
    assert isinstance(result['authors'], list), "Authors must be a list"


@given(st.lists(pwc_paper_strategy, min_size=0, max_size=20))
@settings(max_examples=50)
def test_property_pwc_batch_parsing(papers: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 6: PWC Paper Parsing Completeness (Batch)
    
    **Validates: Requirements 3.3**
    
    对于任意论文列表，每篇有效的论文都应被正确解析。
    For any list of papers, each valid paper should be correctly parsed.
    """
    for i, paper in enumerate(papers):
        result = parse_pwc_paper(paper)
        
        # Property: Each valid paper should produce a result
        assert result is not None, f"Paper {i} should produce a result"
        
        # Property: Each result should have required fields
        assert 'title' in result, f"Paper {i} result should have title"
        assert 'abstract' in result, f"Paper {i} result should have abstract"
        assert 'url' in result, f"Paper {i} result should have url"
        assert 'github_url' in result, f"Paper {i} result should have github_url"
        assert 'github_stars' in result, f"Paper {i} result should have github_stars"
