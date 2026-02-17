"""
ContentProcessor 单元测试
Unit tests for ContentProcessor

测试内容处理器的各项功能：
- truncate_content 函数
- ContentProcessor 初始化
- HTML 转 Markdown
"""

import pytest
from unittest.mock import patch, MagicMock
from src.processors.content_processor import ContentProcessor, truncate_content


class TestTruncateContent:
    """测试 truncate_content 函数"""
    
    def test_no_truncation_needed(self):
        """内容不超过限制时不截断"""
        result = truncate_content("Hello", 10, "...")
        assert result == "Hello"
    
    def test_exact_length(self):
        """内容恰好等于限制时不截断"""
        result = truncate_content("Hello", 5, "...")
        assert result == "Hello"
    
    def test_truncation_with_marker(self):
        """内容超过限制时截断并添加标记"""
        result = truncate_content("Hello World", 8, "...")
        assert result == "Hello..."
        assert len(result) == 8
    
    def test_empty_content(self):
        """空内容返回空字符串"""
        result = truncate_content("", 10, "...")
        assert result == ""
    
    def test_none_content(self):
        """None内容返回None"""
        result = truncate_content(None, 10, "...")
        assert result is None
    
    def test_max_length_equals_marker_length(self):
        """最大长度等于标记长度时只返回标记"""
        result = truncate_content("Hello World", 3, "...")
        assert result == "..."
    
    def test_max_length_less_than_marker_length(self):
        """最大长度小于标记长度时返回截断的标记"""
        result = truncate_content("Hello World", 2, "...")
        assert result == ".."
    
    def test_zero_max_length(self):
        """最大长度为0时返回空字符串"""
        result = truncate_content("Hello", 0, "...")
        # 当max_length <= 0时，返回marker[:max_length]，即空字符串
        assert result == ""
    
    def test_negative_max_length(self):
        """负数最大长度返回空字符串"""
        result = truncate_content("Hello", -5, "...")
        # 当max_length <= 0时，返回空字符串
        assert result == ""
    
    def test_custom_marker(self):
        """自定义截断标记"""
        # "Hello World" 长度为11，小于等于12，不需要截断
        result = truncate_content("Hello World", 12, "...[截断]")
        assert result == "Hello World"  # 不截断
        
        # 测试需要截断的情况
        result2 = truncate_content("Hello World Test", 12, "...[截断]")
        assert result2.endswith("...[截断]")
        assert len(result2) == 12
    
    def test_unicode_content(self):
        """Unicode内容截断"""
        # "你好世界" 长度为4，小于5，不需要截断
        result = truncate_content("你好世界", 5, "...")
        assert result == "你好世界"  # 不截断
        
        # 测试需要截断的情况
        result2 = truncate_content("你好世界测试", 5, "...")
        assert len(result2) == 5
        assert result2.endswith("...")


class TestContentProcessorInit:
    """测试 ContentProcessor 初始化"""
    
    def test_default_config(self):
        """默认配置初始化"""
        processor = ContentProcessor({})
        assert processor.max_content_length == 50000
        assert processor.truncation_marker == "...[内容已截断]"
        assert processor.timeout == 30
    
    def test_custom_config(self):
        """自定义配置初始化"""
        config = {
            'max_content_length': 1000,
            'truncation_marker': '...',
            'timeout': 60,
            'proxy': 'http://127.0.0.1:7890'
        }
        processor = ContentProcessor(config)
        assert processor.max_content_length == 1000
        assert processor.truncation_marker == '...'
        assert processor.timeout == 60
        assert processor.proxy == 'http://127.0.0.1:7890'
    
    def test_none_config(self):
        """None配置使用默认值"""
        processor = ContentProcessor(None)
        assert processor.max_content_length == 50000
    
    def test_playwright_config_from_env(self):
        """从环境变量读取Playwright配置"""
        with patch.dict('os.environ', {
            'PLAYWRIGHT_ALWAYS': 'true',
            'PLAYWRIGHT_HEADLESS': 'false',
            'PLAYWRIGHT_TIMEOUT': '60000'
        }):
            processor = ContentProcessor({})
            assert processor._playwright_always is True
            assert processor._playwright_headless is False
            assert processor._playwright_timeout == 60000
    
    def test_playwright_config_from_dict(self):
        """从配置字典读取Playwright配置"""
        config = {
            'playwright_always': True,
            'playwright_headless': False,
            'playwright_timeout': 45000
        }
        processor = ContentProcessor(config)
        assert processor._playwright_always is True
        assert processor._playwright_headless is False
        assert processor._playwright_timeout == 45000


class TestContentProcessorHtmlToMarkdown:
    """测试 HTML 转 Markdown 功能"""
    
    def test_simple_html(self):
        """简单HTML转换"""
        processor = ContentProcessor({})
        html = "<html><body><h1>Title</h1><p>Content</p></body></html>"
        result = processor.html_to_markdown(html)
        assert result is not None
        assert "Title" in result or "title" in result.lower()
    
    def test_empty_html(self):
        """空HTML返回None"""
        processor = ContentProcessor({})
        result = processor.html_to_markdown("")
        assert result is None
    
    def test_none_html(self):
        """None HTML返回None"""
        processor = ContentProcessor({})
        result = processor.html_to_markdown(None)
        assert result is None


class TestContentProcessorContextManager:
    """测试上下文管理器功能"""
    
    def test_context_manager(self):
        """测试with语句支持"""
        with ContentProcessor({}) as processor:
            assert processor is not None
            assert processor.max_content_length == 50000


class TestContentProcessorFetchHtml:
    """测试 fetch_html 功能"""
    
    def test_empty_url(self):
        """空URL返回None"""
        processor = ContentProcessor({})
        result = processor.fetch_html("")
        assert result is None
    
    def test_none_url(self):
        """None URL返回None"""
        processor = ContentProcessor({})
        result = processor.fetch_html(None)
        assert result is None
    
    @patch('requests.get')
    def test_successful_fetch(self, mock_get):
        """成功获取HTML"""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        processor = ContentProcessor({})
        result = processor.fetch_html("http://example.com")
        
        assert result == "<html><body>Test</body></html>"
        mock_get.assert_called_once()
    
    @patch('requests.get')
    def test_timeout_error(self, mock_get):
        """请求超时返回None"""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()
        
        processor = ContentProcessor({'playwright_always': False})
        # 禁用Playwright回退以测试requests失败
        processor._fetch_with_playwright = MagicMock(return_value=None)
        
        result = processor.fetch_html("http://example.com")
        assert result is None
    
    @patch('requests.get')
    def test_http_error_triggers_playwright_fallback(self, mock_get):
        """HTTP错误触发Playwright回退"""
        import requests
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.side_effect = requests.exceptions.HTTPError(response=mock_response)
        
        processor = ContentProcessor({})
        processor._fetch_with_playwright = MagicMock(return_value="<html>Playwright</html>")
        
        result = processor.fetch_html("http://example.com")
        
        assert result == "<html>Playwright</html>"
        processor._fetch_with_playwright.assert_called_once()


class TestContentProcessorProcessArticle:
    """测试 process_article 完整流程"""
    
    def test_process_article_success(self):
        """成功处理文章"""
        processor = ContentProcessor({'max_content_length': 1000})
        processor.fetch_html = MagicMock(return_value="<html><body><h1>Test</h1></body></html>")
        
        result = processor.process_article("http://example.com")
        
        assert result is not None
        processor.fetch_html.assert_called_once_with("http://example.com")
    
    def test_process_article_fetch_failure(self):
        """获取HTML失败返回None"""
        processor = ContentProcessor({})
        processor.fetch_html = MagicMock(return_value=None)
        
        result = processor.process_article("http://example.com")
        
        assert result is None
    
    def test_process_article_with_truncation(self):
        """处理文章时截断过长内容"""
        processor = ContentProcessor({
            'max_content_length': 50,
            'truncation_marker': '...'
        })
        
        # 创建一个会产生长Markdown的HTML
        long_html = "<html><body>" + "<p>Test content paragraph.</p>" * 10 + "</body></html>"
        processor.fetch_html = MagicMock(return_value=long_html)
        
        result = processor.process_article("http://example.com")
        
        if result:  # 如果转换成功
            assert len(result) <= 50
            if len(result) == 50:
                assert result.endswith('...')


# ============================================================================
# Property-Based Tests for Content Truncation
# 内容截断的属性测试
# ============================================================================

from hypothesis import given, strategies as st, settings


class TestTruncateContentProperties:
    """
    Property-based tests for truncate_content function.
    属性测试：验证内容截断的正确性属性
    
    Feature: daily-article-aggregator, Property 5: 内容截断正确性
    验证: 需求 3.3
    """
    
    @settings(max_examples=100)
    @given(
        content=st.text(min_size=1, max_size=1000),
        max_length=st.integers(min_value=1, max_value=500),
        marker=st.text(min_size=1, max_size=20)
    )
    def test_property_truncated_length_equals_max_length(self, content: str, max_length: int, marker: str):
        """
        Feature: daily-article-aggregator, Property 5: 内容截断正确性
        
        Property: For any content longer than max_length, the result length is exactly max_length.
        属性：对于任意超过最大长度限制的内容，截断后的长度应该恰好等于限制值。
        
        **Validates: Requirements 3.3**
        """
        result = truncate_content(content, max_length, marker)
        
        if len(content) > max_length:
            # When content exceeds max_length, result should be exactly max_length
            assert len(result) == max_length, (
                f"Expected length {max_length}, got {len(result)}. "
                f"Content length: {len(content)}, Marker: '{marker}'"
            )
    
    @settings(max_examples=100)
    @given(
        content=st.text(min_size=1, max_size=1000),
        max_length=st.integers(min_value=1, max_value=500),
        marker=st.text(min_size=1, max_size=20)
    )
    def test_property_truncated_content_ends_with_marker(self, content: str, max_length: int, marker: str):
        """
        Feature: daily-article-aggregator, Property 5: 内容截断正确性
        
        Property: For any content longer than max_length, the result ends with the marker.
        属性：对于任意超过最大长度限制的内容，截断后的内容应该以省略标记结尾。
        
        **Validates: Requirements 3.3**
        """
        result = truncate_content(content, max_length, marker)
        
        if len(content) > max_length:
            # When content exceeds max_length, result should end with marker (or truncated marker)
            if max_length >= len(marker):
                assert result.endswith(marker), (
                    f"Expected result to end with '{marker}', got '{result[-len(marker):]}'"
                )
            else:
                # When max_length < marker length, result should be truncated marker
                assert result == marker[:max_length], (
                    f"Expected truncated marker '{marker[:max_length]}', got '{result}'"
                )
    
    @settings(max_examples=100)
    @given(
        content=st.text(min_size=0, max_size=500),
        max_length=st.integers(min_value=1, max_value=1000),
        marker=st.text(min_size=1, max_size=20)
    )
    def test_property_short_content_unchanged(self, content: str, max_length: int, marker: str):
        """
        Feature: daily-article-aggregator, Property 5: 内容截断正确性
        
        Property: For any content shorter than or equal to max_length, the result equals the original content.
        属性：对于任意长度不超过最大限制的内容，返回结果应该等于原始内容。
        
        **Validates: Requirements 3.3**
        """
        result = truncate_content(content, max_length, marker)
        
        if len(content) <= max_length:
            # When content is within limit, it should remain unchanged
            assert result == content, (
                f"Expected unchanged content '{content}', got '{result}'"
            )
    
    @settings(max_examples=100)
    @given(
        content=st.text(min_size=0, max_size=1000),
        max_length=st.integers(min_value=1, max_value=500),
        marker=st.text(min_size=1, max_size=20)
    )
    def test_property_result_never_exceeds_max_length(self, content: str, max_length: int, marker: str):
        """
        Feature: daily-article-aggregator, Property 5: 内容截断正确性
        
        Property: The function never returns content longer than max_length.
        属性：函数返回的内容长度永远不会超过最大长度限制。
        
        **Validates: Requirements 3.3**
        """
        result = truncate_content(content, max_length, marker)
        
        # Result should never exceed max_length
        assert len(result) <= max_length, (
            f"Result length {len(result)} exceeds max_length {max_length}. "
            f"Content length: {len(content)}, Marker: '{marker}'"
        )
