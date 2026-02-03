"""
飞书事件服务器单元测试

测试 FeishuEventServer 类的核心功能：
- URL 验证（challenge 响应）
- Token 验证
- 消息事件处理
- 服务器配置

Requirements:
    - 2.1: 支持飞书事件订阅（接收消息事件）
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.qa.event_server import FeishuEventServer, create_event_server
from src.qa.config import EventServerConfig


class TestFeishuEventServerInit:
    """测试 FeishuEventServer 初始化"""
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        server = FeishuEventServer()
        
        assert server.host == "0.0.0.0"
        assert server.port == 8080
        assert server.verification_token == ""
        assert server.encrypt_key == ""
        assert server.app is not None
        assert not server.is_running
    
    def test_init_with_config_object(self):
        """测试使用配置对象初始化"""
        config = EventServerConfig(
            host="127.0.0.1",
            port=9000,
            verification_token="test_token",
            encrypt_key="test_key"
        )
        server = FeishuEventServer(config)
        
        assert server.host == "127.0.0.1"
        assert server.port == 9000
        assert server.verification_token == "test_token"
        assert server.encrypt_key == "test_key"
    
    def test_init_with_dict_config(self):
        """测试使用字典配置初始化"""
        config = {
            "host": "localhost",
            "port": 8888,
            "verification_token": "dict_token"
        }
        server = FeishuEventServer(config)
        
        assert server.host == "localhost"
        assert server.port == 8888
        assert server.verification_token == "dict_token"
    
    def test_config_property(self):
        """测试配置属性"""
        config = EventServerConfig(port=9999)
        server = FeishuEventServer(config)
        
        assert server.config.port == 9999
        assert isinstance(server.config, EventServerConfig)


class TestURLVerification:
    """测试 URL 验证功能"""
    
    def test_handle_verification_success(self):
        """测试 URL 验证成功"""
        server = FeishuEventServer({"verification_token": "test_token"})
        
        data = {
            "challenge": "abc123xyz",
            "token": "test_token",
            "type": "url_verification"
        }
        
        response = server.handle_event(data)
        
        assert response == {"challenge": "abc123xyz"}
    
    def test_handle_verification_without_token_config(self):
        """测试未配置 token 时的 URL 验证"""
        server = FeishuEventServer()  # 无 verification_token
        
        data = {
            "challenge": "test_challenge",
            "token": "any_token",
            "type": "url_verification"
        }
        
        response = server.handle_event(data)
        
        assert response == {"challenge": "test_challenge"}
    
    def test_handle_verification_token_mismatch(self):
        """测试 token 不匹配时的 URL 验证"""
        server = FeishuEventServer({"verification_token": "correct_token"})
        
        data = {
            "challenge": "test_challenge",
            "token": "wrong_token",
            "type": "url_verification"
        }
        
        # 使用 Flask 测试客户端
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data=json.dumps(data),
                content_type="application/json"
            )
            
            assert response.status_code == 401
    
    def test_handle_verification_empty_challenge(self):
        """测试空 challenge 的 URL 验证"""
        server = FeishuEventServer()
        
        data = {
            "challenge": "",
            "type": "url_verification"
        }
        
        response = server.handle_event(data)
        
        assert response == {"challenge": ""}


class TestTokenVerification:
    """测试 Token 验证功能"""
    
    def test_verify_token_top_level(self):
        """测试顶层 token 验证"""
        server = FeishuEventServer({"verification_token": "my_token"})
        
        data = {
            "token": "my_token",
            "event": {"type": "message"}
        }
        
        assert server._verify_token(data) is True
    
    def test_verify_token_in_header(self):
        """测试 header 中的 token 验证（v2.0 格式）"""
        server = FeishuEventServer({"verification_token": "my_token"})
        
        data = {
            "header": {
                "token": "my_token",
                "event_type": "im.message.receive_v1"
            },
            "event": {}
        }
        
        assert server._verify_token(data) is True
    
    def test_verify_token_mismatch(self):
        """测试 token 不匹配"""
        server = FeishuEventServer({"verification_token": "correct_token"})
        
        data = {
            "token": "wrong_token",
            "event": {}
        }
        
        assert server._verify_token(data) is False
    
    def test_verify_token_no_config(self):
        """测试未配置 token 时跳过验证"""
        server = FeishuEventServer()  # 无 verification_token
        
        data = {
            "token": "any_token",
            "event": {}
        }
        
        assert server._verify_token(data) is True


class TestMessageEventHandling:
    """测试消息事件处理"""
    
    def test_handle_message_event_v2(self):
        """测试处理 v2.0 格式的消息事件"""
        server = FeishuEventServer()
        
        received_events = []
        def handler(event):
            received_events.append(event)
        
        server.set_message_handler(handler)
        
        data = {
            "header": {
                "event_type": "im.message.receive_v1",
                "token": ""
            },
            "event": {
                "message": {
                    "message_id": "msg_123",
                    "chat_id": "chat_456",
                    "chat_type": "group",
                    "content": '{"text": "Hello"}',
                    "message_type": "text",
                    "mentions": [{"id": {"open_id": "user_789"}}]
                },
                "sender": {
                    "sender_id": {"open_id": "sender_001"},
                    "sender_type": "user"
                }
            }
        }
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data=json.dumps(data),
                content_type="application/json"
            )
            
            assert response.status_code == 200
            
            # 等待异步处理完成
            import time
            time.sleep(0.1)
            
            assert len(received_events) == 1
            event = received_events[0]
            assert event["message_id"] == "msg_123"
            assert event["chat_id"] == "chat_456"
            assert event["sender_id"] == "sender_001"
    
    def test_handle_message_event_legacy(self):
        """测试处理旧版格式的消息事件"""
        server = FeishuEventServer()
        
        received_events = []
        def handler(event):
            received_events.append(event)
        
        server.set_message_handler(handler)
        
        data = {
            "token": "",
            "event": {
                "type": "message",
                "message_id": "legacy_msg",
                "open_chat_id": "legacy_chat",
                "chat_type": "private",
                "text": "Hello from legacy",
                "msg_type": "text",
                "open_id": "legacy_user"
            }
        }
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data=json.dumps(data),
                content_type="application/json"
            )
            
            assert response.status_code == 200
            
            import time
            time.sleep(0.1)
            
            assert len(received_events) == 1
            event = received_events[0]
            assert event["message_id"] == "legacy_msg"
            assert event["chat_id"] == "legacy_chat"
            assert event["content"] == "Hello from legacy"
    
    def test_handle_message_without_handler(self):
        """测试没有设置处理器时的消息处理"""
        server = FeishuEventServer()
        # 不设置 message_handler
        
        data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "message": {"message_id": "test"},
                "sender": {"sender_id": {"open_id": "user"}}
            }
        }
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data=json.dumps(data),
                content_type="application/json"
            )
            
            # 应该正常返回，不报错
            assert response.status_code == 200
    
    def test_message_handler_exception(self):
        """测试消息处理器抛出异常时的处理"""
        server = FeishuEventServer()
        
        def bad_handler(event):
            raise ValueError("Handler error")
        
        server.set_message_handler(bad_handler)
        
        data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "message": {"message_id": "test"},
                "sender": {"sender_id": {"open_id": "user"}}
            }
        }
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data=json.dumps(data),
                content_type="application/json"
            )
            
            # 应该正常返回，异常被捕获
            assert response.status_code == 200


class TestFlaskEndpoints:
    """测试 Flask 端点"""
    
    def test_health_endpoint(self):
        """测试健康检查端点"""
        server = FeishuEventServer()
        
        with server.app.test_client() as client:
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
            assert data["service"] == "feishu-event-server"
    
    def test_index_endpoint(self):
        """测试根路径端点"""
        server = FeishuEventServer()
        
        with server.app.test_client() as client:
            response = client.get("/")
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["service"] == "feishu-event-server"
            assert "endpoints" in data
    
    def test_event_endpoint_empty_body(self):
        """测试空请求体"""
        server = FeishuEventServer()
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data="",
                content_type="application/json"
            )
            
            assert response.status_code == 400
    
    def test_event_endpoint_invalid_json(self):
        """测试无效 JSON"""
        server = FeishuEventServer()
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data="not valid json",
                content_type="application/json"
            )
            
            assert response.status_code == 400


class TestServerLifecycle:
    """测试服务器生命周期"""
    
    def test_is_running_property(self):
        """测试 is_running 属性"""
        server = FeishuEventServer()
        
        assert server.is_running is False
    
    def test_stop_when_not_running(self):
        """测试停止未运行的服务器"""
        server = FeishuEventServer()
        
        # 不应该抛出异常
        server.stop()
        assert server.is_running is False
    
    def test_get_stats(self):
        """测试获取统计信息"""
        server = FeishuEventServer({
            "host": "127.0.0.1",
            "port": 9000,
            "encrypt_key": "test_key"
        })
        
        def dummy_handler(event):
            pass
        server.set_message_handler(dummy_handler)
        
        stats = server.get_stats()
        
        assert stats["is_running"] is False
        assert stats["host"] == "127.0.0.1"
        assert stats["port"] == 9000
        assert stats["has_message_handler"] is True
        assert stats["has_encrypt_key"] is True


class TestFactoryFunction:
    """测试工厂函数"""
    
    def test_create_event_server_default(self):
        """测试使用默认配置创建服务器"""
        server = create_event_server()
        
        assert isinstance(server, FeishuEventServer)
        assert server.host == "0.0.0.0"
        assert server.port == 8080
    
    def test_create_event_server_with_config(self):
        """测试使用配置创建服务器"""
        server = create_event_server({
            "host": "localhost",
            "port": 3000,
            "verification_token": "factory_token"
        })
        
        assert server.host == "localhost"
        assert server.port == 3000
        assert server.verification_token == "factory_token"


class TestUnhandledEvents:
    """测试未处理的事件类型"""
    
    def test_unknown_event_type(self):
        """测试未知事件类型"""
        server = FeishuEventServer()
        
        data = {
            "header": {"event_type": "unknown.event.type"},
            "event": {}
        }
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data=json.dumps(data),
                content_type="application/json"
            )
            
            # 应该返回成功，不报错
            assert response.status_code == 200
            result = response.get_json()
            assert result["code"] == 0


class TestMessageParsing:
    """测试消息解析功能
    
    Requirements: 2.1, 2.2, 2.3
    """
    
    def test_parse_json_text_content(self):
        """测试解析 JSON 格式的文本消息"""
        server = FeishuEventServer()
        
        event_data = {
            "event": {
                "message": {
                    "chat_type": "group",
                    "content": '{"text": "Hello World"}',
                    "message_type": "text",
                    "mentions": []
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        assert result["text"] == "Hello World"
        assert result["question"] == "Hello World"
    
    def test_detect_mention_in_group_chat(self):
        """测试群聊中检测 @mention"""
        server = FeishuEventServer()
        
        event_data = {
            "event": {
                "message": {
                    "chat_type": "group",
                    "content": '{"text": "@_user_1 什么是RAG？"}',
                    "message_type": "text",
                    "mentions": [{"key": "@_user_1", "name": "Bot", "id": {"open_id": "bot123"}}]
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        assert result["is_mentioned"] is True
        assert result["is_private"] is False
        assert result["should_respond"] is True
        assert result["question"] == "什么是RAG？"
    
    def test_detect_private_chat(self):
        """测试检测私聊消息"""
        server = FeishuEventServer()
        
        event_data = {
            "event": {
                "message": {
                    "chat_type": "p2p",
                    "content": '{"text": "什么是向量数据库？"}',
                    "message_type": "text",
                    "mentions": []
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        assert result["is_private"] is True
        assert result["is_mentioned"] is False
        assert result["should_respond"] is True
        assert result["question"] == "什么是向量数据库？"
    
    def test_group_chat_without_mention(self):
        """测试群聊中没有 @mention 时不应响应"""
        server = FeishuEventServer()
        
        event_data = {
            "event": {
                "message": {
                    "chat_type": "group",
                    "content": '{"text": "这是一条普通消息"}',
                    "message_type": "text",
                    "mentions": []
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        assert result["is_mentioned"] is False
        assert result["is_private"] is False
        assert result["should_respond"] is False
    
    def test_extract_question_removes_mention_placeholder(self):
        """测试提取问题时移除 @mention 占位符"""
        server = FeishuEventServer()
        
        event_data = {
            "event": {
                "message": {
                    "chat_type": "group",
                    "content": '{"text": "@_user_1 @_user_2 请问如何使用？"}',
                    "message_type": "text",
                    "mentions": [
                        {"key": "@_user_1", "name": "Bot1"},
                        {"key": "@_user_2", "name": "Bot2"}
                    ]
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        assert "@_user_" not in result["question"]
        assert "请问如何使用？" in result["question"]
    
    def test_parse_rich_text_content(self):
        """测试解析富文本消息"""
        server = FeishuEventServer()
        
        # 富文本格式: {"content": [[{"tag": "text", "text": "..."}, ...]]}
        rich_content = {
            "content": [
                [
                    {"tag": "at", "user_id": "bot123"},
                    {"tag": "text", "text": " 请帮我查询最新漏洞"}
                ]
            ]
        }
        
        event_data = {
            "event": {
                "message": {
                    "chat_type": "group",
                    "content": json.dumps(rich_content),
                    "message_type": "post",
                    "mentions": [{"key": "@_user_1", "name": "Bot"}]
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        assert "请帮我查询最新漏洞" in result["text"]
        assert result["is_mentioned"] is True
    
    def test_parse_plain_text_content(self):
        """测试解析非 JSON 格式的纯文本"""
        server = FeishuEventServer()
        
        event_data = {
            "event": {
                "message": {
                    "chat_type": "p2p",
                    "content": "这是纯文本消息",
                    "message_type": "text",
                    "mentions": []
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        assert result["text"] == "这是纯文本消息"
        assert result["question"] == "这是纯文本消息"
    
    def test_parse_empty_content(self):
        """测试解析空内容"""
        server = FeishuEventServer()
        
        event_data = {
            "event": {
                "message": {
                    "chat_type": "p2p",
                    "content": "",
                    "message_type": "text",
                    "mentions": []
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        assert result["text"] == ""
        assert result["question"] == ""
    
    def test_detect_mention_by_text_pattern(self):
        """测试通过文本模式检测 @mention（备用方案）"""
        server = FeishuEventServer()
        
        # 即使 mentions 列表为空，但文本中有 @_user_ 模式也应检测到
        event_data = {
            "event": {
                "message": {
                    "chat_type": "group",
                    "content": '{"text": "@_user_1 测试问题"}',
                    "message_type": "text",
                    "mentions": []  # 空的 mentions 列表
                },
                "sender": {"sender_id": {"open_id": "user123"}}
            }
        }
        
        result = server.handle_message(event_data)
        
        # 通过文本模式检测到 @mention
        assert result["is_mentioned"] is True
        assert result["should_respond"] is True
    
    def test_handle_message_with_simplified_format(self):
        """测试处理简化格式的消息数据"""
        server = FeishuEventServer()
        
        # 直接传入简化格式（已经提取过的 event_info）
        event_data = {
            "chat_type": "p2p",
            "content": '{"text": "简化格式测试"}',
            "message_type": "text",
            "mentions": [],
            "sender_id": "user123"
        }
        
        result = server.handle_message(event_data)
        
        assert result["is_private"] is True
        assert result["text"] == "简化格式测试"
        assert result["should_respond"] is True
    
    def test_handle_message_legacy_format(self):
        """测试处理旧版格式的消息"""
        server = FeishuEventServer()
        
        event_data = {
            "event": {
                "type": "message",
                "message_id": "legacy_msg",
                "open_chat_id": "legacy_chat",
                "chat_type": "private",
                "text": "旧版格式消息",
                "msg_type": "text",
                "open_id": "legacy_user"
            }
        }
        
        result = server.handle_message(event_data)
        
        assert result["message_id"] == "legacy_msg"
        assert result["chat_id"] == "legacy_chat"
        assert result["text"] == "旧版格式消息"


class TestMessageEventWithParsing:
    """测试消息事件处理与解析的集成
    
    Requirements: 2.1, 2.2, 2.3
    """
    
    def test_message_event_includes_parsed_fields(self):
        """测试消息事件处理后包含解析字段"""
        server = FeishuEventServer()
        
        received_events = []
        def handler(event):
            received_events.append(event)
        
        server.set_message_handler(handler)
        
        data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "message": {
                    "message_id": "msg_test",
                    "chat_id": "chat_test",
                    "chat_type": "group",
                    "content": '{"text": "@_user_1 这是测试问题"}',
                    "message_type": "text",
                    "mentions": [{"key": "@_user_1", "name": "TestBot"}]
                },
                "sender": {"sender_id": {"open_id": "sender_test"}}
            }
        }
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data=json.dumps(data),
                content_type="application/json"
            )
            
            assert response.status_code == 200
            
            import time
            time.sleep(0.1)
            
            assert len(received_events) == 1
            event = received_events[0]
            
            # 验证解析后的字段
            assert event["is_mentioned"] is True
            assert event["is_private"] is False
            assert event["should_respond"] is True
            assert "这是测试问题" in event["question"]
            assert "@_user_" not in event["question"]
    
    def test_private_message_event_should_respond(self):
        """测试私聊消息事件应该响应"""
        server = FeishuEventServer()
        
        received_events = []
        def handler(event):
            received_events.append(event)
        
        server.set_message_handler(handler)
        
        data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "message": {
                    "message_id": "msg_private",
                    "chat_id": "chat_private",
                    "chat_type": "p2p",
                    "content": '{"text": "私聊问题"}',
                    "message_type": "text",
                    "mentions": []
                },
                "sender": {"sender_id": {"open_id": "sender_private"}}
            }
        }
        
        with server.app.test_client() as client:
            response = client.post(
                "/webhook/event",
                data=json.dumps(data),
                content_type="application/json"
            )
            
            assert response.status_code == 200
            
            import time
            time.sleep(0.1)
            
            assert len(received_events) == 1
            event = received_events[0]
            
            assert event["is_private"] is True
            assert event["should_respond"] is True
            assert event["question"] == "私聊问题"
