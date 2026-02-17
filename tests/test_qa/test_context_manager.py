"""
ContextManager 单元测试

测试对话上下文管理器的基本功能。

Requirements:
    - 2.4: 支持多轮对话（记住上下文）
        - 系统应维护每个用户的对话历史
        - 支持配置最大历史轮数（默认5轮）
        - 支持配置上下文过期时间（默认30分钟）
"""

import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

from src.qa.context_manager import ContextManager


class TestContextManagerInit:
    """测试 ContextManager 初始化"""
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        manager = ContextManager()
        
        assert manager.max_history == 5
        assert manager.ttl_minutes == 30
    
    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        manager = ContextManager(max_history=10, ttl_minutes=60)
        
        assert manager.max_history == 10
        assert manager.ttl_minutes == 60
    
    def test_init_empty_contexts(self):
        """测试初始化时上下文为空"""
        manager = ContextManager()
        
        assert manager.get_user_ids() == []
        stats = manager.get_stats()
        assert stats["total_users"] == 0
        assert stats["total_turns"] == 0


class TestAddTurn:
    """测试 add_turn 方法"""
    
    def test_add_single_turn(self):
        """测试添加单轮对话"""
        manager = ContextManager()
        
        manager.add_turn("user1", "什么是RAG?", "RAG是检索增强生成...")
        
        context = manager.get_context("user1")
        assert len(context) == 1
        assert context[0]["query"] == "什么是RAG?"
        assert context[0]["answer"] == "RAG是检索增强生成..."
    
    def test_add_turn_with_sources(self):
        """测试添加带来源的对话"""
        manager = ContextManager()
        sources = ["https://example.com/article1", "https://example.com/article2"]
        
        manager.add_turn("user1", "问题", "回答", sources=sources)
        
        context = manager.get_context("user1")
        assert context[0]["sources"] == sources
    
    def test_add_multiple_turns(self):
        """测试添加多轮对话"""
        manager = ContextManager(max_history=5)
        
        for i in range(3):
            manager.add_turn("user1", f"问题{i}", f"回答{i}")
        
        context = manager.get_context("user1")
        assert len(context) == 3
        # 验证顺序（按时间顺序）
        assert context[0]["query"] == "问题0"
        assert context[1]["query"] == "问题1"
        assert context[2]["query"] == "问题2"
    
    def test_add_turn_respects_max_history(self):
        """测试添加对话时遵守最大历史限制"""
        manager = ContextManager(max_history=3)
        
        for i in range(5):
            manager.add_turn("user1", f"问题{i}", f"回答{i}")
        
        context = manager.get_context("user1")
        assert len(context) == 3
        # 应该只保留最近3轮
        assert context[0]["query"] == "问题2"
        assert context[1]["query"] == "问题3"
        assert context[2]["query"] == "问题4"
    
    def test_add_turn_for_multiple_users(self):
        """测试为多个用户添加对话"""
        manager = ContextManager()
        
        manager.add_turn("user1", "问题A", "回答A")
        manager.add_turn("user2", "问题B", "回答B")
        manager.add_turn("user1", "问题C", "回答C")
        
        context1 = manager.get_context("user1")
        context2 = manager.get_context("user2")
        
        assert len(context1) == 2
        assert len(context2) == 1
        assert context1[0]["query"] == "问题A"
        assert context1[1]["query"] == "问题C"
        assert context2[0]["query"] == "问题B"
    
    def test_add_turn_updates_last_active(self):
        """测试添加对话时更新最后活跃时间"""
        manager = ContextManager()
        
        manager.add_turn("user1", "问题1", "回答1")
        time.sleep(0.1)
        manager.add_turn("user1", "问题2", "回答2")
        
        # 验证上下文存在且未过期
        context = manager.get_context("user1")
        assert len(context) == 2


class TestGetContext:
    """测试 get_context 方法"""
    
    def test_get_context_nonexistent_user(self):
        """测试获取不存在用户的上下文"""
        manager = ContextManager()
        
        context = manager.get_context("nonexistent_user")
        
        assert context == []
    
    def test_get_context_returns_dict_list(self):
        """测试获取上下文返回字典列表"""
        manager = ContextManager()
        manager.add_turn("user1", "问题", "回答")
        
        context = manager.get_context("user1")
        
        assert isinstance(context, list)
        assert isinstance(context[0], dict)
        assert "query" in context[0]
        assert "answer" in context[0]
        assert "timestamp" in context[0]
        assert "sources" in context[0]
    
    def test_get_context_expired(self):
        """测试获取过期的上下文"""
        manager = ContextManager(ttl_minutes=0)  # 立即过期
        manager.add_turn("user1", "问题", "回答")
        
        # 等待一小段时间确保过期
        time.sleep(0.1)
        
        context = manager.get_context("user1")
        
        assert context == []
    
    def test_get_context_not_expired(self):
        """测试获取未过期的上下文"""
        manager = ContextManager(ttl_minutes=30)
        manager.add_turn("user1", "问题", "回答")
        
        context = manager.get_context("user1")
        
        assert len(context) == 1
    
    def test_get_context_chronological_order(self):
        """测试获取上下文按时间顺序排列"""
        manager = ContextManager()
        
        manager.add_turn("user1", "问题1", "回答1")
        manager.add_turn("user1", "问题2", "回答2")
        manager.add_turn("user1", "问题3", "回答3")
        
        context = manager.get_context("user1")
        
        # 验证按时间顺序（最早的在前）
        assert context[0]["query"] == "问题1"
        assert context[1]["query"] == "问题2"
        assert context[2]["query"] == "问题3"


class TestClearContext:
    """测试 clear_context 方法"""
    
    def test_clear_existing_context(self):
        """测试清除存在的上下文"""
        manager = ContextManager()
        manager.add_turn("user1", "问题", "回答")
        
        manager.clear_context("user1")
        
        context = manager.get_context("user1")
        assert context == []
    
    def test_clear_nonexistent_context(self):
        """测试清除不存在的上下文（不应报错）"""
        manager = ContextManager()
        
        # 不应该抛出异常
        manager.clear_context("nonexistent_user")
    
    def test_clear_one_user_preserves_others(self):
        """测试清除一个用户的上下文不影响其他用户"""
        manager = ContextManager()
        manager.add_turn("user1", "问题1", "回答1")
        manager.add_turn("user2", "问题2", "回答2")
        
        manager.clear_context("user1")
        
        assert manager.get_context("user1") == []
        assert len(manager.get_context("user2")) == 1


class TestCleanupExpired:
    """测试 cleanup_expired 方法"""
    
    def test_cleanup_expired_contexts(self):
        """测试清理过期的上下文"""
        manager = ContextManager(ttl_minutes=0)  # 立即过期
        manager.add_turn("user1", "问题1", "回答1")
        manager.add_turn("user2", "问题2", "回答2")
        
        time.sleep(0.1)
        
        cleaned = manager.cleanup_expired()
        
        assert cleaned == 2
        assert manager.get_user_ids() == []
    
    def test_cleanup_preserves_active_contexts(self):
        """测试清理时保留活跃的上下文"""
        manager = ContextManager(ttl_minutes=30)
        manager.add_turn("user1", "问题", "回答")
        
        cleaned = manager.cleanup_expired()
        
        assert cleaned == 0
        assert len(manager.get_context("user1")) == 1
    
    def test_cleanup_mixed_contexts(self):
        """测试清理混合状态的上下文"""
        # 创建一个短TTL的管理器
        manager = ContextManager(ttl_minutes=30)
        
        # 添加一个用户的上下文
        manager.add_turn("user1", "问题1", "回答1")
        
        # 手动修改另一个用户的上下文为过期状态
        manager.add_turn("user2", "问题2", "回答2")
        # 通过直接修改内部状态来模拟过期
        with manager._lock:
            manager._contexts["user2"].last_active = datetime.now() - timedelta(minutes=60)
        
        cleaned = manager.cleanup_expired()
        
        assert cleaned == 1
        assert len(manager.get_context("user1")) == 1
        assert manager.get_context("user2") == []


class TestGetStats:
    """测试 get_stats 方法"""
    
    def test_stats_empty(self):
        """测试空管理器的统计信息"""
        manager = ContextManager(max_history=5, ttl_minutes=30)
        
        stats = manager.get_stats()
        
        assert stats["total_users"] == 0
        assert stats["total_turns"] == 0
        assert stats["max_history"] == 5
        assert stats["ttl_minutes"] == 30
    
    def test_stats_with_data(self):
        """测试有数据时的统计信息"""
        manager = ContextManager(max_history=5, ttl_minutes=30)
        manager.add_turn("user1", "问题1", "回答1")
        manager.add_turn("user1", "问题2", "回答2")
        manager.add_turn("user2", "问题3", "回答3")
        
        stats = manager.get_stats()
        
        assert stats["total_users"] == 2
        assert stats["total_turns"] == 3
        assert stats["max_history"] == 5
        assert stats["ttl_minutes"] == 30


class TestGetUserIds:
    """测试 get_user_ids 方法"""
    
    def test_get_user_ids_empty(self):
        """测试空管理器的用户ID列表"""
        manager = ContextManager()
        
        user_ids = manager.get_user_ids()
        
        assert user_ids == []
    
    def test_get_user_ids_with_users(self):
        """测试有用户时的用户ID列表"""
        manager = ContextManager()
        manager.add_turn("user1", "问题1", "回答1")
        manager.add_turn("user2", "问题2", "回答2")
        manager.add_turn("user3", "问题3", "回答3")
        
        user_ids = manager.get_user_ids()
        
        assert set(user_ids) == {"user1", "user2", "user3"}


class TestThreadSafety:
    """测试线程安全性"""
    
    def test_concurrent_add_turns(self):
        """测试并发添加对话"""
        manager = ContextManager(max_history=100)
        num_threads = 10
        turns_per_thread = 20
        
        def add_turns(user_id: str):
            for i in range(turns_per_thread):
                manager.add_turn(user_id, f"问题{i}", f"回答{i}")
        
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=add_turns, args=(f"user{i}",))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # 验证所有用户都有正确数量的对话
        stats = manager.get_stats()
        assert stats["total_users"] == num_threads
        assert stats["total_turns"] == num_threads * turns_per_thread
    
    def test_concurrent_read_write(self):
        """测试并发读写"""
        manager = ContextManager(max_history=100)
        num_operations = 50
        
        def writer():
            for i in range(num_operations):
                manager.add_turn("shared_user", f"问题{i}", f"回答{i}")
        
        def reader():
            for _ in range(num_operations):
                manager.get_context("shared_user")
        
        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)
        
        writer_thread.start()
        reader_thread.start()
        
        writer_thread.join()
        reader_thread.join()
        
        # 验证没有异常发生，数据完整
        context = manager.get_context("shared_user")
        assert len(context) <= num_operations
    
    def test_concurrent_clear_and_add(self):
        """测试并发清除和添加"""
        manager = ContextManager()
        num_operations = 30
        
        def adder():
            for i in range(num_operations):
                manager.add_turn("user1", f"问题{i}", f"回答{i}")
        
        def clearer():
            for _ in range(num_operations):
                manager.clear_context("user1")
        
        adder_thread = threading.Thread(target=adder)
        clearer_thread = threading.Thread(target=clearer)
        
        adder_thread.start()
        clearer_thread.start()
        
        adder_thread.join()
        clearer_thread.join()
        
        # 验证没有异常发生
        # 最终状态可能是空或有一些对话，取决于执行顺序
        context = manager.get_context("user1")
        assert isinstance(context, list)


class TestEdgeCases:
    """测试边界情况"""
    
    def test_max_history_one(self):
        """测试最大历史为1"""
        manager = ContextManager(max_history=1)
        
        manager.add_turn("user1", "问题1", "回答1")
        manager.add_turn("user1", "问题2", "回答2")
        
        context = manager.get_context("user1")
        assert len(context) == 1
        assert context[0]["query"] == "问题2"
    
    def test_empty_query_and_answer(self):
        """测试空问题和回答"""
        manager = ContextManager()
        
        manager.add_turn("user1", "", "")
        
        context = manager.get_context("user1")
        assert len(context) == 1
        assert context[0]["query"] == ""
        assert context[0]["answer"] == ""
    
    def test_unicode_content(self):
        """测试Unicode内容"""
        manager = ContextManager()
        
        manager.add_turn("user1", "什么是人工智能？🤖", "人工智能是...🧠")
        
        context = manager.get_context("user1")
        assert context[0]["query"] == "什么是人工智能？🤖"
        assert context[0]["answer"] == "人工智能是...🧠"
    
    def test_very_long_content(self):
        """测试非常长的内容"""
        manager = ContextManager()
        long_query = "问题" * 10000
        long_answer = "回答" * 10000
        
        manager.add_turn("user1", long_query, long_answer)
        
        context = manager.get_context("user1")
        assert context[0]["query"] == long_query
        assert context[0]["answer"] == long_answer
    
    def test_special_user_ids(self):
        """测试特殊用户ID"""
        manager = ContextManager()
        special_ids = ["user@domain.com", "user-123", "user_456", "用户1", "🎉"]
        
        for user_id in special_ids:
            manager.add_turn(user_id, "问题", "回答")
        
        for user_id in special_ids:
            context = manager.get_context(user_id)
            assert len(context) == 1
