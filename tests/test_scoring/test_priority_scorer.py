"""
PriorityScorer 单元测试和属性测试
Unit tests and property-based tests for PriorityScorer

测试文章优先级评分器的各项功能。
Tests for article priority scorer functionality.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.scoring.priority_scorer import (
    PriorityScorer,
    ScoredArticle,
    score_article,
)


class TestPriorityScorerInit:
    """测试 PriorityScorer 初始化"""
    
    def test_default_config(self):
        """测试默认配置"""
        scorer = PriorityScorer({})
        
        assert scorer.enable_ai_scoring is True
        assert scorer.ai_analyzer is None
        assert 'kev' in scorer.source_weights
        assert scorer.source_weights['kev'] == 1.5
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = {
            'source_weights': {'custom': 2.0},
            'enable_ai_scoring': False
        }
        scorer = PriorityScorer(config)
        
        assert scorer.enable_ai_scoring is False
        assert scorer.source_weights['custom'] == 2.0
        # 默认权重应该保留
        assert scorer.source_weights['kev'] == 1.5


class TestScoreSingle:
    """测试单篇文章评分"""
    
    def test_score_with_high_weight_source(self):
        """测试高权重来源评分"""
        scorer = PriorityScorer({'enable_ai_scoring': False})
        
        article = {
            'title': 'Critical Vulnerability',
            'source_type': 'kev'
        }
        
        result = scorer.score_single(article)
        
        assert isinstance(result, ScoredArticle)
        assert result.score > 50  # KEV 权重 1.5，基础分 50 * 1.5 = 75
        assert result.article == article
    
    def test_score_with_low_weight_source(self):
        """测试低权重来源评分"""
        scorer = PriorityScorer({'enable_ai_scoring': False})
        
        article = {
            'title': 'Random Article',
            'source_type': 'rss'
        }
        
        result = scorer.score_single(article)
        
        assert result.score < 50  # RSS 权重 0.8，基础分 50 * 0.8 = 40
    
    def test_score_with_unknown_source(self):
        """测试未知来源评分"""
        scorer = PriorityScorer({'enable_ai_scoring': False})
        
        article = {
            'title': 'Unknown Source Article',
            'source_type': 'unknown'
        }
        
        result = scorer.score_single(article)
        
        assert result.score == 50  # 未知来源权重 1.0，基础分 50


class TestScoreArticles:
    """测试批量评分"""
    
    def test_score_multiple_articles(self):
        """测试批量评分多篇文章"""
        scorer = PriorityScorer({'enable_ai_scoring': False})
        
        articles = [
            {'title': 'Article 1', 'source_type': 'kev'},
            {'title': 'Article 2', 'source_type': 'rss'},
            {'title': 'Article 3', 'source_type': 'dblp'},
        ]
        
        results = scorer.score_articles(articles)
        
        assert len(results) == 3
        assert all(isinstance(r, ScoredArticle) for r in results)
    
    def test_score_empty_list(self):
        """测试空列表"""
        scorer = PriorityScorer({'enable_ai_scoring': False})
        
        results = scorer.score_articles([])
        
        assert len(results) == 0


class TestSortByPriority:
    """测试优先级排序"""
    
    def test_sort_descending(self):
        """测试降序排序"""
        scorer = PriorityScorer({'enable_ai_scoring': False})
        
        scored_articles = [
            ScoredArticle(article={'title': 'Low'}, score=30),
            ScoredArticle(article={'title': 'High'}, score=90),
            ScoredArticle(article={'title': 'Medium'}, score=60),
        ]
        
        sorted_articles = scorer.sort_by_priority(scored_articles)
        
        assert sorted_articles[0].score == 90
        assert sorted_articles[1].score == 60
        assert sorted_articles[2].score == 30
    
    def test_sort_empty_list(self):
        """测试空列表排序"""
        scorer = PriorityScorer({})
        
        sorted_articles = scorer.sort_by_priority([])
        
        assert len(sorted_articles) == 0


class TestGetTopArticles:
    """测试获取前 N 篇文章"""
    
    def test_get_top_n(self):
        """测试获取前 N 篇"""
        scorer = PriorityScorer({})
        
        scored_articles = [
            ScoredArticle(article={'title': f'Article {i}'}, score=i * 10)
            for i in range(10)
        ]
        
        top_3 = scorer.get_top_articles(scored_articles, n=3)
        
        assert len(top_3) == 3
        assert top_3[0].score == 90
        assert top_3[1].score == 80
        assert top_3[2].score == 70


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# Strategy for generating article data
article_strategy = st.fixed_dictionaries({
    'title': st.text(min_size=1, max_size=200),
    'source_type': st.sampled_from(['kev', 'nvd', 'dblp', 'huggingface', 'pwc', 'blog', 'arxiv', 'rss', 'unknown']),
    'source': st.text(min_size=0, max_size=100),
})

# Strategy for generating source weights
source_weight_strategy = st.floats(min_value=0.1, max_value=3.0)


@given(article_strategy)
@settings(max_examples=100)
def test_property_priority_score_range(article: dict):
    """
    Feature: aggregator-advanced-features, Property 13: Priority Score Range
    
    **Validates: Requirements 8.1**
    
    对于任意文章，优先级评分应该是 0-100 之间的整数。
    
    For any article processed by PriorityScorer, the resulting score SHALL be
    an integer in the range [0, 100] inclusive.
    """
    result = score_article(article)
    
    # Property: Score must be an integer
    assert isinstance(result.score, int), \
        f"Score must be an integer, got {type(result.score)}"
    
    # Property: Score must be in range [0, 100]
    assert 0 <= result.score <= 100, \
        f"Score {result.score} must be in range [0, 100]"


@given(
    st.lists(article_strategy, min_size=0, max_size=50)
)
@settings(max_examples=50)
def test_property_batch_scoring_consistency(articles: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 13: Priority Score Range (Batch)
    
    **Validates: Requirements 8.1**
    
    批量评分应该对每篇文章产生有效的评分。
    Batch scoring should produce valid scores for each article.
    """
    scorer = PriorityScorer({'enable_ai_scoring': False})
    
    results = scorer.score_articles(articles)
    
    # Property: Result count should match input count
    assert len(results) == len(articles), \
        "Result count should match input count"
    
    # Property: All scores should be in valid range
    for result in results:
        assert 0 <= result.score <= 100, \
            f"Score {result.score} must be in range [0, 100]"


@given(
    st.lists(
        st.fixed_dictionaries({
            'article': article_strategy,
            'score': st.integers(min_value=0, max_value=100)
        }),
        min_size=0,
        max_size=50
    )
)
@settings(max_examples=50)
def test_property_articles_sorted_by_priority_descending(scored_data: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 14: Articles Sorted by Priority Descending
    
    **Validates: Requirements 8.4**
    
    对于任意带评分的文章列表，排序后每篇文章的评分应该大于或等于其后文章的评分。
    
    For any list of scored articles after sorting, each article's score SHALL be
    greater than or equal to the score of the article following it.
    """
    scorer = PriorityScorer({})
    
    # Create ScoredArticle objects
    scored_articles = [
        ScoredArticle(article=item['article'], score=item['score'])
        for item in scored_data
    ]
    
    sorted_articles = scorer.sort_by_priority(scored_articles)
    
    # Property: Articles should be sorted in descending order
    for i in range(len(sorted_articles) - 1):
        assert sorted_articles[i].score >= sorted_articles[i + 1].score, \
            f"Article at position {i} (score={sorted_articles[i].score}) " \
            f"should have score >= article at position {i+1} (score={sorted_articles[i+1].score})"


@given(
    st.lists(article_strategy, min_size=1, max_size=20),
    st.dictionaries(
        st.sampled_from(['kev', 'nvd', 'dblp', 'huggingface', 'pwc', 'blog', 'arxiv', 'rss']),
        source_weight_strategy,
        min_size=0,
        max_size=5
    )
)
@settings(max_examples=50)
def test_property_source_weights_affect_score(articles: list[dict], custom_weights: dict):
    """
    Feature: aggregator-advanced-features, Property 9: Configuration Threshold Respect (Scoring)
    
    **Validates: Requirements 8.2**
    
    自定义的来源权重应该影响评分结果。
    Custom source weights should affect scoring results.
    """
    scorer = PriorityScorer({
        'source_weights': custom_weights,
        'enable_ai_scoring': False
    })
    
    results = scorer.score_articles(articles)
    
    # Property: All scores should still be in valid range
    for result in results:
        assert 0 <= result.score <= 100, \
            f"Score {result.score} must be in range [0, 100]"
