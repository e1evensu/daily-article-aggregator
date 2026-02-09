"""
飞书事件订阅服务器模块

使用 Flask 实现 HTTP 服务器，处理飞书事件回调。
支持 URL 验证（challenge 响应）和消息事件处理。
支持集成 QAEngine 进行问答处理。

Requirements:
    - 2.1: 支持飞书事件订阅（接收消息事件）
        - 系统应能接收飞书事件回调
        - 支持 URL 验证（challenge 响应）
        - 支持消息事件处理
    - 2.2: 支持群聊 @机器人 触发问答
    - 2.3: 支持私聊直接问答
    
Enhanced Requirements (Module 4):
    - 17.1: URL 验证挑战处理
    - 17.2: 请求签名验证
    - 17.4: 事件幂等性处理（去重）
    - 17.5: 健康检查端点
    - 17.6: 错误处理响应
"""

import hashlib
import hmac
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, TYPE_CHECKING

from flask import Flask, request, jsonify

from .config import EventServerConfig

# 使用 TYPE_CHECKING 避免循环导入
if TYPE_CHECKING:
    from .qa_engine import QAEngine
    from .rate_limiter import RateLimiter
    from src.bots.feishu_bot import FeishuAppBot

# 配置日志
logger = logging.getLogger(__name__)


class EventDeduplicator:
    """
    事件去重器
    
    使用 LRU 缓存存储已处理的事件 ID，防止重复处理。
    
    Attributes:
        max_size: 最大缓存大小
        ttl_seconds: 事件 ID 过期时间（秒）
    
    Requirements: 17.4
    """
    
    def __init__(self, max_size: int = 10000, ttl_seconds: int = 300):
        """
        初始化事件去重器
        
        Args:
            max_size: 最大缓存大小，默认 10000
            ttl_seconds: 事件 ID 过期时间（秒），默认 300（5分钟）
        """
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
    
    def is_duplicate(self, event_id: str) -> bool:
        """
        检查事件是否重复
        
        Args:
            event_id: 事件 ID
        
        Returns:
            True 如果事件已处理过，False 如果是新事件
        """
        if not event_id:
            return False
        
        current_time = time.time()
        
        with self._lock:
            # 清理过期条目
            self._cleanup_expired(current_time)
            
            # 检查是否存在
            if event_id in self._cache:
                # 更新访问时间
                self._cache.move_to_end(event_id)
                return True
            
            # 添加新事件
            self._cache[event_id] = current_time
            
            # 如果超过最大大小，移除最旧的
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
            
            return False
    
    def _cleanup_expired(self, current_time: float) -> None:
        """清理过期的事件 ID"""
        expired_keys = [
            key for key, timestamp in self._cache.items()
            if current_time - timestamp > self._ttl_seconds
        ]
        for key in expired_keys:
            del self._cache[key]
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    @property
    def size(self) -> int:
        """获取当前缓存大小"""
        return len(self._cache)


class FeishuEventServer:
    """
    飞书事件订阅服务器
    
    使用 Flask 实现 HTTP 服务器，接收和处理飞书事件回调。
    支持 URL 验证（challenge 响应）和消息事件处理。
    支持集成 QAEngine 进行问答处理。
    
    Enhanced Features (Module 4):
    - 请求签名验证（使用 encrypt_key）
    - 事件幂等性处理（防止重复处理）
    - 健康检查端点
    
    Attributes:
        host: 监听地址
        port: 监听端口
        verification_token: 飞书验证 token
        encrypt_key: 加密密钥（可选，用于签名验证）
        app: Flask 应用实例
        qa_engine: 问答引擎实例（可选）
        feishu_bot: 飞书应用机器人实例（可选）
        rate_limiter: 频率限制器实例（可选）
        deduplicator: 事件去重器实例
    
    Example:
        >>> from src.qa.event_server import FeishuEventServer
        >>> from src.qa.config import EventServerConfig
        >>> 
        >>> config = EventServerConfig(
        ...     host="0.0.0.0",
        ...     port=8080,
        ...     verification_token="your_token",
        ...     encrypt_key="your_encrypt_key"  # 用于签名验证
        ... )
        >>> server = FeishuEventServer(config)
        >>> 
        >>> # 设置消息处理器
        >>> def handle_message(event):
        ...     print(f"Received message: {event}")
        >>> server.set_message_handler(handle_message)
        >>> 
        >>> # 启动服务器
        >>> server.start()
        
        >>> # 或者集成 QAEngine
        >>> from src.qa.qa_engine import QAEngine
        >>> from src.bots.feishu_bot import FeishuAppBot
        >>> server.set_qa_engine(qa_engine)
        >>> server.set_feishu_bot(feishu_bot)
    
    Requirements: 2.1, 2.2, 2.3, 17.1, 17.2, 17.4, 17.5, 17.6
    """
    
    def __init__(
        self,
        config: EventServerConfig | dict[str, Any] | None = None,
        qa_engine: "QAEngine | None" = None,
        feishu_bot: "FeishuAppBot | None" = None,
        rate_limiter: "RateLimiter | None" = None,
    ):
        """
        初始化飞书事件服务器
        
        Args:
            config: 事件服务器配置，可以是 EventServerConfig 对象或字典
            qa_engine: 问答引擎实例（可选，用于处理问答请求）
            feishu_bot: 飞书应用机器人实例（可选，用于发送回复）
            rate_limiter: 频率限制器实例（可选，用于限制请求频率）
        
        Example:
            >>> config = {"host": "0.0.0.0", "port": 8080, "verification_token": "xxx"}
            >>> server = FeishuEventServer(config)
            >>> 
            >>> # 集成 QAEngine
            >>> server = FeishuEventServer(config, qa_engine=qa_engine, feishu_bot=bot)
        
        Requirements: 2.1, 2.2, 2.3, 17.1, 17.2, 17.4, 17.5
        """
        # 解析配置
        if config is None:
            self._config = EventServerConfig()
        elif isinstance(config, EventServerConfig):
            self._config = config
        else:
            self._config = EventServerConfig.from_dict(config)
        
        # 服务器属性
        self.host = self._config.host
        self.port = self._config.port
        self.verification_token = self._config.verification_token
        self.encrypt_key = self._config.encrypt_key
        
        # Flask 应用
        self.app = Flask(__name__)
        self._setup_routes()
        
        # 消息处理器回调
        self._message_handler: Callable[[dict], None] | None = None
        
        # QA 集成组件（可选）
        self._qa_engine: "QAEngine | None" = qa_engine
        self._feishu_bot: "FeishuAppBot | None" = feishu_bot
        self._rate_limiter: "RateLimiter | None" = rate_limiter
        
        # 事件去重器 (Requirement 17.4)
        self._deduplicator = EventDeduplicator()
        
        # 服务器线程
        self._server_thread: threading.Thread | None = None
        self._is_running = False
        
        logger.info(
            f"FeishuEventServer initialized: host={self.host}, port={self.port}, "
            f"qa_engine={'enabled' if qa_engine else 'disabled'}, "
            f"feishu_bot={'enabled' if feishu_bot else 'disabled'}, "
            f"rate_limiter={'enabled' if rate_limiter else 'disabled'}, "
            f"signature_verification={'enabled' if self.encrypt_key else 'disabled'}"
        )
    
    @property
    def config(self) -> EventServerConfig:
        """获取事件服务器配置"""
        return self._config
    
    @property
    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return self._is_running
    
    @property
    def deduplicator(self) -> EventDeduplicator:
        """获取事件去重器"""
        return self._deduplicator
    
    @property
    def config(self) -> EventServerConfig:
        """获取事件服务器配置"""
        return self._config
    
    @property
    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return self._is_running
    
    def _setup_routes(self) -> None:
        """
        设置 Flask 路由
        
        配置事件回调端点和健康检查端点。
        """
        # 事件回调端点
        @self.app.route("/webhook/event", methods=["POST"])
        def handle_event():
            return self._handle_event_request()
        
        # 健康检查端点
        @self.app.route("/health", methods=["GET"])
        def health_check():
            return jsonify({"status": "ok", "service": "feishu-event-server"})
        
        # 根路径
        @self.app.route("/", methods=["GET"])
        def index():
            return jsonify({
                "service": "feishu-event-server",
                "version": "1.0.0",
                "endpoints": {
                    "event": "/webhook/event",
                    "health": "/health"
                }
            })
    
    def _handle_event_request(self) -> tuple[dict, int]:
        """
        处理事件请求
        
        解析请求体，验证签名和 token，检查幂等性，并根据事件类型分发处理。
        
        Returns:
            响应数据和 HTTP 状态码的元组
        
        Requirements: 2.1, 17.2, 17.4, 17.6
        """
        try:
            # 获取原始请求体（用于签名验证）
            raw_body = request.get_data(as_text=True)
            
            # 获取请求数据，使用 silent=True 避免抛出异常
            data = request.get_json(silent=True)
            if data is None:
                logger.warning("Received empty or invalid JSON request body")
                return {"error": "Empty or invalid JSON request body"}, 400
            
            logger.debug(f"Received event: {json.dumps(data, ensure_ascii=False)[:500]}")
            
            # 验证请求签名 (Requirement 17.2)
            if self.encrypt_key and not self._verify_signature(raw_body):
                logger.warning("Request signature verification failed")
                return {"error": "Invalid signature"}, 401
            
            # 处理加密消息（如果配置了 encrypt_key）
            if "encrypt" in data and self.encrypt_key:
                data = self._decrypt_message(data["encrypt"])
                if data is None:
                    return {"error": "Decryption failed"}, 400
            
            # 处理 URL 验证请求（challenge）(Requirement 17.1)
            if "challenge" in data:
                return self._handle_verification(data)
            
            # 验证 token
            if not self._verify_token(data):
                logger.warning("Token verification failed")
                return {"error": "Invalid token"}, 401
            
            # 检查事件幂等性 (Requirement 17.4)
            event_id = self._extract_event_id(data)
            if event_id and self._deduplicator.is_duplicate(event_id):
                logger.info(f"Duplicate event detected, skipping: {event_id}")
                return {"code": 0, "msg": "ok"}, 200
            
            # 处理事件
            return self._dispatch_event(data)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {"error": "Invalid JSON"}, 400
        except Exception as e:
            logger.error(f"Error handling event: {e}", exc_info=True)
            return {"error": "Internal server error"}, 500
    
    def _verify_signature(self, raw_body: str) -> bool:
        """
        验证请求签名
        
        飞书使用 HMAC-SHA256 签名验证请求的真实性。
        签名计算方式：HMAC-SHA256(timestamp + nonce + encrypt_key, body)
        
        Args:
            raw_body: 原始请求体
        
        Returns:
            签名是否有效
        
        Requirements: 17.2
        """
        if not self.encrypt_key:
            return True
        
        # 获取请求头中的签名信息
        timestamp = request.headers.get('X-Lark-Request-Timestamp', '')
        nonce = request.headers.get('X-Lark-Request-Nonce', '')
        signature = request.headers.get('X-Lark-Signature', '')
        
        # 如果没有签名头，可能是旧版本请求，跳过验证
        if not signature:
            logger.debug("No signature header found, skipping signature verification")
            return True
        
        # 计算签名
        sign_string = timestamp + nonce + self.encrypt_key + raw_body
        calculated_signature = hashlib.sha256(sign_string.encode('utf-8')).hexdigest()
        
        if calculated_signature != signature:
            logger.warning(
                f"Signature mismatch: expected={calculated_signature[:16]}..., "
                f"got={signature[:16]}..."
            )
            return False
        
        logger.debug("Request signature verified successfully")
        return True
    
    def _extract_event_id(self, data: dict) -> str | None:
        """
        从事件数据中提取事件 ID
        
        飞书事件 ID 可能在不同位置：
        - 新版格式：header.event_id
        - 旧版格式：uuid 或 event.message_id
        
        Args:
            data: 事件数据
        
        Returns:
            事件 ID，如果无法提取则返回 None
        
        Requirements: 17.4
        """
        # 新版格式
        header = data.get("header", {})
        event_id = header.get("event_id")
        if event_id:
            return event_id
        
        # 旧版格式
        event_id = data.get("uuid")
        if event_id:
            return event_id
        
        # 使用消息 ID 作为备选
        event = data.get("event", {})
        message = event.get("message", {})
        message_id = message.get("message_id") or event.get("message_id")
        if message_id:
            return f"msg_{message_id}"
        
        return None
    
    def _handle_verification(self, data: dict) -> tuple[dict, int]:
        """
        处理飞书 URL 验证请求
        
        飞书在配置事件订阅时会发送 challenge 请求，
        服务器需要返回相同的 challenge 值以完成验证。
        
        Args:
            data: 请求数据，包含 challenge 字段
        
        Returns:
            响应数据和 HTTP 状态码的元组
        
        Example:
            请求: {"challenge": "abc123", "token": "xxx", "type": "url_verification"}
            响应: {"challenge": "abc123"}
        
        Requirements: 2.1
        """
        challenge = data.get("challenge", "")
        token = data.get("token", "")
        event_type = data.get("type", "")
        
        logger.info(f"Received URL verification request: type={event_type}")
        
        # 验证 token（如果配置了）
        if self.verification_token and token != self.verification_token:
            logger.warning(
                f"URL verification token mismatch: "
                f"expected={self.verification_token[:4]}***, got={token[:4]}***"
            )
            return {"error": "Invalid verification token"}, 401
        
        logger.info("URL verification successful")
        return {"challenge": challenge}, 200
    
    def _verify_token(self, data: dict) -> bool:
        """
        验证事件请求的 token
        
        检查请求中的 token 是否与配置的 verification_token 匹配。
        
        Args:
            data: 请求数据
        
        Returns:
            验证是否通过
        
        Requirements: 2.1
        """
        # 如果没有配置 verification_token，跳过验证
        if not self.verification_token:
            return True
        
        # 飞书事件格式可能有两种：
        # 1. 旧版格式：token 在顶层
        # 2. 新版格式（v2.0）：token 在 header 中
        
        # 检查顶层 token
        token = data.get("token", "")
        if token == self.verification_token:
            return True
        
        # 检查 header 中的 token
        header = data.get("header", {})
        token = header.get("token", "")
        if token == self.verification_token:
            return True
        
        return False
    
    def _dispatch_event(self, data: dict) -> tuple[dict, int]:
        """
        分发事件到相应的处理器
        
        根据事件类型调用对应的处理方法。
        
        Args:
            data: 事件数据
        
        Returns:
            响应数据和 HTTP 状态码的元组
        
        Requirements: 2.1
        """
        # 获取事件类型
        # 新版格式（v2.0）
        header = data.get("header", {})
        event_type = header.get("event_type", "")
        
        # 旧版格式
        if not event_type:
            event = data.get("event", {})
            event_type = event.get("type", data.get("type", ""))
        
        logger.info(f"Dispatching event: type={event_type}")
        
        # 处理消息事件
        if event_type in ["im.message.receive_v1", "message"]:
            return self._handle_message_event(data)
        
        # 未知事件类型
        logger.debug(f"Unhandled event type: {event_type}")
        return {"code": 0, "msg": "ok"}, 200
    
    def _handle_message_event(self, data: dict) -> tuple[dict, int]:
        """
        处理消息事件
        
        解析消息内容并调用消息处理器回调。
        
        Args:
            data: 消息事件数据
        
        Returns:
            响应数据和 HTTP 状态码的元组
        
        Requirements: 2.1
        """
        try:
            # 提取事件数据
            event = data.get("event", {})
            
            # 新版格式（v2.0）
            if "message" in event:
                message = event.get("message", {})
                sender = event.get("sender", {})
                
                event_info = {
                    "message_id": message.get("message_id", ""),
                    "chat_id": message.get("chat_id", ""),
                    "chat_type": message.get("chat_type", ""),
                    "content": message.get("content", ""),
                    "message_type": message.get("message_type", ""),
                    "mentions": message.get("mentions", []),
                    "sender_id": sender.get("sender_id", {}).get("open_id", ""),
                    "sender_type": sender.get("sender_type", ""),
                }
            else:
                # 旧版格式
                event_info = {
                    "message_id": event.get("message_id", ""),
                    "chat_id": event.get("open_chat_id", ""),
                    "chat_type": event.get("chat_type", ""),
                    "content": event.get("text", ""),
                    "message_type": event.get("msg_type", ""),
                    "mentions": [],
                    "sender_id": event.get("open_id", ""),
                    "sender_type": event.get("sender_type", "user"),
                }
            
            # 解析消息内容并检测触发条件
            parsed_message = self._parse_message_content(event_info)
            event_info.update(parsed_message)
            
            logger.info(
                f"Received message: chat_id={event_info['chat_id']}, "
                f"chat_type={event_info['chat_type']}, "
                f"is_mentioned={event_info.get('is_mentioned', False)}, "
                f"is_private={event_info.get('is_private', False)}, "
                f"sender={event_info['sender_id'][:8] if event_info['sender_id'] else 'unknown'}..."
            )
            
            # 调用消息处理器（在后台线程中处理，避免阻塞响应）
            # 如果设置了消息处理器或 QA 引擎，都需要启动后台线程
            should_process = (
                self._message_handler is not None or 
                (self._qa_engine is not None and event_info.get("should_respond", False))
            )
            
            if should_process:
                logger.info(
                    f"Starting background thread for message processing: "
                    f"has_handler={self._message_handler is not None}, "
                    f"has_qa_engine={self._qa_engine is not None}, "
                    f"should_respond={event_info.get('should_respond', False)}"
                )
                threading.Thread(
                    target=self._safe_handle_message,
                    args=(event_info,),
                    daemon=True
                ).start()
            else:
                logger.debug(
                    f"Skipping message processing: no handler and no QA engine configured, "
                    f"or message does not require response"
                )
            
            # 立即返回成功响应
            return {"code": 0, "msg": "ok"}, 200
            
        except Exception as e:
            logger.error(f"Error handling message event: {e}", exc_info=True)
            return {"code": 0, "msg": "ok"}, 200  # 仍然返回成功，避免飞书重试
    
    def _parse_message_content(self, event_info: dict) -> dict:
        """
        解析消息内容，检测 @mention 和私聊
        
        飞书消息内容格式：
        - 文本消息: {"text": "@_user_1 问题内容"}
        - 富文本消息: {"content": [[{"tag": "at", "user_id": "xxx"}, {"tag": "text", "text": "问题"}]]}
        
        Args:
            event_info: 消息事件信息
        
        Returns:
            解析结果字典，包含：
            - text: 解析后的纯文本内容
            - is_mentioned: 是否 @了机器人
            - is_private: 是否是私聊消息
            - question: 提取的问题文本（去除 @mention）
            - should_respond: 是否应该响应（私聊或被 @）
        
        Requirements: 2.2, 2.3
        """
        result = {
            "text": "",
            "is_mentioned": False,
            "is_private": False,
            "question": "",
            "should_respond": False,
        }
        
        # 检测是否是私聊
        chat_type = event_info.get("chat_type", "")
        result["is_private"] = chat_type == "p2p"
        
        # 解析消息内容
        raw_content = event_info.get("content", "")
        message_type = event_info.get("message_type", "text")
        mentions = event_info.get("mentions", [])
        
        # 解析 JSON 格式的内容
        text_content = self._extract_text_from_content(raw_content, message_type)
        result["text"] = text_content
        
        # 检测 @mention
        result["is_mentioned"] = self._detect_mention(mentions, text_content)
        
        # 提取问题文本（去除 @mention 前缀）
        result["question"] = self._extract_question(text_content, mentions)
        
        # 判断是否应该响应
        # 私聊直接响应，群聊需要 @机器人
        result["should_respond"] = result["is_private"] or result["is_mentioned"]
        
        return result
    
    def _extract_text_from_content(
        self,
        content: str,
        message_type: str
    ) -> str:
        """
        从飞书消息内容中提取纯文本
        
        Args:
            content: 原始消息内容（JSON 字符串）
            message_type: 消息类型（text, post, etc.）
        
        Returns:
            提取的纯文本内容
        
        Requirements: 2.1
        """
        if not content:
            return ""
        
        # 如果内容不是 JSON 格式，直接返回
        if not content.startswith("{") and not content.startswith("["):
            return content.strip()
        
        try:
            content_data = json.loads(content)
        except json.JSONDecodeError:
            # 解析失败，返回原始内容
            return content.strip()
        
        # 处理文本消息 {"text": "..."}
        if isinstance(content_data, dict) and "text" in content_data:
            return content_data["text"].strip()
        
        # 处理富文本消息 {"content": [[...]]}
        if isinstance(content_data, dict) and "content" in content_data:
            return self._extract_text_from_rich_content(content_data["content"])
        
        # 其他格式，尝试提取 text 字段
        if isinstance(content_data, dict):
            for key in ["text", "content", "title"]:
                if key in content_data and isinstance(content_data[key], str):
                    return content_data[key].strip()
        
        return ""
    
    def _extract_text_from_rich_content(self, content: list) -> str:
        """
        从富文本内容中提取纯文本
        
        富文本格式: [[{"tag": "text", "text": "..."}, {"tag": "at", ...}], ...]
        
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
                    # @mention 用占位符表示，后续会处理
                    text_parts.append("@")
        
        return "".join(text_parts).strip()
    
    def _detect_mention(self, mentions: list, text_content: str) -> bool:
        """
        检测消息是否 @了机器人
        
        飞书 mentions 格式:
        [{"key": "@_user_1", "id": {"open_id": "xxx", "user_id": "yyy"}, "name": "机器人名"}]
        
        Args:
            mentions: 飞书消息中的 mentions 列表
            text_content: 消息文本内容
        
        Returns:
            是否 @了机器人
        
        Requirements: 2.2
        """
        # 如果有 mentions 列表，说明消息中有 @
        if mentions and len(mentions) > 0:
            return True
        
        # 备用检测：检查文本中是否有 @_user_ 格式的 mention
        # 飞书在文本中用 @_user_1 这样的占位符表示 @
        if "@_user_" in text_content:
            return True
        
        return False
    
    def _extract_question(self, text_content: str, mentions: list) -> str:
        """
        从消息文本中提取问题内容（去除 @mention 前缀）
        
        Args:
            text_content: 消息文本内容
            mentions: mentions 列表
        
        Returns:
            提取的问题文本
        
        Requirements: 2.2, 2.3
        """
        if not text_content:
            return ""
        
        question = text_content
        
        # 移除 @_user_N 格式的占位符
        import re
        question = re.sub(r'@_user_\d+\s*', '', question)
        
        # 移除开头的 @ 符号（可能是富文本解析后的残留）
        question = re.sub(r'^@\s*', '', question)
        
        # 移除 mentions 中的名称（如果出现在文本中）
        for mention in mentions:
            if isinstance(mention, dict):
                name = mention.get("name", "")
                if name and name in question:
                    question = question.replace(f"@{name}", "").strip()
                    question = question.replace(name, "").strip()
        
        return question.strip()
    
    def _safe_handle_message(self, event_info: dict) -> None:
        """
        安全地调用消息处理器
        
        捕获处理器中的异常，避免影响服务器运行。
        如果配置了 QAEngine，会自动处理问答请求。
        
        Args:
            event_info: 消息事件信息
        
        Requirements: 2.2, 2.3
        """
        try:
            logger.info(
                f"Processing message in background thread: "
                f"should_respond={event_info.get('should_respond', False)}, "
                f"has_qa_engine={self._qa_engine is not None}, "
                f"has_feishu_bot={self._feishu_bot is not None}"
            )
            
            # 首先调用自定义消息处理器（如果设置了）
            if self._message_handler:
                logger.debug("Calling custom message handler")
                self._message_handler(event_info)
            
            # 如果配置了 QAEngine，处理问答请求
            if self._qa_engine and event_info.get("should_respond", False):
                logger.info("Calling QA engine to process message")
                result = self.process_qa_message(event_info)
                logger.info(f"QA processing result: {result}")
            elif not self._qa_engine:
                logger.warning("QA engine not configured, cannot process QA request")
            elif not event_info.get("should_respond", False):
                logger.debug("Message does not require response (should_respond=False)")
                
        except Exception as e:
            logger.error(f"Error in message handler: {e}", exc_info=True)
    
    def _decrypt_message(self, encrypted: str) -> dict | None:
        """
        解密加密的消息
        
        使用 AES 解密飞书发送的加密消息。
        
        Args:
            encrypted: 加密的消息字符串
        
        Returns:
            解密后的消息字典，失败返回 None
        
        Note:
            需要安装 pycryptodome 库才能使用加密功能。
        """
        if not self.encrypt_key:
            logger.warning("Encrypt key not configured, cannot decrypt message")
            return None
        
        try:
            import base64
            from Crypto.Cipher import AES
            
            # 飞书使用 AES-256-CBC 加密
            key = hashlib.sha256(self.encrypt_key.encode()).digest()
            encrypted_bytes = base64.b64decode(encrypted)
            
            # IV 是加密数据的前 16 字节
            iv = encrypted_bytes[:16]
            cipher = AES.new(key, AES.MODE_CBC, iv)
            
            # 解密并去除 PKCS7 填充
            decrypted = cipher.decrypt(encrypted_bytes[16:])
            padding_len = decrypted[-1]
            decrypted = decrypted[:-padding_len]
            
            return json.loads(decrypted.decode("utf-8"))
            
        except ImportError:
            logger.error(
                "pycryptodome not installed, cannot decrypt message. "
                "Install with: pip install pycryptodome"
            )
            return None
        except Exception as e:
            logger.error(f"Error decrypting message: {e}")
            return None
    
    def set_message_handler(
        self,
        handler: Callable[[dict], None]
    ) -> None:
        """
        设置消息处理器回调
        
        当收到消息事件时，会调用此处理器。
        
        Args:
            handler: 消息处理器函数，接收事件信息字典作为参数
        
        Example:
            >>> def my_handler(event):
            ...     print(f"Message from {event['sender_id']}: {event['content']}")
            >>> server.set_message_handler(my_handler)
        
        Requirements: 2.1
        """
        self._message_handler = handler
        logger.info("Message handler set")
    
    def set_qa_engine(self, qa_engine: "QAEngine") -> None:
        """
        设置问答引擎
        
        设置后，当收到需要响应的消息时，会自动调用 QAEngine 处理问答。
        
        Args:
            qa_engine: QAEngine 实例
        
        Example:
            >>> from src.qa.qa_engine import QAEngine
            >>> server.set_qa_engine(qa_engine)
        
        Requirements: 2.2, 2.3
        """
        self._qa_engine = qa_engine
        logger.info("QA engine set")
    
    def set_feishu_bot(self, feishu_bot: "FeishuAppBot") -> None:
        """
        设置飞书应用机器人
        
        设置后，问答回复会通过 FeishuAppBot 发送给用户。
        
        Args:
            feishu_bot: FeishuAppBot 实例
        
        Example:
            >>> from src.bots.feishu_bot import FeishuAppBot
            >>> bot = FeishuAppBot(app_id="xxx", app_secret="yyy")
            >>> server.set_feishu_bot(bot)
        
        Requirements: 2.2, 2.3
        """
        self._feishu_bot = feishu_bot
        logger.info("Feishu bot set")
    
    def set_rate_limiter(self, rate_limiter: "RateLimiter") -> None:
        """
        设置频率限制器
        
        设置后，会在处理问答请求前检查频率限制。
        
        Args:
            rate_limiter: RateLimiter 实例
        
        Example:
            >>> from src.qa.rate_limiter import RateLimiter
            >>> limiter = RateLimiter()
            >>> server.set_rate_limiter(limiter)
        
        Requirements: 5.4
        """
        self._rate_limiter = rate_limiter
        logger.info("Rate limiter set")
    
    @property
    def qa_engine(self) -> "QAEngine | None":
        """获取问答引擎实例"""
        return self._qa_engine
    
    @property
    def feishu_bot(self) -> "FeishuAppBot | None":
        """获取飞书应用机器人实例"""
        return self._feishu_bot
    
    @property
    def rate_limiter(self) -> "RateLimiter | None":
        """获取频率限制器实例"""
        return self._rate_limiter
    
    def process_qa_message(self, event_info: dict) -> dict | None:
        """
        处理问答消息
        
        当消息需要响应时（私聊或被 @），调用 QAEngine 处理问答，
        并通过 FeishuAppBot 发送回复。
        
        Args:
            event_info: 解析后的消息事件信息
        
        Returns:
            处理结果字典，包含：
            - success: 是否处理成功
            - answer: 回答内容（如果成功）
            - error: 错误信息（如果失败）
            - rate_limited: 是否被频率限制
            如果不需要响应或未配置 QAEngine，返回 None
        
        Example:
            >>> result = server.process_qa_message(event_info)
            >>> if result and result["success"]:
            ...     print(f"Answer: {result['answer']}")
        
        Requirements: 2.2, 2.3
        """
        # 检查是否需要响应
        if not event_info.get("should_respond", False):
            logger.debug("Message does not require response, skipping QA processing")
            return None
        
        # 检查是否配置了 QAEngine
        if not self._qa_engine:
            logger.debug("QA engine not configured, skipping QA processing")
            return None
        
        sender_id = event_info.get("sender_id", "")
        chat_id = event_info.get("chat_id", "")
        question = event_info.get("question", "")
        is_private = event_info.get("is_private", False)
        
        if not question:
            logger.warning("Empty question, skipping QA processing")
            return {
                "success": False,
                "error": "Empty question",
                "rate_limited": False,
            }
        
        logger.info(
            f"Processing QA message: sender={sender_id[:8] if sender_id else 'unknown'}..., "
            f"chat_id={chat_id[:8] if chat_id else 'unknown'}..., "
            f"is_private={is_private}, question={question[:50]}..."
        )
        
        # 检查频率限制
        if self._rate_limiter:
            rate_result = self._rate_limiter.is_allowed(sender_id)
            if not rate_result.allowed:
                logger.warning(
                    f"Rate limited for user {sender_id[:8] if sender_id else 'unknown'}..., "
                    f"retry after {rate_result.reset_after:.1f}s"
                )
                
                # 发送频率限制提示
                error_message = rate_result.error.message if rate_result.error else "请求过于频繁，请稍后再试"
                self._send_reply(
                    message=error_message,
                    chat_id=chat_id,
                    sender_id=sender_id,
                    is_private=is_private
                )
                
                return {
                    "success": False,
                    "error": error_message,
                    "rate_limited": True,
                    "retry_after": rate_result.reset_after,
                }
        
        # 调用 QAEngine 处理问答
        try:
            response = self._qa_engine.process_query(
                query=question,
                user_id=sender_id,
                chat_id=chat_id if not is_private else None
            )
            
            answer = response.answer
            sources = response.sources
            confidence = response.confidence
            
            logger.info(
                f"QA response generated: confidence={confidence:.2f}, "
                f"sources={len(sources)}, answer_length={len(answer)}"
            )
            
            # 发送回复
            send_success = self._send_reply(
                message=answer,
                chat_id=chat_id,
                sender_id=sender_id,
                is_private=is_private
            )
            
            return {
                "success": send_success,
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
                "rate_limited": False,
            }
            
        except Exception as e:
            logger.error(f"Error processing QA message: {e}", exc_info=True)
            
            # 发送错误提示
            error_message = "抱歉，处理您的问题时出现了错误，请稍后再试。"
            self._send_reply(
                message=error_message,
                chat_id=chat_id,
                sender_id=sender_id,
                is_private=is_private
            )
            
            return {
                "success": False,
                "error": str(e),
                "rate_limited": False,
            }
    
    def _send_reply(
        self,
        message: str,
        chat_id: str,
        sender_id: str,
        is_private: bool
    ) -> bool:
        """
        发送回复消息
        
        通过 FeishuAppBot 发送回复。私聊时发送给用户，
        群聊时发送到群组。
        
        Args:
            message: 回复消息内容
            chat_id: 聊天 ID
            sender_id: 发送者 ID
            is_private: 是否是私聊
        
        Returns:
            是否发送成功
        
        Requirements: 2.2, 2.3
        """
        if not self._feishu_bot:
            logger.warning("Feishu bot not configured, cannot send reply")
            return False
        
        if not message:
            logger.warning("Empty message, skipping send")
            return False
        
        logger.info(
            f"Attempting to send reply: is_private={is_private}, "
            f"chat_id={chat_id[:8] if chat_id else 'none'}..., "
            f"sender_id={sender_id[:8] if sender_id else 'none'}..., "
            f"message_length={len(message)}"
        )
        
        try:
            if is_private:
                # 私聊：发送给用户
                logger.info(f"Sending private message to user: {sender_id[:8] if sender_id else 'none'}...")
                success = self._feishu_bot.send_text_to_user(sender_id, message)
            else:
                # 群聊：发送到群组
                logger.info(f"Sending group message to chat: {chat_id[:8] if chat_id else 'none'}...")
                content = {"text": message}
                success = self._feishu_bot.send_message_to_chat(
                    chat_id, "text", content
                )
            
            if success:
                logger.info(
                    f"Reply sent successfully: "
                    f"{'private' if is_private else 'group'}, "
                    f"message_length={len(message)}"
                )
            else:
                logger.error(
                    f"Failed to send reply: "
                    f"{'private' if is_private else 'group'}, "
                    f"check feishu_bot logs for details"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending reply: {e}", exc_info=True)
            return False
    
    def handle_message(self, event_data: dict) -> dict:
        """
        处理消息事件（公共接口）
        
        解析飞书消息事件格式，检测 @mention 和私聊消息，
        提取问题文本并返回解析结果。
        
        Args:
            event_data: 飞书消息事件数据，可以是完整的事件数据或简化的消息信息
        
        Returns:
            解析后的消息信息字典，包含：
            - message_id: 消息 ID
            - chat_id: 聊天 ID
            - chat_type: 聊天类型（p2p/group）
            - content: 原始消息内容
            - text: 解析后的纯文本
            - is_mentioned: 是否 @了机器人
            - is_private: 是否是私聊
            - question: 提取的问题文本
            - should_respond: 是否应该响应
            - sender_id: 发送者 ID
        
        Example:
            >>> event_data = {
            ...     "header": {"event_type": "im.message.receive_v1"},
            ...     "event": {
            ...         "message": {
            ...             "chat_type": "group",
            ...             "content": '{"text": "@_user_1 什么是RAG？"}',
            ...             "mentions": [{"key": "@_user_1", "name": "Bot"}]
            ...         },
            ...         "sender": {"sender_id": {"open_id": "user123"}}
            ...     }
            ... }
            >>> result = server.handle_message(event_data)
            >>> result["is_mentioned"]
            True
            >>> result["question"]
            "什么是RAG？"
        
        Requirements: 2.1, 2.2, 2.3
        """
        # 提取事件数据
        event = event_data.get("event", event_data)
        
        # 新版格式（v2.0）- 有 message 字段
        if "message" in event:
            message = event.get("message", {})
            sender = event.get("sender", {})
            
            event_info = {
                "message_id": message.get("message_id", ""),
                "chat_id": message.get("chat_id", ""),
                "chat_type": message.get("chat_type", ""),
                "content": message.get("content", ""),
                "message_type": message.get("message_type", "text"),
                "mentions": message.get("mentions", []),
                "sender_id": sender.get("sender_id", {}).get("open_id", ""),
                "sender_type": sender.get("sender_type", ""),
            }
        elif "chat_type" in event and "content" in event:
            # 已经是简化格式（有 chat_type 和 content）
            event_info = {
                "message_id": event.get("message_id", ""),
                "chat_id": event.get("chat_id", event.get("open_chat_id", "")),
                "chat_type": event.get("chat_type", ""),
                "content": event.get("content", ""),
                "message_type": event.get("message_type", "text"),
                "mentions": event.get("mentions", []),
                "sender_id": event.get("sender_id", event.get("open_id", "")),
                "sender_type": event.get("sender_type", "user"),
            }
        else:
            # 旧版格式 - 使用 open_chat_id, text, open_id 等字段
            event_info = {
                "message_id": event.get("message_id", ""),
                "chat_id": event.get("open_chat_id", event.get("chat_id", "")),
                "chat_type": event.get("chat_type", ""),
                "content": event.get("text", event.get("content", "")),
                "message_type": event.get("msg_type", event.get("message_type", "text")),
                "mentions": event.get("mentions", []),
                "sender_id": event.get("open_id", event.get("sender_id", "")),
                "sender_type": event.get("sender_type", "user"),
            }
        
        # 解析消息内容并检测触发条件
        parsed_message = self._parse_message_content(event_info)
        event_info.update(parsed_message)
        
        return event_info
    
    def handle_event(self, data: dict) -> dict:
        """
        手动处理事件（用于测试）
        
        直接处理事件数据，不通过 HTTP 请求。
        
        Args:
            data: 事件数据
        
        Returns:
            响应数据
        
        Example:
            >>> response = server.handle_event({
            ...     "challenge": "test123",
            ...     "token": "xxx",
            ...     "type": "url_verification"
            ... })
            >>> response
            {"challenge": "test123"}
        
        Requirements: 2.1
        """
        # 处理 URL 验证
        if "challenge" in data:
            response, _ = self._handle_verification(data)
            return response
        
        # 验证 token
        if not self._verify_token(data):
            return {"error": "Invalid token"}
        
        # 分发事件
        response, _ = self._dispatch_event(data)
        return response
    
    def start(self, threaded: bool = True, debug: bool = False) -> None:
        """
        启动事件服务器
        
        Args:
            threaded: 是否在新线程中启动（默认 True）
            debug: 是否启用 Flask 调试模式（默认 False）
        
        Example:
            >>> server.start()  # 在后台线程启动
            >>> server.start(threaded=False)  # 在当前线程启动（阻塞）
        
        Requirements: 2.1
        """
        if self._is_running:
            logger.warning("Server is already running")
            return
        
        logger.info(f"Starting FeishuEventServer on {self.host}:{self.port}")
        
        if threaded:
            self._server_thread = threading.Thread(
                target=self._run_server,
                args=(debug,),
                daemon=True
            )
            self._server_thread.start()
            self._is_running = True
            logger.info("Server started in background thread")
        else:
            self._is_running = True
            self._run_server(debug)
    
    def _run_server(self, debug: bool = False) -> None:
        """
        运行 Flask 服务器
        
        Args:
            debug: 是否启用调试模式
        """
        try:
            # 禁用 Flask 的默认日志
            import logging as flask_logging
            flask_log = flask_logging.getLogger("werkzeug")
            flask_log.setLevel(flask_logging.WARNING)
            
            self.app.run(
                host=self.host,
                port=self.port,
                debug=debug,
                use_reloader=False,  # 禁用重载器，避免线程问题
                threaded=True  # 启用多线程处理请求
            )
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            self._is_running = False
    
    def stop(self) -> None:
        """
        停止事件服务器
        
        Note:
            Flask 开发服务器不支持优雅关闭，
            此方法主要用于标记服务器状态。
            在生产环境中应使用 WSGI 服务器（如 gunicorn）。
        
        Requirements: 2.1
        """
        if not self._is_running:
            logger.warning("Server is not running")
            return
        
        logger.info("Stopping FeishuEventServer...")
        self._is_running = False
        
        # Flask 开发服务器不支持优雅关闭
        # 在生产环境中应使用 gunicorn 等 WSGI 服务器
        logger.info(
            "Note: Flask development server does not support graceful shutdown. "
            "Use a WSGI server like gunicorn in production."
        )
    
    def run(self, debug: bool = False) -> None:
        """
        运行事件服务器（阻塞模式）
        
        这是 start() 的别名，以非线程模式启动服务器。
        
        Args:
            debug: 是否启用 Flask 调试模式
        
        Example:
            >>> server.run()  # 阻塞当前线程
        
        Requirements: 2.1
        """
        self.start(threaded=False, debug=debug)
    
    def get_stats(self) -> dict[str, Any]:
        """
        获取服务器统计信息
        
        Returns:
            统计信息字典，包含：
            - is_running: 服务器是否运行中
            - host: 监听地址
            - port: 监听端口
            - has_message_handler: 是否设置了消息处理器
            - has_encrypt_key: 是否配置了加密密钥
            - has_qa_engine: 是否配置了问答引擎
            - has_feishu_bot: 是否配置了飞书机器人
            - has_rate_limiter: 是否配置了频率限制器
            - deduplicator_size: 去重器缓存大小
        """
        return {
            "is_running": self._is_running,
            "host": self.host,
            "port": self.port,
            "has_message_handler": self._message_handler is not None,
            "has_encrypt_key": bool(self.encrypt_key),
            "has_qa_engine": self._qa_engine is not None,
            "has_feishu_bot": self._feishu_bot is not None,
            "has_rate_limiter": self._rate_limiter is not None,
            "deduplicator_size": self._deduplicator.size,
        }


def create_event_server(
    config: EventServerConfig | dict[str, Any] | None = None,
) -> FeishuEventServer:
    """
    创建飞书事件服务器的工厂函数
    
    Args:
        config: 事件服务器配置
    
    Returns:
        FeishuEventServer 实例
    
    Example:
        >>> server = create_event_server({
        ...     "host": "0.0.0.0",
        ...     "port": 8080,
        ...     "verification_token": "your_token"
        ... })
    
    Requirements: 2.1
    """
    return FeishuEventServer(config)
