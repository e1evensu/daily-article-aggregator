"""测试飞书推送和反馈功能"""

import os
from pathlib import Path

# 加载环境变量
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

print("测试 1: 测试反馈处理器...")
try:
    from src.feedback.feishu_feedback import FeishuFeedbackHandler
    from src.feedback.feedback_handler import FeedbackHandler
    from src.feedback.models import QuickRating

    fh = FeedbackHandler()
    handler = FeishuFeedbackHandler(fh)

    # 测试识别反馈命令
    assert handler.is_feedback_command("有用") == True
    assert handler.is_feedback_command("没用") == True
    assert handler.is_feedback_command("收藏") == True

    # 测试处理反馈
    article_context = {
        'id': 'test_article_1',
        'url': 'http://example.com/article1',
        'title': '测试文章'
    }
    response = handler.process_feedback("test_user", "有用", article_context)
    print(f"   反馈响应: {response}")
    assert "感谢" in response or "已收藏" in response

    print("✅ 反馈功能测试通过")
except Exception as e:
    print(f"❌ 反馈功能测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试 2: 测试飞书 webhook 推送...")
try:
    import httpx
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if webhook_url:
        # 发送测试消息
        test_msg = {
            "msg_type": "text",
            "content": {"text": "🧪 测试消息 - 推送功能正常"}
        }
        resp = httpx.post(webhook_url, json=test_msg, timeout=10)
        if resp.status_code == 200:
            print("✅ 飞书 webhook 推送测试通过")
        else:
            print(f"❌ 飞书 webhook 推送失败: {resp.status_code} - {resp.text}")
    else:
        print("⚠️ 未配置 FEISHU_WEBHOOK_URL，跳过测试")
except Exception as e:
    print(f"❌ 飞书推送测试失败: {e}")

print("\n测试 3: 测试多维表格连接...")
try:
    from src.bots.feishu_bitable import FeishuBitable
    config = {
        'feishu_bitable': {
            'app_id': os.getenv('FEISHU_APP_ID', ''),
            'app_secret': os.getenv('FEISHU_APP_SECRET', ''),
            'app_token': os.getenv('FEISHU_BITABLE_TOKEN', ''),
            'table_id': os.getenv('FEISHU_TABLE_ID', ''),
        }
    }
    if config['feishu_bitable']['app_id']:
        bitable = FeishuBitable(config['feishu_bitable'])
        print("✅ 多维表格客户端初始化成功")
        print(f"   字段: {[f['field_name'] for f in bitable.ARTICLE_FIELDS]}")
    else:
        print("⚠️ 未配置 FEISHU_APP_ID，跳过测试")
except Exception as e:
    print(f"❌ 多维表格测试失败: {e}")

print("\n🎉 所有测试完成!")
