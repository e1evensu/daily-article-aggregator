"""
AIAnalyzer 单元测试
Unit tests for AIAnalyzer

测试AI分析器的各项功能：
- 初始化配置
- 提示词模板应用 (需求 4.3)
- API错误处理 (需求 4.5)
- 摘要生成、分类生成、翻译功能
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from openai import APIError, APITimeoutError, APIConnectionError

from src.analyzers.ai_analyzer import (
    AIAnalyzer,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_SUMMARY_PROMPT,
    DEFAULT_CATEGORY_PROMPT,
    DEFAULT_TRANSLATE_PROMPT,
)


# ============================================================================
# Initialization Tests - 初始化测试
# ============================================================================

class TestAIAnalyzerInit:
    """测试 AIAnalyzer 初始化"""
    
    def test_default_configuration(self):
        """
        测试默认配置初始化
        Test default configuration initialization
        """
        config = {
            'api_base': 'https://api.openai.com/v1',
            'api_key': 'test-key'
        }
        analyzer = AIAnalyzer(config)
        
        assert analyzer.model == 'gpt-4o-mini'
        assert analyzer.max_tokens is None
        assert analyzer.temperature == 0.7
        assert analyzer.timeout == 60
        assert analyzer.translate_enabled is True
        assert analyzer.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert analyzer.summary_prompt == DEFAULT_SUMMARY_PROMPT
        assert analyzer.category_prompt == DEFAULT_CATEGORY_PROMPT
        assert analyzer.translate_prompt == DEFAULT_TRANSLATE_PROMPT
    
    def test_custom_configuration(self):
        """
        测试自定义配置初始化
        Test custom configuration initialization
        """
        config = {
            'api_base': 'https://api.siliconflow.cn/v1',
            'api_key': 'custom-key',
            'model': 'deepseek-ai/DeepSeek-V3',
            'max_tokens': 2000,
            'temperature': 0.5,
            'timeout': 120,
            'translate': False
        }
        analyzer = AIAnalyzer(config)
        
        assert analyzer.model == 'deepseek-ai/DeepSeek-V3'
        assert analyzer.max_tokens == 2000
        assert analyzer.temperature == 0.5
        assert analyzer.timeout == 120
        assert analyzer.translate_enabled is False
    
    def test_empty_max_tokens_handling(self):
        """
        测试空/None max_tokens 处理
        Test empty/None max_tokens handling
        
        max_tokens为空字符串、None或0时应该设置为None（不限制）
        """
        # Test empty string
        config1 = {'api_key': 'test', 'max_tokens': ''}
        analyzer1 = AIAnalyzer(config1)
        assert analyzer1.max_tokens is None
        
        # Test None
        config2 = {'api_key': 'test', 'max_tokens': None}
        analyzer2 = AIAnalyzer(config2)
        assert analyzer2.max_tokens is None
        
        # Test 0
        config3 = {'api_key': 'test', 'max_tokens': 0}
        analyzer3 = AIAnalyzer(config3)
        assert analyzer3.max_tokens is None
        
        # Test missing key
        config4 = {'api_key': 'test'}
        analyzer4 = AIAnalyzer(config4)
        assert analyzer4.max_tokens is None
    
    def test_custom_prompt_templates(self):
        """
        测试自定义提示词模板
        Test custom prompt templates
        
        **Validates: Requirement 4.3**
        """
        custom_system = "You are a custom assistant."
        custom_summary = "Summarize: {title}\n{content}"
        custom_category = "Categorize: {title}\n{summary}"
        custom_translate = "Translate: {text}"
        
        config = {
            'api_key': 'test',
            'system_prompt': custom_system,
            'summary_prompt': custom_summary,
            'category_prompt': custom_category,
            'translate_prompt': custom_translate
        }
        analyzer = AIAnalyzer(config)
        
        assert analyzer.system_prompt == custom_system
        assert analyzer.summary_prompt == custom_summary
        assert analyzer.category_prompt == custom_category
        assert analyzer.translate_prompt == custom_translate


# ============================================================================
# Prompt Template Tests - 提示词模板测试 (需求 4.3)
# ============================================================================

class TestPromptTemplates:
    """
    测试提示词模板应用
    Test prompt template application
    
    **Validates: Requirement 4.3**
    """
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_custom_system_prompt_used(self, mock_openai_class):
        """
        验证自定义 system_prompt 被使用
        Verify custom system_prompt is used
        
        **Validates: Requirement 4.3**
        """
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test summary"
        mock_client.chat.completions.create.return_value = mock_response
        
        custom_system = "Custom system prompt for testing"
        config = {
            'api_key': 'test',
            'system_prompt': custom_system
        }
        analyzer = AIAnalyzer(config)
        
        # Call method
        analyzer.generate_summary("Test Title", "Test Content")
        
        # Verify system prompt was used
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        
        assert messages[0]['role'] == 'system'
        assert messages[0]['content'] == custom_system
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_custom_summary_prompt_applied(self, mock_openai_class):
        """
        验证自定义 summary_prompt 模板被应用
        Verify custom summary_prompt template is applied
        
        **Validates: Requirement 4.3**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated summary"
        mock_client.chat.completions.create.return_value = mock_response
        
        custom_summary_prompt = "CUSTOM: Title={title}, Content={content}"
        config = {
            'api_key': 'test',
            'summary_prompt': custom_summary_prompt
        }
        analyzer = AIAnalyzer(config)
        
        analyzer.generate_summary("My Title", "My Content")
        
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        user_message = messages[1]['content']
        
        assert "CUSTOM:" in user_message
        assert "Title=My Title" in user_message
        assert "Content=My Content" in user_message
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_custom_category_prompt_applied(self, mock_openai_class):
        """
        验证自定义 category_prompt 模板被应用
        Verify custom category_prompt template is applied
        
        **Validates: Requirement 4.3**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "AI/机器学习"
        mock_client.chat.completions.create.return_value = mock_response
        
        custom_category_prompt = "CATEGORY: {title} | {summary}"
        config = {
            'api_key': 'test',
            'category_prompt': custom_category_prompt
        }
        analyzer = AIAnalyzer(config)
        
        analyzer.generate_category("Test Title", "Test Summary")
        
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        user_message = messages[1]['content']
        
        assert "CATEGORY:" in user_message
        assert "Test Title" in user_message
        assert "Test Summary" in user_message
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_custom_translate_prompt_applied(self, mock_openai_class):
        """
        验证自定义 translate_prompt 模板被应用
        Verify custom translate_prompt template is applied
        
        **Validates: Requirement 4.3**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "翻译结果"
        mock_client.chat.completions.create.return_value = mock_response
        
        custom_translate_prompt = "TRANSLATE THIS: {text}"
        config = {
            'api_key': 'test',
            'translate_prompt': custom_translate_prompt
        }
        analyzer = AIAnalyzer(config)
        
        analyzer.translate_text("Hello world")
        
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        user_message = messages[1]['content']
        
        assert "TRANSLATE THIS:" in user_message
        assert "Hello world" in user_message


# ============================================================================
# API Error Handling Tests - API错误处理测试 (需求 4.5)
# ============================================================================

class TestAPIErrorHandling:
    """
    测试API错误处理
    Test API error handling
    
    **Validates: Requirement 4.5**
    """
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_timeout_error_returns_none(self, mock_openai_class):
        """
        测试超时错误返回None
        Test timeout error returns None
        
        **Validates: Requirement 4.5**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("Title", "Content")
        
        assert result is None
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_connection_error_returns_none(self, mock_openai_class):
        """
        测试连接错误返回None
        Test connection error returns None
        
        **Validates: Requirement 4.5**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("Title", "Content")
        
        assert result is None
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_api_error_returns_none(self, mock_openai_class):
        """
        测试API错误返回None
        Test API error returns None
        
        **Validates: Requirement 4.5**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Create a proper APIError with required parameters
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.chat.completions.create.side_effect = APIError(
            message="Internal Server Error",
            request=MagicMock(),
            body=None
        )
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("Title", "Content")
        
        assert result is None
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_category_returns_other_on_failure(self, mock_openai_class):
        """
        测试 generate_category 失败时返回 "其他"
        Test generate_category returns "其他" on failure
        
        **Validates: Requirement 4.5**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_category("Title", "Summary")
        
        assert result == "其他"
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_translate_text_returns_none_on_failure(self, mock_openai_class):
        """
        测试 translate_text 失败时返回 None
        Test translate_text returns None on failure
        
        **Validates: Requirement 4.5**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.translate_text("Hello world")
        
        assert result is None
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_unexpected_exception_returns_none(self, mock_openai_class):
        """
        测试意外异常返回None
        Test unexpected exception returns None
        
        **Validates: Requirement 4.5**
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("Unexpected error")
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("Title", "Content")
        
        assert result is None


# ============================================================================
# Method Tests - 方法测试
# ============================================================================

class TestGenerateSummary:
    """测试 generate_summary 方法"""
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_summary_with_valid_input(self, mock_openai_class):
        """
        测试有效输入生成摘要
        Test generate_summary with valid input
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is a test summary."
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("Test Title", "Test content here")
        
        assert result == "This is a test summary."
        mock_client.chat.completions.create.assert_called_once()
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_summary_with_empty_title(self, mock_openai_class):
        """
        测试空标题返回None
        Test generate_summary with empty title returns None
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("", "Content")
        
        assert result is None
        mock_client.chat.completions.create.assert_not_called()
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_summary_with_empty_content(self, mock_openai_class):
        """
        测试空内容返回None
        Test generate_summary with empty content returns None
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("Title", "")
        
        assert result is None
        mock_client.chat.completions.create.assert_not_called()
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_summary_strips_whitespace(self, mock_openai_class):
        """
        测试摘要结果去除首尾空白
        Test generate_summary strips whitespace from result
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "  Summary with spaces  \n"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("Title", "Content")
        
        assert result == "Summary with spaces"
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_summary_empty_response(self, mock_openai_class):
        """
        测试API返回空响应
        Test generate_summary with empty API response
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = []
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_summary("Title", "Content")
        
        assert result is None


class TestGenerateCategory:
    """测试 generate_category 方法"""
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_category_with_valid_input(self, mock_openai_class):
        """
        测试有效输入生成分类
        Test generate_category with valid input
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "AI/机器学习"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_category("Deep Learning Paper", "This paper discusses...")
        
        assert result == "AI/机器学习"
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_category_with_empty_title(self, mock_openai_class):
        """
        测试空标题返回 "其他"
        Test generate_category with empty title returns "其他"
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_category("", "Summary")
        
        assert result == "其他"
        mock_client.chat.completions.create.assert_not_called()
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_category_with_empty_summary(self, mock_openai_class):
        """
        测试空摘要仍能生成分类
        Test generate_category with empty summary still works
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "编程语言"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_category("Python Tutorial", "")
        
        assert result == "编程语言"
        mock_client.chat.completions.create.assert_called_once()
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_generate_category_with_none_summary(self, mock_openai_class):
        """
        测试None摘要仍能生成分类
        Test generate_category with None summary still works
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "安全/隐私"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.generate_category("Security Best Practices", None)
        
        assert result == "安全/隐私"


class TestTranslateText:
    """测试 translate_text 方法"""
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_translate_text_with_valid_input(self, mock_openai_class):
        """
        测试有效输入翻译文本
        Test translate_text with valid input
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "这是一个测试翻译。"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.translate_text("This is a test translation.")
        
        assert result == "这是一个测试翻译。"
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_translate_text_with_empty_input(self, mock_openai_class):
        """
        测试空输入返回None
        Test translate_text with empty input returns None
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.translate_text("")
        
        assert result is None
        mock_client.chat.completions.create.assert_not_called()
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_translate_text_uses_translation_system_prompt(self, mock_openai_class):
        """
        测试翻译使用专门的系统提示词
        Test translate_text uses translation-specific system prompt
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "翻译结果"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        analyzer.translate_text("Hello")
        
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        system_message = messages[0]['content']
        
        # Should use translation-specific system prompt, not the default one
        assert "翻译" in system_message


class TestAnalyzeArticle:
    """测试 analyze_article 完整流程"""
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_analyze_article_complete_workflow(self, mock_openai_class):
        """
        测试完整分析流程
        Test analyze_article complete workflow
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Setup responses for summary, category, and translation
        responses = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="English summary"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content="AI/机器学习"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content="中文摘要"))]),
        ]
        mock_client.chat.completions.create.side_effect = responses
        
        analyzer = AIAnalyzer({'api_key': 'test', 'translate': True})
        result = analyzer.analyze_article("Test Title", "Test content")
        
        assert result['summary'] == "English summary"
        assert result['category'] == "AI/机器学习"
        assert result['zh_summary'] == "中文摘要"
        assert mock_client.chat.completions.create.call_count == 3
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_analyze_article_without_translation(self, mock_openai_class):
        """
        测试禁用翻译的分析流程
        Test analyze_article without translation
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        responses = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="Summary"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content="编程语言"))]),
        ]
        mock_client.chat.completions.create.side_effect = responses
        
        analyzer = AIAnalyzer({'api_key': 'test', 'translate': False})
        result = analyzer.analyze_article("Test Title", "Test content")
        
        assert result['summary'] == "Summary"
        assert result['category'] == "编程语言"
        assert result['zh_summary'] is None
        assert mock_client.chat.completions.create.call_count == 2
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_analyze_article_summary_failure(self, mock_openai_class):
        """
        测试摘要生成失败时的处理
        Test analyze_article when summary generation fails
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # First call (summary) fails, second call (category) succeeds
        responses = [
            MagicMock(choices=[]),  # Empty response for summary
            MagicMock(choices=[MagicMock(message=MagicMock(content="其他"))]),
        ]
        mock_client.chat.completions.create.side_effect = responses
        
        analyzer = AIAnalyzer({'api_key': 'test', 'translate': True})
        result = analyzer.analyze_article("Test Title", "Test content")
        
        assert result['summary'] is None
        assert result['category'] == "其他"
        assert result['zh_summary'] is None  # No translation when summary is None
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_analyze_article_returns_default_on_all_failures(self, mock_openai_class):
        """
        测试所有API调用失败时返回默认值
        Test analyze_article returns defaults when all API calls fail
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
        
        analyzer = AIAnalyzer({'api_key': 'test'})
        result = analyzer.analyze_article("Test Title", "Test content")
        
        assert result['summary'] is None
        assert result['category'] == "其他"
        assert result['zh_summary'] is None


# ============================================================================
# API Call Configuration Tests - API调用配置测试
# ============================================================================

class TestAPICallConfiguration:
    """测试API调用配置"""
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_max_tokens_included_when_set(self, mock_openai_class):
        """
        测试设置max_tokens时包含在API调用中
        Test max_tokens is included in API call when set
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test', 'max_tokens': 1000})
        analyzer.generate_summary("Title", "Content")
        
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs['max_tokens'] == 1000
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_max_tokens_not_included_when_none(self, mock_openai_class):
        """
        测试max_tokens为None时不包含在API调用中
        Test max_tokens is not included in API call when None
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({'api_key': 'test'})  # No max_tokens
        analyzer.generate_summary("Title", "Content")
        
        call_args = mock_client.chat.completions.create.call_args
        assert 'max_tokens' not in call_args.kwargs
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_temperature_and_timeout_used(self, mock_openai_class):
        """
        测试temperature和timeout参数被使用
        Test temperature and timeout parameters are used
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({
            'api_key': 'test',
            'temperature': 0.3,
            'timeout': 90
        })
        analyzer.generate_summary("Title", "Content")
        
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs['temperature'] == 0.3
        assert call_args.kwargs['timeout'] == 90
    
    @patch('src.analyzers.ai_analyzer.OpenAI')
    def test_model_name_used(self, mock_openai_class):
        """
        测试模型名称被使用
        Test model name is used
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_client.chat.completions.create.return_value = mock_response
        
        analyzer = AIAnalyzer({
            'api_key': 'test',
            'model': 'custom-model-v1'
        })
        analyzer.generate_summary("Title", "Content")
        
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs['model'] == 'custom-model-v1'
