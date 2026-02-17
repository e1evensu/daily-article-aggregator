#!/usr/bin/env python3
"""测试发送带反馈按钮的消息"""
import os

# 加载环境变量
env_path = '/opt/daily-article-aggregator/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v = line.split('=',1)
                os.environ.setdefault(k,v)

from src.bots.feishu_bot import FeishuAppBot

app_id = os.getenv('FEISHU_APP_ID')
app_secret = os.getenv('FEISHU_APP_SECRET')
chat_id = os.getenv('FEISHU_CHAT_ID')

print(f"初始化 FeishuAppBot: app_id={app_id[:10]}..., chat_id={chat_id}")

# 创建机器人
bot = FeishuAppBot(app_id, app_secret)

# 构建带反馈按钮的卡片消息
card = {
    "header": {
        "title": {
            "tag": "plain_text",
            "content": "🔥 今日技术资讯汇总"
        },
        "template": "blue"
    },
    "elements": [
        {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": "📰 推荐文章："
            }
        },
        {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": "• 测试文章1 - AI 相关"
            }
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "👍 有用"
                    },
                    "type": "primary",
                    "value": {"action": "feedback", "rating": "useful", "article_id": "test_1"}
                },
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "👎 没用"
                    },
                    "type": "default",
                    "value": {"action": "feedback", "rating": "not_useful", "article_id": "test_1"}
                },
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "⭐ 收藏"
                    },
                    "type": "default",
                    "value": {"action": "feedback", "rating": "bookmark", "article_id": "test_1"}
                }
            ]
        }
    ]
}

# 发送消息
print("发送消息到群聊...")
result = bot.send_interactive_card(card, chat_id)
print(f"发送结果: {result}")
