#!/usr/bin/env python3
"""测试卡片回调处理"""
import os
import sys
sys.path.insert(0, '/opt/daily-article-aggregator')

# 加载环境变量
env_path = '/opt/daily-article-aggregator/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v = line.split('=',1)
                os.environ.setdefault(k,v)

# 模拟卡片回调数据
test_data = {
    "schema": "2.0",
    "token": "test_token",
    "type": "interactive",
    "event": {
        "type": "card.action.trigger",
        "action": {
            "tag": "button",
            "value": {
                "action": "feedback",
                "rating": "useful",
                "article_id": "test_article_123"
            }
        },
        "operator": {
            "open_id": "ou_test123"
        }
    }
}

print("测试卡片回调处理...")
print(f"输入数据: {test_data}")

try:
    from src.qa.event_server import FeishuEventHandler

    # 创建处理器
    handler = FeishuEventHandler(
        encryption_key=os.getenv('FEISHU_ENCRYPT_KEY'),
        verification_token=os.getenv('FEISHU_VERIFICATION_TOKEN'),
        feedback_handler=None,
        qa_engine=None
    )

    # 调用处理方法
    result, status = handler._handle_card_action(test_data)
    print(f"\n处理结果:")
    print(f"  状态码: {status}")
    print(f"  响应: {result}")

except Exception as e:
    print(f"\n❌ 处理失败: {e}")
    import traceback
    traceback.print_exc()
