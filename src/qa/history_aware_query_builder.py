"""
历史感知查询构建器模块

基于对话历史构建增强查询，将历史上下文融入当前查询以提升检索质量。

Requirements:
    - 3.1: 接受可选的对话历史作为输入
    - 3.2: 使用对话历史增强查询理解和检索
    - 3.4: 历史超过 max_history_turns 时只使用最近的轮次
    - 3.5: 历史为空或未提供时，不使用历史上下文处理查询
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.qa.models import ConversationTurn

# 配置日志
logger = logging.getLogger(__name__)


class HistoryAwareQueryBuilder:
    """
    基于对话历史构建增强查询
    
    将对话历史融入当前查询，生成包含上下文信息的增强查询字符串，
    以提升 RAG 检索的相关性和准确性。
    
    Requirements:
        - 3.1: 接受可选的对话历史作为输入
        - 3.2: 使用对话历史增强查询理解和检索
        - 3.4: 历史超过 max_history_turns 时只使用最近的轮次
        - 3.5: 历史为空或未提供时，不使用历史上下文处理查询
    
    Property 5: History Truncation
        *For any* conversation history with length > max_history_turns, 
        the RAG_Engine SHALL use only the most recent max_history_turns entries, 
        preserving their chronological order.
    """
    
    def __init__(self, default_max_turns: int = 5):
        """
        初始化历史感知查询构建器
        
        Args:
            default_max_turns: 默认使用的最大历史轮数
        """
        self.default_max_turns = default_max_turns
        logger.info(f"HistoryAwareQueryBuilder initialized with default_max_turns={default_max_turns}")
    
    def build_query(
        self,
        current_query: str,
        history: list["ConversationTurn"] | None = None,
        max_turns: int | None = None
    ) -> str:
        """
        构建包含历史上下文的查询
        
        将对话历史中的关键信息融入当前查询，生成增强后的查询字符串。
        
        算法：
        1. 如果历史为空或未提供，直接返回当前查询（Requirement 3.5）
        2. 截断历史到 max_turns 轮，保留最近的轮次（Requirement 3.4）
        3. 从历史中提取关键上下文信息
        4. 将上下文信息与当前查询组合
        
        Args:
            current_query: 当前用户查询
            history: 对话历史列表（可选）
            max_turns: 使用的最大历史轮数（可选，默认使用 default_max_turns）
            
        Returns:
            增强后的查询字符串
        
        Requirements:
            - 3.1: 接受可选的对话历史作为输入
            - 3.2: 使用对话历史增强查询理解和检索
            - 3.4: 历史超过 max_history_turns 时只使用最近的轮次
            - 3.5: 历史为空或未提供时，不使用历史上下文处理查询
        
        Property 5: History Truncation
            *For any* conversation history with length > max_history_turns, 
            the RAG_Engine SHALL use only the most recent max_history_turns entries, 
            preserving their chronological order.
        
        Examples:
            >>> builder = HistoryAwareQueryBuilder()
            >>> # 无历史时直接返回原查询
            >>> builder.build_query("什么是RAG?", None)
            '什么是RAG?'
            >>> builder.build_query("什么是RAG?", [])
            '什么是RAG?'
            >>> # 有历史时构建增强查询
            >>> from src.qa.models import ConversationTurn
            >>> history = [ConversationTurn(query="什么是向量数据库?", answer="向量数据库是...")]
            >>> enhanced = builder.build_query("它有什么优点?", history)
            >>> "向量数据库" in enhanced
            True
        """
        # 处理空查询
        if not current_query or not current_query.strip():
            return ""
        
        current_query = current_query.strip()
        
        # Requirement 3.5: 历史为空或未提供时，不使用历史上下文处理查询
        if not history:
            logger.debug(f"No history provided, returning original query: '{current_query[:50]}...'")
            return current_query
        
        # 确定使用的最大轮数
        effective_max_turns = max_turns if max_turns is not None else self.default_max_turns
        
        # Requirement 3.4 / Property 5: 截断历史到 max_turns 轮，保留最近的轮次
        # 保持时间顺序（最早的在前，最近的在后）
        truncated_history = self._truncate_history(history, effective_max_turns)
        
        # 如果截断后历史为空，直接返回原查询
        if not truncated_history:
            return current_query
        
        # Requirement 3.2: 使用对话历史增强查询理解和检索
        enhanced_query = self._build_enhanced_query(current_query, truncated_history)
        
        logger.debug(
            f"Built enhanced query: original='{current_query[:30]}...', "
            f"history_turns={len(truncated_history)}, "
            f"enhanced='{enhanced_query[:50]}...'"
        )
        
        return enhanced_query
    
    def _truncate_history(
        self,
        history: list["ConversationTurn"],
        max_turns: int
    ) -> list["ConversationTurn"]:
        """
        截断历史到指定轮数，保留最近的轮次
        
        Property 5: History Truncation
            *For any* conversation history with length > max_history_turns, 
            the RAG_Engine SHALL use only the most recent max_history_turns entries, 
            preserving their chronological order.
        
        Args:
            history: 完整的对话历史列表
            max_turns: 最大保留轮数
            
        Returns:
            截断后的历史列表，保持时间顺序（最早在前，最近在后）
        
        Requirements:
            - 3.4: 历史超过 max_history_turns 时只使用最近的轮次
        """
        if max_turns <= 0:
            return []
        
        if len(history) <= max_turns:
            # 历史长度不超过限制，返回完整历史
            return list(history)
        
        # 历史长度超过限制，只保留最近的 max_turns 轮
        # 使用切片保持时间顺序
        truncated = history[-max_turns:]
        
        logger.debug(
            f"Truncated history: original_length={len(history)}, "
            f"max_turns={max_turns}, truncated_length={len(truncated)}"
        )
        
        return truncated
    
    def _build_enhanced_query(
        self,
        current_query: str,
        history: list["ConversationTurn"]
    ) -> str:
        """
        构建增强查询
        
        将历史上下文信息与当前查询组合，生成增强后的查询字符串。
        
        策略：
        1. 提取历史中的关键问题和主题
        2. 将上下文信息作为前缀添加到当前查询
        3. 保持查询的可读性和检索相关性
        
        Args:
            current_query: 当前用户查询
            history: 截断后的对话历史
            
        Returns:
            增强后的查询字符串
        
        Requirements:
            - 3.2: 使用对话历史增强查询理解和检索
        """
        # 提取历史上下文
        context_parts = []
        
        for turn in history:
            # 提取每轮对话的关键信息
            if turn.query:
                # 简化历史问题，只保留核心内容
                simplified_query = self._simplify_text(turn.query, max_length=100)
                context_parts.append(f"Q: {simplified_query}")
            
            if turn.answer:
                # 从回答中提取关键信息（简化处理）
                simplified_answer = self._simplify_text(turn.answer, max_length=150)
                context_parts.append(f"A: {simplified_answer}")
        
        # 如果没有有效的上下文，直接返回原查询
        if not context_parts:
            return current_query
        
        # 构建增强查询
        # 格式：[历史上下文] 当前问题
        context_str = " | ".join(context_parts)
        enhanced_query = f"[对话上下文: {context_str}] {current_query}"
        
        return enhanced_query
    
    def _simplify_text(self, text: str, max_length: int = 100) -> str:
        """
        简化文本，截断过长内容
        
        Args:
            text: 原始文本
            max_length: 最大长度
            
        Returns:
            简化后的文本
        """
        if not text:
            return ""
        
        text = text.strip()
        
        if len(text) <= max_length:
            return text
        
        # 截断并添加省略号
        return text[:max_length - 3] + "..."
    
    def get_truncated_history(
        self,
        history: list["ConversationTurn"] | None,
        max_turns: int | None = None
    ) -> list["ConversationTurn"]:
        """
        获取截断后的历史（用于外部访问）
        
        这是一个便捷方法，允许外部代码获取截断后的历史，
        而不需要构建完整的增强查询。
        
        Args:
            history: 完整的对话历史列表
            max_turns: 最大保留轮数（可选，默认使用 default_max_turns）
            
        Returns:
            截断后的历史列表
        
        Requirements:
            - 3.4: 历史超过 max_history_turns 时只使用最近的轮次
        
        Property 5: History Truncation
            *For any* conversation history with length > max_history_turns, 
            the RAG_Engine SHALL use only the most recent max_history_turns entries, 
            preserving their chronological order.
        """
        if not history:
            return []
        
        effective_max_turns = max_turns if max_turns is not None else self.default_max_turns
        return self._truncate_history(history, effective_max_turns)
