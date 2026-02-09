"""
历史感知查询构建器单元测试

测试 HistoryAwareQueryBuilder 类的功能，包括：
- 历史截断逻辑
- 增强查询构建
- 边界条件处理

Requirements:
    - 3.1: 接受可选的对话历史作为输入
    - 3.2: 使用对话历史增强查询理解和检索
    - 3.4: 历史超过 max_history_turns 时只使用最近的轮次
    - 3.5: 历史为空或未提供时，不使用历史上下文处理查询
"""

import pytest
from datetime import datetime

from src.qa.history_aware_query_builder import HistoryAwareQueryBuilder
from src.qa.models import ConversationTurn


class TestHistoryAwareQueryBuilderInit:
    """测试 HistoryAwareQueryBuilder 初始化"""
    
    def test_init_with_default_max_turns(self):
        """测试默认最大轮数"""
        builder = HistoryAwareQueryBuilder()
        assert builder.default_max_turns == 5
    
    def test_init_with_custom_max_turns(self):
        """测试自定义最大轮数"""
        builder = HistoryAwareQueryBuilder(default_max_turns=10)
        assert builder.default_max_turns == 10


class TestBuildQueryNoHistory:
    """测试无历史时的查询构建 (Requirement 3.5)"""
    
    def test_build_query_with_none_history(self):
        """测试 history=None 时直接返回原查询"""
        builder = HistoryAwareQueryBuilder()
        query = "什么是RAG?"
        
        result = builder.build_query(query, None)
        
        assert result == query
    
    def test_build_query_with_empty_history(self):
        """测试 history=[] 时直接返回原查询"""
        builder = HistoryAwareQueryBuilder()
        query = "什么是RAG?"
        
        result = builder.build_query(query, [])
        
        assert result == query
    
    def test_build_query_with_empty_query(self):
        """测试空查询返回空字符串"""
        builder = HistoryAwareQueryBuilder()
        
        result = builder.build_query("", None)
        
        assert result == ""
    
    def test_build_query_with_whitespace_query(self):
        """测试空白查询返回空字符串"""
        builder = HistoryAwareQueryBuilder()
        
        result = builder.build_query("   ", None)
        
        assert result == ""
    
    def test_build_query_strips_whitespace(self):
        """测试查询前后空白被去除"""
        builder = HistoryAwareQueryBuilder()
        query = "  什么是RAG?  "
        
        result = builder.build_query(query, None)
        
        assert result == "什么是RAG?"


class TestBuildQueryWithHistory:
    """测试有历史时的查询构建 (Requirements 3.1, 3.2)"""
    
    def test_build_query_includes_history_context(self):
        """测试增强查询包含历史上下文"""
        builder = HistoryAwareQueryBuilder()
        history = [
            ConversationTurn(query="什么是向量数据库?", answer="向量数据库是一种专门存储向量的数据库")
        ]
        
        result = builder.build_query("它有什么优点?", history)
        
        # 增强查询应该包含历史信息
        assert "向量数据库" in result
        assert "它有什么优点?" in result
    
    def test_build_query_with_multiple_history_turns(self):
        """测试多轮历史的增强查询"""
        builder = HistoryAwareQueryBuilder()
        history = [
            ConversationTurn(query="什么是RAG?", answer="RAG是检索增强生成"),
            ConversationTurn(query="它有什么优点?", answer="RAG可以提高回答准确性"),
        ]
        
        result = builder.build_query("如何实现?", history)
        
        # 增强查询应该包含多轮历史信息
        assert "RAG" in result
        assert "如何实现?" in result
    
    def test_build_query_preserves_current_query(self):
        """测试当前查询被保留在增强查询中"""
        builder = HistoryAwareQueryBuilder()
        history = [
            ConversationTurn(query="什么是向量数据库?", answer="向量数据库是...")
        ]
        current_query = "它有什么优点?"
        
        result = builder.build_query(current_query, history)
        
        assert current_query in result


class TestHistoryTruncation:
    """测试历史截断逻辑 (Requirement 3.4, Property 5)"""
    
    def test_truncate_history_within_limit(self):
        """测试历史长度不超过限制时不截断"""
        builder = HistoryAwareQueryBuilder(default_max_turns=5)
        history = [
            ConversationTurn(query=f"问题{i}", answer=f"回答{i}")
            for i in range(3)
        ]
        
        truncated = builder.get_truncated_history(history)
        
        assert len(truncated) == 3
    
    def test_truncate_history_exceeds_limit(self):
        """测试历史长度超过限制时截断到最近的轮次"""
        builder = HistoryAwareQueryBuilder(default_max_turns=3)
        history = [
            ConversationTurn(query=f"问题{i}", answer=f"回答{i}")
            for i in range(5)
        ]
        
        truncated = builder.get_truncated_history(history)
        
        # 应该只保留最近的 3 轮
        assert len(truncated) == 3
        # 验证保留的是最近的轮次
        assert truncated[0].query == "问题2"
        assert truncated[1].query == "问题3"
        assert truncated[2].query == "问题4"
    
    def test_truncate_history_preserves_chronological_order(self):
        """测试截断后保持时间顺序（最早在前，最近在后）"""
        builder = HistoryAwareQueryBuilder(default_max_turns=3)
        history = [
            ConversationTurn(query=f"问题{i}", answer=f"回答{i}")
            for i in range(10)
        ]
        
        truncated = builder.get_truncated_history(history)
        
        # 验证时间顺序：问题7 < 问题8 < 问题9
        assert truncated[0].query == "问题7"
        assert truncated[1].query == "问题8"
        assert truncated[2].query == "问题9"
    
    def test_truncate_history_with_custom_max_turns(self):
        """测试使用自定义 max_turns 参数"""
        builder = HistoryAwareQueryBuilder(default_max_turns=5)
        history = [
            ConversationTurn(query=f"问题{i}", answer=f"回答{i}")
            for i in range(10)
        ]
        
        # 使用自定义 max_turns=2
        truncated = builder.get_truncated_history(history, max_turns=2)
        
        assert len(truncated) == 2
        assert truncated[0].query == "问题8"
        assert truncated[1].query == "问题9"
    
    def test_truncate_history_max_turns_zero(self):
        """测试 max_turns=0 时返回空列表"""
        builder = HistoryAwareQueryBuilder()
        history = [
            ConversationTurn(query=f"问题{i}", answer=f"回答{i}")
            for i in range(5)
        ]
        
        truncated = builder.get_truncated_history(history, max_turns=0)
        
        assert len(truncated) == 0
    
    def test_truncate_history_none_input(self):
        """测试 history=None 时返回空列表"""
        builder = HistoryAwareQueryBuilder()
        
        truncated = builder.get_truncated_history(None)
        
        assert truncated == []
    
    def test_truncate_history_empty_input(self):
        """测试 history=[] 时返回空列表"""
        builder = HistoryAwareQueryBuilder()
        
        truncated = builder.get_truncated_history([])
        
        assert truncated == []
    
    def test_truncate_history_exact_limit(self):
        """测试历史长度正好等于限制时不截断"""
        builder = HistoryAwareQueryBuilder(default_max_turns=5)
        history = [
            ConversationTurn(query=f"问题{i}", answer=f"回答{i}")
            for i in range(5)
        ]
        
        truncated = builder.get_truncated_history(history)
        
        assert len(truncated) == 5
        # 验证所有轮次都保留
        for i in range(5):
            assert truncated[i].query == f"问题{i}"


class TestBuildQueryWithTruncation:
    """测试 build_query 中的历史截断"""
    
    def test_build_query_truncates_long_history(self):
        """测试 build_query 自动截断过长的历史"""
        builder = HistoryAwareQueryBuilder(default_max_turns=2)
        history = [
            ConversationTurn(query="问题1", answer="回答1"),
            ConversationTurn(query="问题2", answer="回答2"),
            ConversationTurn(query="问题3", answer="回答3"),
            ConversationTurn(query="问题4", answer="回答4"),
        ]
        
        result = builder.build_query("当前问题", history)
        
        # 只有最近的 2 轮应该被包含
        assert "问题3" in result
        assert "问题4" in result
        # 较早的轮次不应该被包含
        assert "问题1" not in result
        assert "问题2" not in result
    
    def test_build_query_with_custom_max_turns(self):
        """测试 build_query 使用自定义 max_turns"""
        builder = HistoryAwareQueryBuilder(default_max_turns=5)
        history = [
            ConversationTurn(query=f"问题{i}", answer=f"回答{i}")
            for i in range(10)
        ]
        
        result = builder.build_query("当前问题", history, max_turns=1)
        
        # 只有最近的 1 轮应该被包含
        assert "问题9" in result
        # 其他轮次不应该被包含
        assert "问题8" not in result


class TestSimplifyText:
    """测试文本简化功能"""
    
    def test_simplify_short_text(self):
        """测试短文本不被截断"""
        builder = HistoryAwareQueryBuilder()
        
        result = builder._simplify_text("短文本", max_length=100)
        
        assert result == "短文本"
    
    def test_simplify_long_text(self):
        """测试长文本被截断"""
        builder = HistoryAwareQueryBuilder()
        long_text = "这是一个很长的文本" * 20
        
        result = builder._simplify_text(long_text, max_length=50)
        
        assert len(result) == 50
        assert result.endswith("...")
    
    def test_simplify_empty_text(self):
        """测试空文本返回空字符串"""
        builder = HistoryAwareQueryBuilder()
        
        result = builder._simplify_text("", max_length=100)
        
        assert result == ""
    
    def test_simplify_whitespace_text(self):
        """测试空白文本被去除"""
        builder = HistoryAwareQueryBuilder()
        
        result = builder._simplify_text("  ", max_length=100)
        
        assert result == ""


class TestEdgeCases:
    """测试边界情况"""
    
    def test_history_with_empty_query(self):
        """测试历史中包含空查询"""
        builder = HistoryAwareQueryBuilder()
        history = [
            ConversationTurn(query="", answer="回答1"),
            ConversationTurn(query="问题2", answer="回答2"),
        ]
        
        result = builder.build_query("当前问题", history)
        
        # 应该正常处理，不崩溃
        assert "当前问题" in result
    
    def test_history_with_empty_answer(self):
        """测试历史中包含空回答"""
        builder = HistoryAwareQueryBuilder()
        history = [
            ConversationTurn(query="问题1", answer=""),
            ConversationTurn(query="问题2", answer="回答2"),
        ]
        
        result = builder.build_query("当前问题", history)
        
        # 应该正常处理，不崩溃
        assert "当前问题" in result
    
    def test_history_with_very_long_content(self):
        """测试历史中包含很长的内容"""
        builder = HistoryAwareQueryBuilder()
        long_query = "问题" * 500
        long_answer = "回答" * 500
        history = [
            ConversationTurn(query=long_query, answer=long_answer),
        ]
        
        result = builder.build_query("当前问题", history)
        
        # 应该正常处理，内容被截断
        assert "当前问题" in result
        # 增强查询不应该过长
        assert len(result) < len(long_query) + len(long_answer)
    
    def test_max_turns_negative(self):
        """测试负数 max_turns 返回空列表"""
        builder = HistoryAwareQueryBuilder()
        history = [
            ConversationTurn(query="问题1", answer="回答1"),
        ]
        
        truncated = builder.get_truncated_history(history, max_turns=-1)
        
        assert truncated == []
