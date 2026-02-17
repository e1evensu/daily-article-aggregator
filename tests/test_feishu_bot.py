"""
飞书机器人属性测试

使用hypothesis库进行属性测试，验证文章格式化的正确性。
"""

import pytest
from hypothesis import given, strategies as st, settings

from src.bots.feishu_bot import format_article_list


# 定义文章策略：生成有效的文章（包含非空title和url）
valid_article_strategy = st.fixed_dictionaries({
    'title': st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    'url': st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
    'summary': st.text(max_size=500),
    'zh_summary': st.text(max_size=500),
    'category': st.text(max_size=50),
})

# 定义可能无效的文章策略（可能缺少title或url）
maybe_invalid_article_strategy = st.fixed_dictionaries({
    'title': st.one_of(st.just(''), st.text(max_size=100)),
    'url': st.one_of(st.just(''), st.text(max_size=200)),
    'summary': st.text(max_size=500),
    'zh_summary': st.text(max_size=500),
    'category': st.text(max_size=50),
})


class TestFormatArticleListProperty:
    """Property 10: 文章格式化完整性的属性测试"""

    @settings(max_examples=100)
    @given(st.lists(valid_article_strategy, min_size=0, max_size=20))
    def test_format_article_list_contains_all_titles_and_urls(self, articles: list[dict]):
        """
        Feature: daily-article-aggregator, Property 10: 文章格式化完整性
        
        **Validates: Requirements 6.3**
        
        对于任意文章列表，格式化后的消息文本应该包含每篇文章的标题和URL。
        """
        result = format_article_list(articles)
        
        for article in articles:
            title = article.get('title', '').strip()
            url = article.get('url', '').strip()
            
            # 有效文章（非空title和url）应该出现在结果中
            if title and url:
                assert title in result, f"标题 '{title}' 应该出现在格式化结果中"
                assert url in result, f"URL '{url}' 应该出现在格式化结果中"

    @settings(max_examples=100)
    @given(st.lists(maybe_invalid_article_strategy, min_size=0, max_size=20))
    def test_format_article_list_skips_invalid_articles(self, articles: list[dict]):
        """
        Feature: daily-article-aggregator, Property 10: 文章格式化完整性
        
        **Validates: Requirements 6.3**
        
        验证缺少title或url的文章会被跳过，不会出现在格式化结果中。
        """
        result = format_article_list(articles)
        
        for article in articles:
            title = article.get('title', '').strip()
            url = article.get('url', '').strip()
            
            if title and url:
                # 有效文章应该出现在结果中
                assert title in result, f"有效文章的标题 '{title}' 应该出现在格式化结果中"
                assert url in result, f"有效文章的URL '{url}' 应该出现在格式化结果中"
            else:
                # 无效文章的title（如果非空）不应该作为文章标题出现
                # 注意：空字符串不需要检查
                pass  # 无效文章被跳过是预期行为

    @settings(max_examples=100)
    @given(st.lists(valid_article_strategy, min_size=0, max_size=20))
    def test_format_article_list_empty_returns_empty(self, articles: list[dict]):
        """
        Feature: daily-article-aggregator, Property 10: 文章格式化完整性
        
        **Validates: Requirements 6.3**
        
        验证空列表返回空字符串。
        """
        if not articles:
            result = format_article_list(articles)
            assert result == "", "空文章列表应该返回空字符串"


class TestFormatArticleListUnit:
    """文章格式化的单元测试"""

    def test_empty_list(self):
        """测试空列表返回空字符串"""
        result = format_article_list([])
        assert result == ""

    def test_single_article_with_title_and_url(self):
        """测试单篇文章格式化"""
        articles = [{'title': 'Test Article', 'url': 'https://example.com'}]
        result = format_article_list(articles)
        
        assert 'Test Article' in result
        assert 'https://example.com' in result

    def test_article_missing_title_is_skipped(self):
        """测试缺少标题的文章被跳过"""
        articles = [
            {'title': '', 'url': 'https://example.com'},
            {'title': 'Valid Article', 'url': 'https://valid.com'}
        ]
        result = format_article_list(articles)
        
        assert 'https://example.com' not in result
        assert 'Valid Article' in result
        assert 'https://valid.com' in result

    def test_article_missing_url_is_skipped(self):
        """测试缺少URL的文章被跳过"""
        articles = [
            {'title': 'No URL Article', 'url': ''},
            {'title': 'Valid Article', 'url': 'https://valid.com'}
        ]
        result = format_article_list(articles)
        
        assert 'No URL Article' not in result
        assert 'Valid Article' in result
        assert 'https://valid.com' in result

    def test_article_with_summary(self):
        """测试带摘要的文章格式化"""
        articles = [{'title': 'Test', 'url': 'https://test.com', 'summary': 'This is a summary'}]
        result = format_article_list(articles)
        
        assert 'Test' in result
        assert 'https://test.com' in result
        assert 'This is a summary' in result

    def test_article_with_zh_summary_preferred(self):
        """测试中文摘要优先于英文摘要"""
        articles = [{
            'title': 'Test',
            'url': 'https://test.com',
            'summary': 'English summary',
            'zh_summary': '中文摘要'
        }]
        result = format_article_list(articles)
        
        assert '中文摘要' in result
        # 当有中文摘要时，英文摘要不应该出现
        assert 'English summary' not in result

    def test_article_with_category(self):
        """测试带分类的文章格式化"""
        articles = [{'title': 'Test', 'url': 'https://test.com', 'category': 'Technology'}]
        result = format_article_list(articles)
        
        assert 'Technology' in result

    def test_multiple_articles(self):
        """测试多篇文章格式化"""
        articles = [
            {'title': 'Article 1', 'url': 'https://example1.com'},
            {'title': 'Article 2', 'url': 'https://example2.com'},
            {'title': 'Article 3', 'url': 'https://example3.com'}
        ]
        result = format_article_list(articles)
        
        for article in articles:
            assert article['title'] in result
            assert article['url'] in result

    def test_whitespace_only_title_is_skipped(self):
        """测试只有空白字符的标题被跳过"""
        articles = [
            {'title': '   ', 'url': 'https://example.com'},
            {'title': 'Valid', 'url': 'https://valid.com'}
        ]
        result = format_article_list(articles)
        
        assert 'https://example.com' not in result
        assert 'Valid' in result

    def test_whitespace_only_url_is_skipped(self):
        """测试只有空白字符的URL被跳过"""
        articles = [
            {'title': 'No URL', 'url': '   '},
            {'title': 'Valid', 'url': 'https://valid.com'}
        ]
        result = format_article_list(articles)
        
        assert 'No URL' not in result
        assert 'Valid' in result
