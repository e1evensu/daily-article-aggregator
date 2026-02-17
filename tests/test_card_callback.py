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
    # 直接测试回调处理逻辑
    event = test_data.get("event", test_data)
    action = event.get("action", {})
    value = action.get("value", {})

    print(f"\n解析结果:")
    print(f"  action: {value.get('action')}")
    print(f"  rating: {value.get('rating')}")
    print(f"  article_id: {value.get('article_id')}")

    if value.get("action") == "feedback":
        print("\n✅ 回调数据解析成功，可以处理反馈")
    else:
        print("\n⚠️ 不是反馈动作")

except Exception as e:
    print(f"\n❌ 处理失败: {e}")
    import traceback
    traceback.print_exc()
