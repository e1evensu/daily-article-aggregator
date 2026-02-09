"""
飞书线程回复器模块

支持在消息线程中回复，包含来源链接和低置信度提示。

Requirements:
    - 14.3: 支持线程回复
    - 14.4: 回复内容包含来源链接
    - 14.5: 低置信度时显示提示
    - 16.1: 支持 thread_replies 配置开关
    - 16.2: 线程回复 API 调用
    - 16.3: 回复内容构建
    - 16.4: 低置信度提示
    - 16.5: 来源链接格式化
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from src.bots.feishu_bot import FeishuAppBot

logger = logging.getLogger(__name__)


@dataclass
class ReplyContent:
    """
    回复内容数据类
    
    Attributes:
        answer: 回答文本
        sources: 来源列表
        confidence: 置信度
        low_confidence_threshold: 低置信度阈值
    """
    answer: str
    sources: list[dict[str, Any]]
    confidence: float
    low_confidence_threshold: float = 0.5
    
    @property
    def is_low_confidence(self) -> bool:
        """是否为低置信度"""
        return self.confidence < self.low_confidence_threshold


class ThreadReplier:
    """
    飞书线程回复器
    
    支持在消息线程中回复，自动添加来源链接和低置信度提示。
    
    Attributes:
        feishu_bot: 飞书应用机器人实例
        thread_replies_enabled: 是否启用线程回复
        low_confidence_threshold: 低置信度阈值
        low_confidence_message: 低置信度提示消息
        max_sources: 最大显示来源数
    
    Examples:
        >>> from src.bots.feishu_bot import FeishuAppBot
        >>> bot = FeishuAppBot(app_id="xxx", app_secret="yyy")
        >>> replier = ThreadReplier(bot)
        >>> 
        >>> # 发送线程回复
        >>> replier.reply_in_thread(
        ...     chat_id="chat_123",
        ...     message_id="msg_456",
        ...     answer="RAG 是检索增强生成...",
        ...     sources=[{"title": "RAG 介绍", "url": "https://..."}],
        ...     confidence=0.85
        ... )
    
    Requirements: 14.3, 14.4, 14.5, 16.1, 16.2, 16.3, 16.4, 16.5
    """
    
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    def __init__(
        self,
        feishu_bot: "FeishuAppBot | None" = None,
        thread_replies_enabled: bool = True,
        low_confidence_threshold: float = 0.5,
        low_confidence_message: str = "⚠️ 以下回答置信度较低，仅供参考：",
        max_sources: int = 5
    ):
        """
        初始化线程回复器
        
        Args:
            feishu_bot: 飞书应用机器人实例
            thread_replies_enabled: 是否启用线程回复
            low_confidence_threshold: 低置信度阈值
            low_confidence_message: 低置信度提示消息
            max_sources: 最大显示来源数
        """
        self._feishu_bot = feishu_bot
        self.thread_replies_enabled = thread_replies_enabled
        self.low_confidence_threshold = low_confidence_threshold
        self.low_confidence_message = low_confidence_message
        self.max_sources = max_sources
        
        logger.info(
            f"ThreadReplier initialized: "
            f"thread_replies_enabled={thread_replies_enabled}, "
            f"low_confidence_threshold={low_confidence_threshold}"
        )
    
    @property
    def feishu_bot(self) -> "FeishuAppBot | None":
        """获取飞书机器人实例"""
        return self._feishu_bot
    
    def set_feishu_bot(self, bot: "FeishuAppBot") -> None:
        """设置飞书机器人实例"""
        self._feishu_bot = bot
        logger.info("Feishu bot set for ThreadReplier")
    
    def reply_in_thread(
        self,
        chat_id: str,
        message_id: str,
        answer: str,
        sources: list[dict[str, Any]] | None = None,
        confidence: float = 1.0,
        use_thread: bool | None = None
    ) -> bool:
        """
        在消息线程中回复
        
        Args:
            chat_id: 聊天 ID
            message_id: 要回复的消息 ID（作为线程根消息）
            answer: 回答文本
            sources: 来源列表
            confidence: 置信度
            use_thread: 是否使用线程回复（None 时使用默认配置）
        
        Returns:
            是否发送成功
        
        Requirements: 14.3, 16.1, 16.2
        """
        if not self._feishu_bot:
            logger.error("Feishu bot not configured, cannot send reply")
            return False
        
        # 确定是否使用线程回复
        should_use_thread = (
            use_thread if use_thread is not None 
            else self.thread_replies_enabled
        )
        
        # 构建回复内容
        reply_content = self.build_reply_content(
            answer=answer,
            sources=sources or [],
            confidence=confidence
        )
        
        # 发送回复
        if should_use_thread and message_id:
            return self._send_thread_reply(
                chat_id=chat_id,
                root_id=message_id,
                content=reply_content
            )
        else:
            return self._send_direct_reply(
                chat_id=chat_id,
                content=reply_content
            )
    
    def build_reply_content(
        self,
        answer: str,
        sources: list[dict[str, Any]],
        confidence: float
    ) -> str:
        """
        构建回复内容
        
        包含回答文本、来源链接和低置信度提示。
        
        Args:
            answer: 回答文本
            sources: 来源列表
            confidence: 置信度
        
        Returns:
            格式化的回复内容
        
        Requirements: 14.4, 14.5, 16.3, 16.4, 16.5
        """
        parts = []
        
        # 低置信度提示
        if confidence < self.low_confidence_threshold:
            parts.append(self.low_confidence_message)
            parts.append("")
        
        # 回答内容
        parts.append(answer)
        
        # 来源链接
        if sources:
            source_text = self.format_sources(sources)
            if source_text:
                parts.append("")
                parts.append(source_text)
        
        return "\n".join(parts)
    
    def format_sources(self, sources: list[dict[str, Any]]) -> str:
        """
        格式化来源链接
        
        Args:
            sources: 来源列表
        
        Returns:
            格式化的来源文本
        
        Requirements: 14.4, 16.5
        """
        if not sources:
            return ""
        
        # 限制来源数量
        display_sources = sources[:self.max_sources]
        
        lines = ["📚 参考来源："]
        for i, source in enumerate(display_sources, 1):
            title = source.get("title", "未知来源")
            url = source.get("url", "")
            
            if url:
                lines.append(f"{i}. {title}")
                lines.append(f"   {url}")
            else:
                lines.append(f"{i}. {title}")
        
        # 如果有更多来源
        if len(sources) > self.max_sources:
            remaining = len(sources) - self.max_sources
            lines.append(f"   ... 还有 {remaining} 个来源")
        
        return "\n".join(lines)
    
    def _send_thread_reply(
        self,
        chat_id: str,
        root_id: str,
        content: str
    ) -> bool:
        """
        发送线程回复
        
        Args:
            chat_id: 聊天 ID
            root_id: 线程根消息 ID
            content: 回复内容
        
        Returns:
            是否发送成功
        
        Requirements: 16.2
        """
        if not self._feishu_bot:
            return False
        
        headers = self._feishu_bot._get_headers()
        if not headers:
            logger.error("Failed to get access token for thread reply")
            return False
        
        try:
            url = f"{self.BASE_URL}/im/v1/messages"
            params = {"receive_id_type": "chat_id"}
            
            payload = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": content}),
                "reply_in_thread": True,
                "root_id": root_id
            }
            
            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=self._feishu_bot.timeout
            )
            
            if response.status_code != 200:
                logger.error(
                    f"Thread reply failed: HTTP {response.status_code}, "
                    f"response: {response.text}"
                )
                return False
            
            data = response.json()
            if data.get("code") != 0:
                logger.error(f"Thread reply failed: {data.get('msg')}")
                return False
            
            logger.info(f"Thread reply sent successfully to chat {chat_id[:8]}...")
            return True
            
        except requests.exceptions.Timeout:
            logger.error("Thread reply timeout")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Thread reply request error: {e}")
            return False
        except Exception as e:
            logger.error(f"Thread reply error: {e}")
            return False
    
    def _send_direct_reply(
        self,
        chat_id: str,
        content: str
    ) -> bool:
        """
        发送直接回复（非线程）
        
        Args:
            chat_id: 聊天 ID
            content: 回复内容
        
        Returns:
            是否发送成功
        """
        if not self._feishu_bot:
            return False
        
        try:
            return self._feishu_bot.send_message_to_chat(
                chat_id=chat_id,
                msg_type="text",
                content={"text": content}
            )
        except Exception as e:
            logger.error(f"Direct reply error: {e}")
            return False
    
    def reply_to_user(
        self,
        user_id: str,
        answer: str,
        sources: list[dict[str, Any]] | None = None,
        confidence: float = 1.0
    ) -> bool:
        """
        回复用户（私聊）
        
        Args:
            user_id: 用户 ID
            answer: 回答文本
            sources: 来源列表
            confidence: 置信度
        
        Returns:
            是否发送成功
        """
        if not self._feishu_bot:
            logger.error("Feishu bot not configured, cannot send reply")
            return False
        
        # 构建回复内容
        reply_content = self.build_reply_content(
            answer=answer,
            sources=sources or [],
            confidence=confidence
        )
        
        try:
            return self._feishu_bot.send_text_to_user(user_id, reply_content)
        except Exception as e:
            logger.error(f"Reply to user error: {e}")
            return False
