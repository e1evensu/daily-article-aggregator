#!/usr/bin/env python3
"""测试飞书配置"""
import os

# 直接读取 .env 文件
env_path = '/opt/daily-article-aggregator/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v = line.split('=',1)
                os.environ.setdefault(k,v)

# 检查配置
app_id = os.getenv('FEISHU_APP_ID')
app_secret = os.getenv('FEISHU_APP_SECRET')
chat_id = os.getenv('FEISHU_CHAT_ID')
webhook_url = os.getenv('FEISHU_WEBHOOK_URL')

print('配置检查:')
print(f'  APP_ID: {app_id[:10]}...' if app_id else '  APP_ID: None')
print(f'  CHAT_ID: {chat_id}')
print(f'  WEBHOOK: {webhook_url[:30]}...' if webhook_url else '  WEBHOOK: None')
print()

if app_id and app_secret and chat_id:
    print('✅ 将使用应用中心 API')
elif webhook_url:
    print('⚠️ 将使用 webhook (无应用中心配置)')
else:
    print('❌ 未配置飞书')
