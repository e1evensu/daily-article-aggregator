"""
TieredPusher 单元测试和属性测试
Unit tests and property-based tests for TieredPusher

测试分级推送器的各项功能。
Tests for tiered pusher functionality.
"""

import pytest
from unittest.mock import MagicMock

from src.pushers.tiered_pusher import (
    TieredPusher,
    PushLevel,
    TieredArticle,
    categorize_by_position,
)


class TestTieredPusherInit:
    """测试 TieredPusher 初始化"""
    
    def test_default_config(self):
        """测试默认配置"""
        pusher = TieredPusher({})
        
        assert pusher.level1_threshold == 0.10
        assert pusher.level2_threshold == 0.40
        assert pusher.feishu_bot is None
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = {
            'level1_threshold': 0.15,
            'level2_threshold': 0.50
        }
        pusher = TieredPusher(config)
        
        assert pusher.level1_threshold == 0.15
        assert pusher.level2_threshold == 0.50


class TestCategorizeArticles:
    """测试文章分级"""
    
    def test_categorize_10_articles(self):
        """测试 10 篇文章分级"""
        pusher = TieredPusher({
            'level1_threshold': 0.10,
            'level2_threshold': 0.40
        })
        
        # 创建 10 篇文章
        class ScoredArticle:
            def __init__(self, article, score):
                self.article = article
                self.score = score
        
        articles = [
            ScoredArticle({'title': f'Article {i}'}, 100 - i * 10)
            for i in range(10)
        ]
        
        result = pusher.categorize_articles(articles)
        
        # 10 * 0.10 = 1 篇 Level 1
        # 10 * 0.40 - 1 = 3 篇 Level 2
        # 剩余 6 篇 Level 3
        assert len(result[PushLevel.LEVEL_1]) == 1
        assert len(result[PushLevel.LEVEL_2]) == 3
        assert len(result[PushLevel.LEVEL_3]) == 6
    
    def test_categorize_empty_list(self):
        """测试空列表"""
        pusher = TieredPusher({})
        
        result = pusher.categorize_articles([])
        
        assert len(result[PushLevel.LEVEL_1]) == 0
        assert len(result[PushLevel.LEVEL_2]) == 0
        assert len(result[PushLevel.LEVEL_3]) == 0
    
    def test_categorize_single_article(self):
        """测试单篇文章"""
        pusher = TieredPusher({})
        
        class ScoredArticle:
            def __init__(self, article, score):
                self.article = article
                self.score = score
        
        articles = [ScoredArticle({'title': 'Only One'}, 90)]
        
        result = pusher.categorize_articles(articles)
        
        # 单篇文章应该在 Level 3（因为 1 * 0.10 = 0）
        total = sum(len(v) for v in result.values())
        assert total == 1


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings, assume
import math


# Strategy for generating article data with score
scored_article_strategy = st.fixed_dictionaries({
    'title': st.text(min_size=1, max_size=100),
    'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
    'score': st.integers(min_value=0, max_value=100),
})


@given(
    st.lists(scored_article_strategy, min_size=0, max_size=100),
    st.floats(min_value=0.01, max_value=0.30),
    st.floats(min_value=0.31, max_value=0.70)
)
@settings(max_examples=100)
def test_property_tiered_categorization_correctness(
    articles: list[dict],
    level1_threshold: float,
    level2_threshold: float
):
    """
    Feature: aggregator-advanced-features, Property 15: Tiered Categorization Correctness
    
    **Validates: Requirements 9.1, 10.1, 11.1**
    
    对于任意已排序的 N 篇文章和配置的阈值：
    - 位置 0 到 floor(N*level1_threshold)-1 的文章应为 Level 1
    - 位置 floor(N*level1_threshold) 到 floor(N*level2_threshold)-1 的文章应为 Level 2
    - 位置 floor(N*level2_threshold) 到 N-1 的文章应为 Level 3
    """
    # 确保 level1 < level2
    assume(level1_threshold < level2_threshold)
    
    result = categorize_by_position(
        articles,
        level1_threshold=level1_threshold,
        level2_threshold=level2_threshold
    )
    
    n = len(articles)
    level1_end = int(n * level1_threshold)
    level2_end = int(n * level2_threshold)
    
    # Property: Level 1 count should match expected
    expected_level1 = level1_end
    assert len(result[PushLevel.LEVEL_1]) == expected_level1, \
        f"Expected {expected_level1} Level 1 articles, got {len(result[PushLevel.LEVEL_1])}"
    
    # Property: Level 2 count should match expected
    expected_level2 = level2_end - level1_end
    assert len(result[PushLevel.LEVEL_2]) == expected_level2, \
        f"Expected {expected_level2} Level 2 articles, got {len(result[PushLevel.LEVEL_2])}"
    
    # Property: Level 3 count should match expected
    expected_level3 = n - level2_end
    assert len(result[PushLevel.LEVEL_3]) == expected_level3, \
        f"Expected {expected_level3} Level 3 articles, got {len(result[PushLevel.LEVEL_3])}"
    
    # Property: Total count should equal input count
    total = sum(len(v) for v in result.values())
    assert total == n, f"Total {total} should equal input count {n}"


@given(
    st.lists(scored_article_strategy, min_size=1, max_size=50)
)
@settings(max_examples=50)
def test_property_all_articles_assigned_level(articles: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 15: Tiered Categorization Correctness (Coverage)
    
    **Validates: Requirements 9.1, 10.1, 11.1**
    
    所有输入文章都应该被分配到某个级别。
    All input articles should be assigned to some level.
    """
    result = categorize_by_position(articles)
    
    total = sum(len(v) for v in result.values())
    
    # Property: All articles should be categorized
    assert total == len(articles), \
        f"All {len(articles)} articles should be categorized, got {total}"



from src.pushers.tiered_pusher import format_article_by_level


class TestFormatMethods:
    """测试格式化方法"""
    
    def test_format_level1_full(self):
        """测试 Level 1 完整格式"""
        pusher = TieredPusher({})
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/test',
            'zh_summary': '这是一篇测试文章的摘要',
            'category': 'AI/机器学习',
            'keywords': ['AI', '测试', '机器学习']
        }
        tiered = TieredArticle(article=article, score=90, level=PushLevel.LEVEL_1)
        
        result = pusher._format_level1_article(tiered)
        
        assert 'Test Article' in result
        assert 'https://example.com/test' in result
        assert '这是一篇测试文章的摘要' in result
        assert 'AI/机器学习' in result
        assert 'AI' in result
    
    def test_format_level2_brief(self):
        """测试 Level 2 简要格式"""
        pusher = TieredPusher({})
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/test',
            'brief_summary': '简要摘要'
        }
        tiered = TieredArticle(article=article, score=60, level=PushLevel.LEVEL_2)
        
        result = pusher._format_level2_article(tiered)
        
        assert 'Test Article' in result
        assert 'https://example.com/test' in result
        assert '简要摘要' in result
    
    def test_format_level3_link_only(self):
        """测试 Level 3 仅链接格式"""
        pusher = TieredPusher({})
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/test',
            'zh_summary': '这个摘要不应该出现'
        }
        tiered = TieredArticle(article=article, score=30, level=PushLevel.LEVEL_3)
        
        result = pusher._format_level3_article(tiered)
        
        assert 'Test Article' in result
        assert 'https://example.com/test' in result
        assert '这个摘要不应该出现' not in result


# Property 16 tests
@given(
    st.fixed_dictionaries({
        'title': st.text(min_size=1, max_size=100),
        'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
        'zh_summary': st.text(min_size=10, max_size=200),
        'summary': st.text(min_size=10, max_size=200),
        'category': st.text(min_size=1, max_size=50),
        'keywords': st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5),
        'brief_summary': st.text(min_size=5, max_size=50),
    })
)
@settings(max_examples=50)
def test_property_level1_format_contains_required_fields(article: dict):
    """
    Feature: aggregator-advanced-features, Property 16: Level-Appropriate Formatting (Level 1)
    
    **Validates: Requirements 9.2**
    
    Level 1 格式应包含：详细摘要、链接、分类、关键词
    Level 1 format SHALL contain: detailed summary, url, category, keywords
    """
    result = format_article_by_level(article, PushLevel.LEVEL_1)
    
    # Property: Level 1 must contain title
    assert article['title'] in result, "Level 1 must contain title"
    
    # Property: Level 1 must contain url
    assert article['url'] in result, "Level 1 must contain url"
    
    # Property: Level 1 must contain summary (zh_summary or summary)
    has_summary = article['zh_summary'] in result or article['summary'] in result
    assert has_summary, "Level 1 must contain summary"
    
    # Property: Level 1 must contain category
    assert article['category'] in result, "Level 1 must contain category"
    
    # Property: Level 1 must contain at least one keyword
    has_keyword = any(kw in result for kw in article['keywords'])
    assert has_keyword, "Level 1 must contain keywords"


@given(
    st.fixed_dictionaries({
        'title': st.text(min_size=1, max_size=100),
        'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
        'brief_summary': st.text(min_size=5, max_size=50),
    })
)
@settings(max_examples=50)
def test_property_level2_format_contains_required_fields(article: dict):
    """
    Feature: aggregator-advanced-features, Property 16: Level-Appropriate Formatting (Level 2)
    
    **Validates: Requirements 10.2**
    
    Level 2 格式应包含：简要摘要、链接
    Level 2 format SHALL contain: brief summary, url
    """
    result = format_article_by_level(article, PushLevel.LEVEL_2)
    
    # Property: Level 2 must contain title
    assert article['title'] in result, "Level 2 must contain title"
    
    # Property: Level 2 must contain url
    assert article['url'] in result, "Level 2 must contain url"
    
    # Property: Level 2 must contain brief summary
    assert article['brief_summary'] in result, "Level 2 must contain brief summary"


@given(
    st.fixed_dictionaries({
        'title': st.text(min_size=5, max_size=100, alphabet=st.characters(whitelist_categories=('Lu',))),
        'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
        'zh_summary': st.text(min_size=20, max_size=200, alphabet=st.characters(whitelist_categories=('Ll',))),
        'category': st.text(min_size=10, max_size=50, alphabet=st.characters(whitelist_categories=('Nd',))),
    })
)
@settings(max_examples=50)
def test_property_level3_format_contains_only_title_url(article: dict):
    """
    Feature: aggregator-advanced-features, Property 16: Level-Appropriate Formatting (Level 3)
    
    **Validates: Requirements 11.2**
    
    Level 3 格式仅包含：标题、链接
    Level 3 format SHALL contain: title, url only
    """
    result = format_article_by_level(article, PushLevel.LEVEL_3)
    
    # Property: Level 3 must contain title
    assert article['title'] in result, "Level 3 must contain title"
    
    # Property: Level 3 must contain url
    assert article['url'] in result, "Level 3 must contain url"
    
    # Property: Level 3 format is minimal (just title and url)
    # The format is "- {title}: {url}" so it should be relatively short
    expected_format = f"- {article['title']}: {article['url']}"
    assert result == expected_format, f"Level 3 format should be minimal: expected '{expected_format}', got '{result}'"



from src.pushers.tiered_pusher import format_tiered_message


class TestTieredMessage:
    """测试分级消息格式化"""
    
    def test_format_with_all_levels(self):
        """测试包含所有级别的消息"""
        pusher = TieredPusher({})
        
        tiered_articles = {
            PushLevel.LEVEL_1: [
                TieredArticle({'title': 'L1 Article', 'url': 'https://l1.com'}, 90, PushLevel.LEVEL_1)
            ],
            PushLevel.LEVEL_2: [
                TieredArticle({'title': 'L2 Article', 'url': 'https://l2.com'}, 60, PushLevel.LEVEL_2)
            ],
            PushLevel.LEVEL_3: [
                TieredArticle({'title': 'L3 Article', 'url': 'https://l3.com'}, 30, PushLevel.LEVEL_3)
            ],
        }
        
        result = pusher._format_tiered_message(tiered_articles)
        
        assert '重点推荐' in result
        assert '值得关注' in result
        assert '其他文章' in result
        assert 'L1 Article' in result
        assert 'L2 Article' in result
        assert 'L3 Article' in result
    
    def test_statistics_header(self):
        """测试统计头部"""
        pusher = TieredPusher({})
        
        tiered_articles = {
            PushLevel.LEVEL_1: [TieredArticle({'title': 'A'}, 90, PushLevel.LEVEL_1)],
            PushLevel.LEVEL_2: [TieredArticle({'title': 'B'}, 60, PushLevel.LEVEL_2)] * 3,
            PushLevel.LEVEL_3: [TieredArticle({'title': 'C'}, 30, PushLevel.LEVEL_3)] * 6,
        }
        
        header = pusher._build_statistics_header(tiered_articles)
        
        assert '共 10 篇' in header
        assert '重点 1 篇' in header
        assert '推荐 3 篇' in header
        assert '其他 6 篇' in header


# Property 17, 18, 19 tests
@given(
    st.lists(
        st.fixed_dictionaries({
            'title': st.text(min_size=1, max_size=50),
            'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
        }),
        min_size=0,
        max_size=5
    ),
    st.lists(
        st.fixed_dictionaries({
            'title': st.text(min_size=1, max_size=50),
            'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
        }),
        min_size=0,
        max_size=5
    ),
    st.lists(
        st.fixed_dictionaries({
            'title': st.text(min_size=1, max_size=50),
            'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
        }),
        min_size=0,
        max_size=5
    ),
)
@settings(max_examples=50)
def test_property_empty_level_omission(
    level1_articles: list[dict],
    level2_articles: list[dict],
    level3_articles: list[dict]
):
    """
    Feature: aggregator-advanced-features, Property 17: Empty Level Omission
    
    **Validates: Requirements 12.4**
    
    如果某个级别没有文章，该级别的部分不应出现在输出中。
    If a level contains zero articles, that level's section SHALL NOT appear in the output.
    """
    tiered_articles = {
        PushLevel.LEVEL_1: [TieredArticle(a, 90, PushLevel.LEVEL_1) for a in level1_articles],
        PushLevel.LEVEL_2: [TieredArticle(a, 60, PushLevel.LEVEL_2) for a in level2_articles],
        PushLevel.LEVEL_3: [TieredArticle(a, 30, PushLevel.LEVEL_3) for a in level3_articles],
    }
    
    result = format_tiered_message(tiered_articles)
    
    # Property: Empty Level 1 should not have "重点推荐" section
    if not level1_articles:
        assert '重点推荐' not in result, "Empty Level 1 should not appear"
    else:
        assert '重点推荐' in result, "Non-empty Level 1 should appear"
    
    # Property: Empty Level 2 should not have "值得关注" section
    if not level2_articles:
        assert '值得关注' not in result, "Empty Level 2 should not appear"
    else:
        assert '值得关注' in result, "Non-empty Level 2 should appear"
    
    # Property: Empty Level 3 should not have "其他文章" section
    if not level3_articles:
        assert '其他文章' not in result, "Empty Level 3 should not appear"
    else:
        assert '其他文章' in result, "Non-empty Level 3 should appear"


@given(
    st.lists(
        st.fixed_dictionaries({
            'title': st.text(min_size=1, max_size=50),
            'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
        }),
        min_size=1,
        max_size=10
    )
)
@settings(max_examples=50)
def test_property_push_message_statistics_header(articles: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 18: Push Message Statistics Header
    
    **Validates: Requirements 12.3**
    
    分级推送消息应以统计摘要开头，显示各非空级别的文章数量。
    The message SHALL begin with a statistics summary showing the count of articles in each non-empty level.
    """
    # 分配文章到各级别
    n = len(articles)
    level1_end = max(1, n // 10)
    level2_end = max(level1_end + 1, n * 4 // 10)
    
    tiered_articles = {
        PushLevel.LEVEL_1: [TieredArticle(a, 90, PushLevel.LEVEL_1) for a in articles[:level1_end]],
        PushLevel.LEVEL_2: [TieredArticle(a, 60, PushLevel.LEVEL_2) for a in articles[level1_end:level2_end]],
        PushLevel.LEVEL_3: [TieredArticle(a, 30, PushLevel.LEVEL_3) for a in articles[level2_end:]],
    }
    
    result = format_tiered_message(tiered_articles)
    
    # Property: Message should start with statistics header
    assert result.startswith('📊'), "Message should start with statistics header"
    
    # Property: Header should contain total count
    total = len(articles)
    assert f'共 {total} 篇' in result, f"Header should contain total count: {total}"


@given(
    st.lists(
        st.fixed_dictionaries({
            'title': st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('Lu',))),
            'url': st.from_regex(r'https://[a-z]+\.[a-z]+/[a-z0-9]+', fullmatch=True),
        }),
        min_size=3,
        max_size=10
    )
)
@settings(max_examples=50)
def test_property_level_grouping_in_output(articles: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 19: Level Grouping in Output
    
    **Validates: Requirements 12.1, 12.2**
    
    分级推送输出中，文章应按级别分组，组之间有明确的分隔。
    Articles SHALL be grouped by level with clear separators between groups.
    """
    # 确保每个级别至少有一篇文章
    n = len(articles)
    
    tiered_articles = {
        PushLevel.LEVEL_1: [TieredArticle(articles[0], 90, PushLevel.LEVEL_1)],
        PushLevel.LEVEL_2: [TieredArticle(articles[1], 60, PushLevel.LEVEL_2)],
        PushLevel.LEVEL_3: [TieredArticle(a, 30, PushLevel.LEVEL_3) for a in articles[2:]],
    }
    
    result = format_tiered_message(tiered_articles)
    
    # Property: Level 1 section should appear before Level 2
    level1_pos = result.find('重点推荐')
    level2_pos = result.find('值得关注')
    level3_pos = result.find('其他文章')
    
    assert level1_pos < level2_pos, "Level 1 should appear before Level 2"
    assert level2_pos < level3_pos, "Level 2 should appear before Level 3"
    
    # Property: Each level should have a clear header/separator
    assert '【重点推荐】' in result, "Level 1 should have clear header"
    assert '【值得关注】' in result, "Level 2 should have clear header"
    assert '【其他文章】' in result, "Level 3 should have clear header"
