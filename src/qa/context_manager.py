"""
对话上下文管理器模块

管理用户的对话历史上下文，支持多轮对话功能。

Requirements:
    - 2.4: 支持多轮对话（记住上下文）
        - 系统应维护每个用户的对话历史
        - 支持配置最大历史轮数（默认5轮）
        - 支持配置上下文过期时间（默认30分钟）
"""

import threading
from datetime import datetime, timedelta
from typing import Any

from .models import ConversationContext, ConversationTurn


class ContextManager:
    """
    对话上下文管理器
    
    管理用户的对话历史上下文，支持：
    - 内存存储的对话上下文
    - 配置最大历史轮数
    - 配置上下文过期时间
    - 线程安全的并发访问
    
    Attributes:
        max_history: 最大历史记录数（默认5轮）
        ttl_minutes: 上下文过期时间（分钟，默认30分钟）
    
    Example:
        >>> manager = ContextManager(max_history=5, ttl_minutes=30)
        >>> manager.add_turn("user123", "什么是RAG?", "RAG是检索增强生成...")
        >>> context = manager.get_context("user123")
        >>> len(context)
        1
    
    Requirements: 2.4
    """
    
    def __init__(self, max_history: int = 5, ttl_minutes: int = 30):
        """
        初始化上下文管理器
        
        Args:
            max_history: 最大历史记录数（默认5轮）
            ttl_minutes: 上下文过期时间（分钟，默认30分钟）
        
        Requirements: 2.4
        """
        self.max_history = max_history
        self.ttl_minutes = ttl_minutes
        
        # 内存存储：user_id -> ConversationContext
        self._contexts: dict[str, ConversationContext] = {}
        
        # 线程锁，确保并发安全
        self._lock = threading.RLock()
    
    def add_turn(
        self, 
        user_id: str, 
        query: str, 
        answer: str,
        sources: list[str] | None = None
    ) -> None:
        """
        添加一轮对话
        
        将用户的问题和机器人的回答添加到对话历史中。
        如果历史记录超过 max_history，则删除最旧的记录。
        
        Args:
            user_id: 用户 ID
            query: 用户问题
            answer: 机器人回答
            sources: 引用来源 URL 列表（可选）
        
        Example:
            >>> manager = ContextManager(max_history=3)
            >>> manager.add_turn("user1", "问题1", "回答1")
            >>> manager.add_turn("user1", "问题2", "回答2")
            >>> manager.add_turn("user1", "问题3", "回答3")
            >>> manager.add_turn("user1", "问题4", "回答4")
            >>> context = manager.get_context("user1")
            >>> len(context)  # 只保留最近3轮
            3
        
        Requirements: 2.4
        """
        with self._lock:
            # 创建新的对话轮次
            turn = ConversationTurn(
                query=query,
                answer=answer,
                timestamp=datetime.now(),
                sources=sources or [],
            )
            
            # 获取或创建用户上下文
            if user_id not in self._contexts:
                self._contexts[user_id] = ConversationContext(
                    user_id=user_id,
                    turns=[],
                    last_active=datetime.now(),
                )
            
            context = self._contexts[user_id]
            
            # 添加新轮次
            context.turns.append(turn)
            
            # 更新最后活跃时间
            context.last_active = datetime.now()
            
            # 如果超过最大历史数，删除最旧的记录
            if len(context.turns) > self.max_history:
                context.turns = context.turns[-self.max_history:]
    
    def get_context(self, user_id: str) -> list[dict[str, Any]]:
        """
        获取用户对话上下文
        
        返回用户的对话历史，如果上下文已过期则返回空列表。
        返回的是按时间顺序排列的对话轮次列表。
        
        Args:
            user_id: 用户 ID
            
        Returns:
            对话轮次列表，每个轮次包含 query, answer, timestamp, sources
            如果用户没有上下文或上下文已过期，返回空列表
        
        Example:
            >>> manager = ContextManager(max_history=5, ttl_minutes=30)
            >>> manager.add_turn("user1", "问题", "回答")
            >>> context = manager.get_context("user1")
            >>> context[0]["query"]
            '问题'
        
        Requirements: 2.4
        """
        with self._lock:
            # 检查用户是否有上下文
            if user_id not in self._contexts:
                return []
            
            context = self._contexts[user_id]
            
            # 检查上下文是否过期
            if self._is_expired(context):
                # 清除过期上下文
                del self._contexts[user_id]
                return []
            
            # 返回对话轮次列表（按时间顺序）
            return [turn.to_dict() for turn in context.turns]
    
    def clear_context(self, user_id: str) -> None:
        """
        清除用户上下文
        
        删除指定用户的所有对话历史。
        
        Args:
            user_id: 用户 ID
        
        Example:
            >>> manager = ContextManager()
            >>> manager.add_turn("user1", "问题", "回答")
            >>> manager.clear_context("user1")
            >>> manager.get_context("user1")
            []
        
        Requirements: 2.4
        """
        with self._lock:
            if user_id in self._contexts:
                del self._contexts[user_id]
    
    def _is_expired(self, context: ConversationContext) -> bool:
        """
        检查上下文是否过期
        
        Args:
            context: 对话上下文
            
        Returns:
            如果上下文已过期返回 True，否则返回 False
        """
        expiry_time = context.last_active + timedelta(minutes=self.ttl_minutes)
        return datetime.now() > expiry_time
    
    def cleanup_expired(self) -> int:
        """
        清理所有过期的上下文
        
        遍历所有用户上下文，删除已过期的记录。
        
        Returns:
            清理的上下文数量
        
        Example:
            >>> manager = ContextManager(ttl_minutes=0)  # 立即过期
            >>> manager.add_turn("user1", "问题", "回答")
            >>> import time; time.sleep(0.1)
            >>> cleaned = manager.cleanup_expired()
            >>> cleaned
            1
        """
        with self._lock:
            expired_users = [
                user_id 
                for user_id, context in self._contexts.items()
                if self._is_expired(context)
            ]
            
            for user_id in expired_users:
                del self._contexts[user_id]
            
            return len(expired_users)
    
    def get_stats(self) -> dict[str, Any]:
        """
        获取上下文管理器统计信息
        
        Returns:
            统计信息字典，包含：
            - total_users: 当前活跃用户数
            - total_turns: 总对话轮次数
            - max_history: 配置的最大历史数
            - ttl_minutes: 配置的过期时间
        
        Example:
            >>> manager = ContextManager(max_history=5, ttl_minutes=30)
            >>> manager.add_turn("user1", "问题1", "回答1")
            >>> manager.add_turn("user2", "问题2", "回答2")
            >>> stats = manager.get_stats()
            >>> stats["total_users"]
            2
        """
        with self._lock:
            total_turns = sum(
                len(context.turns) 
                for context in self._contexts.values()
            )
            
            return {
                "total_users": len(self._contexts),
                "total_turns": total_turns,
                "max_history": self.max_history,
                "ttl_minutes": self.ttl_minutes,
            }
    
    def get_user_ids(self) -> list[str]:
        """
        获取所有活跃用户 ID
        
        Returns:
            活跃用户 ID 列表
        """
        with self._lock:
            return list(self._contexts.keys())
