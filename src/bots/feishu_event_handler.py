"""
飞书事件处理器模块

处理飞书消息事件，支持 @mention 检测和 always_respond 模式。

Requirements:
    - 14.1: 接收飞书消息事件
    - 14.2: 解析消息内容
    - 15.1: 检测 @mention
    - 15.2: 提取 @mention 后的问题文本
    - 15.3: 支持多种 @mention 格式
    - 15.4: 支持 always_respond 模式
    - 15.5: 私聊消息直接响应
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FeishuMessage:
    """
    飞书消息数据类
    
    封装飞书消息的所有相关信息。
    
    Attributes:
        message_id: 消息 ID
        chat_id: 聊天 ID
        chat_type: 聊天类型（p2p/group）
        content: 原始消息内容
        message_type: 消息类型（text/post/interactive 等）
        mentions: @mention 列表
        sender_id: 发送者 ID
        sender_type: 发送者类型
        text: 解析后的纯文本
        is_mentioned: 是否 @了机器人
        is_private: 是否是私聊
        question: 提取的问题文本
        should_respond: 是否应该响应
        root_id: 根消息 ID（用于线程回复）
        parent_id: 父消息 ID（用于线程回复）
    
    Requirements: 14.1, 14.2
    """
    message_id: str = ""
    chat_id: str = ""
    chat_type: str = ""
    content: str = ""
    message_type: str = "text"
    mentions: list[dict] = field(default_factory=list)
    sender_id: str = ""
    sender_type: str = "user"
    text: str = ""
    is_mentioned: bool = False
    is_private: bool = False
    question: str = ""
    should_respond: bool = False
    root_id: str = ""
    parent_id: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
            "content": self.content,
            "message_type": self.message_type,
            "mentions": self.mentions,
            "sender_id": self.sender_id,
            "sender_type": self.sender_type,
            "text": self.text,
            "is_mentioned": self.is_mentioned,
            "is_private": self.is_private,
            "question": self.question,
            "should_respond": self.should_respond,
            "root_id": self.root_id,
            "parent_id": self.parent_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeishuMessage":
        """从字典创建实例"""
        return cls(
            message_id=data.get("message_id", ""),
            chat_id=data.get("chat_id", ""),
            chat_type=data.get("chat_type", ""),
            content=data.get("content", ""),
            message_type=data.get("message_type", "text"),
            mentions=data.get("mentions", []),
            sender_id=data.get("sender_id", ""),
            sender_type=data.get("sender_type", "user"),
            text=data.get("text", ""),
            is_mentioned=data.get("is_mentioned", False),
            is_private=data.get("is_private", False),
            question=data.get("question", ""),
            should_respond=data.get("should_respond", False),
            root_id=data.get("root_id", ""),
            parent_id=data.get("parent_id", ""),
        )


class FeishuEventHandler:
    """
    飞书事件处理器
    
    解析飞书消息事件，检测 @mention，提取问题文本。
    
    Attributes:
        always_respond: 是否总是响应（不需要 @mention）
        bot_user_id: 机器人用户 ID（用于精确检测 @mention）
    
    Examples:
        >>> handler = FeishuEventHandler()
        >>> message = handler.parse_event(event_data)
        >>> if message.should_respond:
        ...     print(f"Question: {message.question}")
        
        >>> # always_respond 模式
        >>> handler = FeishuEventHandler(always_respond=True)
        >>> message = handler.parse_event(event_data)
        >>> message.should_respond  # 总是 True（群聊中）
    
    Requirements: 14.1, 14.2, 15.1, 15.2, 15.3, 15.4, 15.5
    """
    
    def __init__(
        self,
        always_respond: bool = False,
        bot_user_id: str | None = None
    ):
        """
        初始化事件处理器
        
        Args:
            always_respond: 是否总是响应（不需要 @mention）
            bot_user_id: 机器人用户 ID（用于精确检测 @mention）
        """
        self.always_respond = always_respond
        self.bot_user_id = bot_user_id
        
        logger.info(
            f"FeishuEventHandler initialized: "
            f"always_respond={always_respond}, "
            f"bot_user_id={'set' if bot_user_id else 'not set'}"
        )
    
    def parse_event(self, event_data: dict[str, Any]) -> FeishuMessage:
        """
        解析飞书事件数据
        
        支持新版（v2.0）和旧版事件格式。
        
        Args:
            event_data: 飞书事件数据
        
        Returns:
            解析后的 FeishuMessage 对象
        
        Examples:
            >>> event_data = {
            ...     "event": {
            ...         "message": {
            ...             "chat_type": "group",
            ...             "content": '{"text": "@_user_1 什么是RAG？"}',
            ...             "mentions": [{"key": "@_user_1"}]
            ...         }
            ...     }
            ... }
            >>> message = handler.parse_event(event_data)
            >>> message.is_mentioned
            True
        
        Requirements: 14.1, 14.2
        """
        # 提取事件数据
        event = event_data.get("event", event_data)
        
        # 解析消息基本信息
        message = self._extract_message_info(event)
        
        # 解析消息内容
        message.text = self._extract_text_from_content(
            message.content, 
            message.message_type
        )
        
        # 检测 @mention
        message.is_mentioned = self._detect_mention(
            message.mentions, 
            message.text
        )
        
        # 检测私聊
        message.is_private = message.chat_type == "p2p"
        
        # 提取问题文本
        message.question = self._extract_question(
            message.text, 
            message.mentions
        )
        
        # 判断是否应该响应
        message.should_respond = self._should_respond(message)
        
        logger.debug(
            f"Parsed message: id={message.message_id[:8] if message.message_id else 'none'}..., "
            f"is_mentioned={message.is_mentioned}, "
            f"is_private={message.is_private}, "
            f"should_respond={message.should_respond}"
        )
        
        return message
    
    def _extract_message_info(self, event: dict[str, Any]) -> FeishuMessage:
        """
        从事件数据中提取消息基本信息
        
        Args:
            event: 事件数据
        
        Returns:
            FeishuMessage 对象（部分填充）
        """
        # 新版格式（v2.0）- 有 message 字段
        if "message" in event:
            message_data = event.get("message", {})
            sender = event.get("sender", {})
            
            return FeishuMessage(
                message_id=message_data.get("message_id", ""),
                chat_id=message_data.get("chat_id", ""),
                chat_type=message_data.get("chat_type", ""),
                content=message_data.get("content", ""),
                message_type=message_data.get("message_type", "text"),
                mentions=message_data.get("mentions", []),
                sender_id=sender.get("sender_id", {}).get("open_id", ""),
                sender_type=sender.get("sender_type", "user"),
                root_id=message_data.get("root_id", ""),
                parent_id=message_data.get("parent_id", ""),
            )
        
        # 已经是简化格式（有 chat_type 和 content）
        if "chat_type" in event and "content" in event:
            return FeishuMessage(
                message_id=event.get("message_id", ""),
                chat_id=event.get("chat_id", event.get("open_chat_id", "")),
                chat_type=event.get("chat_type", ""),
                content=event.get("content", ""),
                message_type=event.get("message_type", "text"),
                mentions=event.get("mentions", []),
                sender_id=event.get("sender_id", event.get("open_id", "")),
                sender_type=event.get("sender_type", "user"),
                root_id=event.get("root_id", ""),
                parent_id=event.get("parent_id", ""),
            )
        
        # 旧版格式
        return FeishuMessage(
            message_id=event.get("message_id", ""),
            chat_id=event.get("open_chat_id", event.get("chat_id", "")),
            chat_type=event.get("chat_type", ""),
            content=event.get("text", event.get("content", "")),
            message_type=event.get("msg_type", event.get("message_type", "text")),
            mentions=event.get("mentions", []),
            sender_id=event.get("open_id", event.get("sender_id", "")),
            sender_type=event.get("sender_type", "user"),
        )
    
    def _extract_text_from_content(
        self,
        content: str,
        message_type: str
    ) -> str:
        """
        从飞书消息内容中提取纯文本
        
        Args:
            content: 原始消息内容（JSON 字符串）
            message_type: 消息类型
        
        Returns:
            提取的纯文本内容
        
        Requirements: 14.2
        """
        if not content:
            return ""
        
        # 如果内容不是 JSON 格式，直接返回
        if not content.startswith("{") and not content.startswith("["):
            return content.strip()
        
        try:
            content_data = json.loads(content)
        except json.JSONDecodeError:
            return content.strip()
        
        # 处理文本消息 {"text": "..."}
        if isinstance(content_data, dict) and "text" in content_data:
            return content_data["text"].strip()
        
        # 处理富文本消息 {"content": [[...]]}
        if isinstance(content_data, dict) and "content" in content_data:
            return self._extract_text_from_rich_content(content_data["content"])
        
        # 其他格式
        if isinstance(content_data, dict):
            for key in ["text", "content", "title"]:
                if key in content_data and isinstance(content_data[key], str):
                    return content_data[key].strip()
        
        return ""
    
    def _extract_text_from_rich_content(self, content: list) -> str:
        """
        从富文本内容中提取纯文本
        
        Args:
            content: 富文本内容列表
        
        Returns:
            提取的纯文本
        """
        if not isinstance(content, list):
            return ""
        
        text_parts = []
        for paragraph in content:
            if not isinstance(paragraph, list):
                continue
            for element in paragraph:
                if not isinstance(element, dict):
                    continue
                tag = element.get("tag", "")
                if tag == "text":
                    text_parts.append(element.get("text", ""))
                elif tag == "at":
                    text_parts.append("@")
        
        return "".join(text_parts).strip()
    
    def _detect_mention(self, mentions: list, text_content: str) -> bool:
        """
        检测消息是否 @了机器人
        
        支持多种 @mention 格式：
        - mentions 列表中有条目
        - 文本中有 @_user_N 格式
        - 如果设置了 bot_user_id，精确匹配
        
        Args:
            mentions: 飞书消息中的 mentions 列表
            text_content: 消息文本内容
        
        Returns:
            是否 @了机器人
        
        Requirements: 15.1, 15.3
        """
        # 如果有 mentions 列表
        if mentions and len(mentions) > 0:
            # 如果设置了 bot_user_id，精确匹配
            if self.bot_user_id:
                for mention in mentions:
                    if isinstance(mention, dict):
                        mention_id = mention.get("id", {})
                        if isinstance(mention_id, dict):
                            if mention_id.get("open_id") == self.bot_user_id:
                                return True
                            if mention_id.get("user_id") == self.bot_user_id:
                                return True
                        elif mention_id == self.bot_user_id:
                            return True
                # 没有匹配到机器人
                return False
            else:
                # 没有设置 bot_user_id，有 mention 就认为是 @机器人
                return True
        
        # 备用检测：检查文本中是否有 @_user_ 格式
        if "@_user_" in text_content:
            return True
        
        return False
    
    def _extract_question(self, text_content: str, mentions: list) -> str:
        """
        从消息文本中提取问题内容
        
        去除 @mention 前缀和相关文本。
        
        Args:
            text_content: 消息文本内容
            mentions: mentions 列表
        
        Returns:
            提取的问题文本
        
        Requirements: 15.2
        """
        if not text_content:
            return ""
        
        question = text_content
        
        # 移除 @_user_N 格式的占位符
        question = re.sub(r'@_user_\d+\s*', '', question)
        
        # 移除开头的 @ 符号
        question = re.sub(r'^@\s*', '', question)
        
        # 移除 mentions 中的名称
        for mention in mentions:
            if isinstance(mention, dict):
                name = mention.get("name", "")
                if name and name in question:
                    question = question.replace(f"@{name}", "").strip()
                    question = question.replace(name, "").strip()
        
        return question.strip()
    
    def _should_respond(self, message: FeishuMessage) -> bool:
        """
        判断是否应该响应消息
        
        响应条件：
        1. 私聊消息：总是响应
        2. 群聊消息：被 @mention 或 always_respond 模式
        
        Args:
            message: 解析后的消息
        
        Returns:
            是否应该响应
        
        Requirements: 15.4, 15.5
        """
        # 私聊总是响应
        if message.is_private:
            return True
        
        # always_respond 模式
        if self.always_respond:
            return True
        
        # 群聊需要 @mention
        return message.is_mentioned
    
    def set_always_respond(self, value: bool) -> None:
        """
        设置 always_respond 模式
        
        Args:
            value: 是否启用 always_respond 模式
        """
        self.always_respond = value
        logger.info(f"always_respond mode set to: {value}")
    
    def set_bot_user_id(self, user_id: str) -> None:
        """
        设置机器人用户 ID
        
        Args:
            user_id: 机器人用户 ID
        """
        self.bot_user_id = user_id
        logger.info(f"bot_user_id set to: {user_id[:8] if user_id else 'none'}...")
