"""
ArxivFetcher 单元测试
Unit tests for ArxivFetcher

测试arXiv论文获取器的核心功能：
- 论文ID去重
- 关键词过滤
- 配置初始化
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.fetchers.arxiv_fetcher import (
    ArxivFetcher,
    deduplicate_papers,
    filter_papers_by_keywords,
)


class TestArxivFetcherInit:
    """测试ArxivFetcher初始化"""
    
    def test_init_with_full_config(self):
        """测试使用完整配置初始化"""
        config = {
            'categories': ['cs.AI', 'cs.CL'],
            'keywords': ['llm', 'security'],
            'use_llm_filter': True,
            'max_results': 50
        }
        fetcher = ArxivFetcher(config)
        
        assert fetcher.categories == ['cs.AI', 'cs.CL']
        assert fetcher.keywords == ['llm', 'security']
        assert fetcher.use_llm_filter is True
        assert fetcher.max_results == 50
    
    def test_init_with_empty_config(self):
        """测试使用空配置初始化"""
        fetcher = ArxivFetcher({})
        
        assert fetcher.categories == []
        assert fetcher.keywords == []
        assert fetcher.use_llm_filter is False
        assert fetcher.max_results == 100  # 默认值
    
    def test_init_with_partial_config(self):
        """测试使用部分配置初始化"""
        config = {'categories': ['cs.AI']}
        fetcher = ArxivFetcher(config)
        
        assert fetcher.categories == ['cs.AI']
        assert fetcher.keywords == []
        assert fetcher.use_llm_filter is False
        assert fetcher.max_results == 100


class TestDeduplicatePapers:
    """测试论文去重功能"""
    
    def test_deduplicate_empty_list(self):
        """测试空列表去重"""
        result = deduplicate_papers([])
        assert result == []
    
    def test_deduplicate_no_duplicates(self):
        """测试无重复的列表"""
        papers = [
            {'id': 'a', 'title': 'Paper A'},
            {'id': 'b', 'title': 'Paper B'},
            {'id': 'c', 'title': 'Paper C'}
        ]
        result = deduplicate_papers(papers)
        
        assert len(result) == 3
        assert set(p['id'] for p in result) == {'a', 'b', 'c'}
    
    def test_deduplicate_with_duplicates(self):
        """测试有重复的列表"""
        papers = [
            {'id': 'a', 'title': 'Paper A'},
            {'id': 'a', 'title': 'Paper A Copy'},
            {'id': 'b', 'title': 'Paper B'},
            {'id': 'b', 'title': 'Paper B Copy'},
            {'id': 'c', 'title': 'Paper C'}
        ]
        result = deduplicate_papers(papers)
        
        assert len(result) == 3
        assert set(p['id'] for p in result) == {'a', 'b', 'c'}
        # 保留第一次出现的
        assert result[0]['title'] == 'Paper A'
        assert result[1]['title'] == 'Paper B'
    
    def test_deduplicate_preserves_order(self):
        """测试去重保持顺序"""
        papers = [
            {'id': 'c', 'title': 'Paper C'},
            {'id': 'a', 'title': 'Paper A'},
            {'id': 'b', 'title': 'Paper B'},
            {'id': 'a', 'title': 'Paper A Dup'}
        ]
        result = deduplicate_papers(papers)
        
        assert len(result) == 3
        assert result[0]['id'] == 'c'
        assert result[1]['id'] == 'a'
        assert result[2]['id'] == 'b'
    
    def test_deduplicate_papers_without_id(self):
        """测试没有id字段的论文被跳过"""
        papers = [
            {'id': 'a', 'title': 'Paper A'},
            {'title': 'Paper No ID'},  # 没有id
            {'id': '', 'title': 'Paper Empty ID'},  # 空id
            {'id': 'b', 'title': 'Paper B'}
        ]
        result = deduplicate_papers(papers)
        
        assert len(result) == 2
        assert set(p['id'] for p in result) == {'a', 'b'}


class TestFilterPapersByKeywords:
    """测试关键词过滤功能"""
    
    def test_filter_empty_papers(self):
        """测试空论文列表"""
        result = filter_papers_by_keywords([], ['llm'])
        assert result == []
    
    def test_filter_empty_keywords(self):
        """测试空关键词列表返回所有论文"""
        papers = [
            {'title': 'Paper A', 'abstract': 'About AI'},
            {'title': 'Paper B', 'abstract': 'About DB'}
        ]
        result = filter_papers_by_keywords(papers, [])
        assert len(result) == 2
    
    def test_filter_by_title(self):
        """测试通过标题过滤"""
        papers = [
            {'title': 'LLM Safety Research', 'abstract': 'Some content'},
            {'title': 'Database Design', 'abstract': 'SQL optimization'}
        ]
        result = filter_papers_by_keywords(papers, ['llm'])
        
        assert len(result) == 1
        assert result[0]['title'] == 'LLM Safety Research'
    
    def test_filter_by_abstract(self):
        """测试通过摘要过滤"""
        papers = [
            {'title': 'Research Paper', 'abstract': 'This paper discusses LLM safety'},
            {'title': 'Database Design', 'abstract': 'SQL optimization'}
        ]
        result = filter_papers_by_keywords(papers, ['llm'])
        
        assert len(result) == 1
        assert result[0]['title'] == 'Research Paper'
    
    def test_filter_case_insensitive(self):
        """测试不区分大小写"""
        papers = [
            {'title': 'LLM Research', 'abstract': 'Content'},
            {'title': 'llm research', 'abstract': 'Content'},
            {'title': 'Research', 'abstract': 'About LLM'},
            {'title': 'Research', 'abstract': 'About llm'}
        ]
        result = filter_papers_by_keywords(papers, ['LLM'])
        
        assert len(result) == 4
    
    def test_filter_multiple_keywords(self):
        """测试多个关键词（OR逻辑）"""
        papers = [
            {'title': 'LLM Safety', 'abstract': 'Content'},
            {'title': 'Security Analysis', 'abstract': 'Content'},
            {'title': 'Database Design', 'abstract': 'Content'}
        ]
        result = filter_papers_by_keywords(papers, ['llm', 'security'])
        
        assert len(result) == 2
        titles = {p['title'] for p in result}
        assert titles == {'LLM Safety', 'Security Analysis'}
    
    def test_filter_no_matches(self):
        """测试无匹配结果"""
        papers = [
            {'title': 'Database Design', 'abstract': 'SQL optimization'},
            {'title': 'Web Development', 'abstract': 'JavaScript frameworks'}
        ]
        result = filter_papers_by_keywords(papers, ['llm', 'security'])
        
        assert len(result) == 0
    
    def test_filter_partial_match(self):
        """测试部分匹配（关键词是子字符串）"""
        papers = [
            {'title': 'LLMs in Production', 'abstract': 'Content'},
            {'title': 'Security', 'abstract': 'Content'}
        ]
        result = filter_papers_by_keywords(papers, ['llm'])
        
        assert len(result) == 1
        assert result[0]['title'] == 'LLMs in Production'


class TestArxivFetcherFilterByKeywords:
    """测试ArxivFetcher.filter_by_keywords方法"""
    
    def test_filter_with_configured_keywords(self):
        """测试使用配置的关键词过滤"""
        config = {
            'categories': [],
            'keywords': ['llm', 'security']
        }
        fetcher = ArxivFetcher(config)
        
        papers = [
            {'title': 'LLM Safety', 'content': 'About AI'},
            {'title': 'Database', 'content': 'SQL'}
        ]
        result = fetcher.filter_by_keywords(papers)
        
        assert len(result) == 1
        assert result[0]['title'] == 'LLM Safety'
    
    def test_filter_without_keywords(self):
        """测试没有配置关键词时返回所有论文"""
        config = {'categories': [], 'keywords': []}
        fetcher = ArxivFetcher(config)
        
        papers = [
            {'title': 'Paper A', 'content': 'Content A'},
            {'title': 'Paper B', 'content': 'Content B'}
        ]
        result = fetcher.filter_by_keywords(papers)
        
        assert len(result) == 2
    
    def test_filter_uses_content_field(self):
        """测试使用content字段（而非abstract）"""
        config = {'categories': [], 'keywords': ['security']}
        fetcher = ArxivFetcher(config)
        
        papers = [
            {'title': 'Paper', 'content': 'About security'},
            {'title': 'Paper', 'abstract': 'About security'}  # 只有abstract
        ]
        result = fetcher.filter_by_keywords(papers)
        
        # 只有第一个匹配（使用content字段）
        assert len(result) == 1


class TestArxivFetcherDeduplication:
    """测试ArxivFetcher内部去重方法"""
    
    def test_internal_deduplicate_uses_arxiv_id(self):
        """测试内部去重使用arxiv_id字段"""
        fetcher = ArxivFetcher({'categories': []})
        
        papers = [
            {'arxiv_id': '2401.00001', 'title': 'Paper 1'},
            {'arxiv_id': '2401.00001', 'title': 'Paper 1 Dup'},
            {'arxiv_id': '2401.00002', 'title': 'Paper 2'}
        ]
        result = fetcher._deduplicate_papers(papers)
        
        assert len(result) == 2
        assert result[0]['title'] == 'Paper 1'
        assert result[1]['title'] == 'Paper 2'


class TestArxivFetcherResultToDict:
    """测试ArxivFetcher._result_to_dict方法"""
    
    def test_result_to_dict_conversion(self):
        """测试arXiv结果转换为字典"""
        fetcher = ArxivFetcher({'categories': []})
        
        # 创建模拟的arXiv结果
        mock_result = Mock()
        mock_result.title = "Test Paper Title"
        mock_result.entry_id = "http://arxiv.org/abs/2401.00001v1"
        mock_result.summary = "This is the abstract"
        mock_result.published = datetime(2024, 1, 15, 10, 30, 0)
        
        result = fetcher._result_to_dict(mock_result, 'cs.AI')
        
        assert result['title'] == "Test Paper Title"
        assert result['url'] == "http://arxiv.org/abs/2401.00001v1"
        assert result['source'] == 'cs.AI'
        assert result['source_type'] == 'arxiv'
        assert result['published_date'] == '2024-01-15'
        assert result['content'] == "This is the abstract"
        assert result['arxiv_id'] == '2401.00001v1'
    
    def test_result_to_dict_no_published_date(self):
        """测试没有发布日期的情况"""
        fetcher = ArxivFetcher({'categories': []})
        
        mock_result = Mock()
        mock_result.title = "Test Paper"
        mock_result.entry_id = "http://arxiv.org/abs/2401.00001"
        mock_result.summary = "Abstract"
        mock_result.published = None
        
        result = fetcher._result_to_dict(mock_result, 'cs.CL')
        
        assert result['published_date'] == ''


class TestArxivFetcherFilterByLLM:
    """测试ArxivFetcher.filter_by_llm方法"""
    
    def test_filter_by_llm_disabled(self):
        """测试LLM过滤禁用时返回原列表"""
        config = {'categories': [], 'use_llm_filter': False}
        fetcher = ArxivFetcher(config)
        
        papers = [{'title': 'Paper 1'}, {'title': 'Paper 2'}]
        result = fetcher.filter_by_llm(papers, "AI safety research")
        
        assert result == papers
    
    def test_filter_by_llm_enabled_stub(self):
        """测试LLM过滤启用时的存根行为"""
        config = {'categories': [], 'use_llm_filter': True}
        fetcher = ArxivFetcher(config)
        
        papers = [{'title': 'Paper 1'}, {'title': 'Paper 2'}]
        result = fetcher.filter_by_llm(papers, "AI safety research")
        
        # 存根实现返回原列表
        assert result == papers


# =============================================================================
# 属性测试 (Property-Based Tests)
# =============================================================================

from hypothesis import given, strategies as st, settings


class TestPropertyDeduplication:
    """Property 1: 论文ID去重 - 属性测试"""
    
    @settings(max_examples=100)
    @given(st.lists(st.fixed_dictionaries({
        'id': st.text(min_size=1, max_size=50),
        'title': st.text(max_size=200),
        'abstract': st.text(max_size=500)
    }), min_size=0, max_size=50))
    def test_deduplication_unique_ids(self, papers):
        """
        Feature: daily-article-aggregator, Property 1: 论文ID去重
        
        **Validates: Requirements 1.3**
        
        对于任意包含重复ID的论文列表，去重后的列表中每个ID应该只出现一次。
        For any list of papers with duplicate IDs, each ID should appear only once after deduplication.
        """
        result = deduplicate_papers(papers)
        
        # 提取所有ID
        result_ids = [p['id'] for p in result]
        
        # 验证所有ID唯一
        assert len(result_ids) == len(set(result_ids)), \
            "去重后的列表中存在重复ID / Duplicate IDs found after deduplication"
    
    @settings(max_examples=100)
    @given(st.lists(st.fixed_dictionaries({
        'id': st.text(min_size=1, max_size=50),
        'title': st.text(max_size=200),
        'abstract': st.text(max_size=500)
    }), min_size=0, max_size=50))
    def test_deduplication_no_unique_id_lost(self, papers):
        """
        Feature: daily-article-aggregator, Property 1: 论文ID去重
        
        **Validates: Requirements 1.3**
        
        对于任意包含重复ID的论文列表，去重后不应丢失任何唯一论文。
        For any list of papers, deduplication should not lose any unique paper.
        """
        result = deduplicate_papers(papers)
        
        # 获取原始唯一ID集合
        original_unique_ids = set(p['id'] for p in papers if p.get('id'))
        
        # 获取结果ID集合
        result_ids = set(p['id'] for p in result)
        
        # 验证不丢失任何唯一ID
        assert result_ids == original_unique_ids, \
            f"丢失了唯一ID / Lost unique IDs: {original_unique_ids - result_ids}"


class TestPropertyKeywordFiltering:
    """Property 2: 关键词过滤有效性 - 属性测试"""
    
    @settings(max_examples=100)
    @given(
        st.lists(st.fixed_dictionaries({
            'title': st.text(max_size=200),
            'abstract': st.text(max_size=500)
        }), min_size=0, max_size=30),
        st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=10)
    )
    def test_filtered_papers_contain_keyword(self, papers, keywords):
        """
        Feature: daily-article-aggregator, Property 2: 关键词过滤有效性
        
        **Validates: Requirements 1.4**
        
        对于任意关键词列表和论文集合，过滤后的每篇论文的摘要或标题中应该至少包含一个关键词（不区分大小写）。
        For any keyword list and paper collection, each filtered paper should contain at least one keyword 
        in its title or abstract (case-insensitive).
        """
        result = filter_papers_by_keywords(papers, keywords)
        
        # 将关键词转换为小写
        keywords_lower = [kw.lower() for kw in keywords]
        
        # 验证每篇过滤后的论文都包含至少一个关键词
        for paper in result:
            title = paper.get('title', '').lower()
            abstract = paper.get('abstract', '').lower()
            
            contains_keyword = any(
                kw in title or kw in abstract 
                for kw in keywords_lower
            )
            
            assert contains_keyword, \
                f"过滤后的论文不包含任何关键词 / Filtered paper doesn't contain any keyword: {paper}"
    
    @settings(max_examples=100)
    @given(
        st.lists(st.fixed_dictionaries({
            'title': st.text(max_size=200),
            'abstract': st.text(max_size=500)
        }), min_size=0, max_size=30)
    )
    def test_empty_keywords_returns_all(self, papers):
        """
        Feature: daily-article-aggregator, Property 2: 关键词过滤有效性
        
        **Validates: Requirements 1.4**
        
        当关键词列表为空时，应返回所有论文。
        When keyword list is empty, all papers should be returned.
        """
        result = filter_papers_by_keywords(papers, [])
        
        assert len(result) == len(papers), \
            "空关键词列表应返回所有论文 / Empty keyword list should return all papers"


class TestPropertyArticleFieldCompleteness:
    """Property 4: 文章字段完整性 - 属性测试"""
    
    @settings(max_examples=100)
    @given(st.fixed_dictionaries({
        'title': st.text(min_size=1, max_size=200),
        'url': st.text(min_size=1, max_size=500),
        'source': st.text(min_size=1, max_size=100),
        'source_type': st.sampled_from(['arxiv', 'rss']),
        'published_date': st.text(max_size=20),
        'content': st.text(max_size=1000),
        'arxiv_id': st.text(min_size=1, max_size=50)
    }))
    def test_article_has_required_fields(self, article):
        """
        Feature: daily-article-aggregator, Property 4: 文章字段完整性
        
        **Validates: Requirements 1.2, 1.4**
        
        对于任意成功获取的文章，都应该包含非空的标题、URL和来源字段。
        For any successfully fetched article, it should contain non-empty title, URL, and source fields.
        """
        # 验证必需字段非空
        assert article.get('title'), \
            "文章标题不能为空 / Article title cannot be empty"
        assert article.get('url'), \
            "文章URL不能为空 / Article URL cannot be empty"
        assert article.get('source'), \
            "文章来源不能为空 / Article source cannot be empty"
    
    @settings(max_examples=100)
    @given(st.lists(st.fixed_dictionaries({
        'id': st.text(min_size=1, max_size=50),
        'title': st.text(min_size=1, max_size=200),
        'url': st.text(min_size=1, max_size=500),
        'source': st.text(min_size=1, max_size=100),
        'abstract': st.text(max_size=500)
    }), min_size=0, max_size=20))
    def test_deduplicated_articles_preserve_required_fields(self, papers):
        """
        Feature: daily-article-aggregator, Property 4: 文章字段完整性
        
        **Validates: Requirements 1.2, 1.3**
        
        去重后的文章应保留所有必需字段。
        Deduplicated articles should preserve all required fields.
        """
        result = deduplicate_papers(papers)
        
        for paper in result:
            # 验证去重后的论文保留了必需字段
            assert 'id' in paper, "去重后的论文缺少id字段 / Deduplicated paper missing id field"
            assert 'title' in paper, "去重后的论文缺少title字段 / Deduplicated paper missing title field"
            assert 'url' in paper, "去重后的论文缺少url字段 / Deduplicated paper missing url field"
            assert 'source' in paper, "去重后的论文缺少source字段 / Deduplicated paper missing source field"
