"""测试本次修复的功能"""

from openai import OpenAI
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


def test_siliconflow_api():
    """测试 SiliconFlow API"""
    print("测试 1: SiliconFlow API...")
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'),
        base_url='https://api.siliconflow.cn/v1'
    )
    resp = client.chat.completions.create(
        model='deepseek-ai/DeepSeek-V3',
        messages=[{'role': 'user', 'content': 'hello'}],
        max_tokens=10
    )
    print('✅ API 测试成功:', resp.choices[0].message.content)


def test_topic_cluster():
    """测试 TopicCluster 参数修复"""
    print("\n测试 2: TopicCluster...")
    from src.aggregation.models import TopicCluster
    cluster = TopicCluster(
        id='test_123',
        topic_keywords=['AI', '安全'],
        articles=[]
    )
    print('✅ TopicCluster 测试成功, id:', cluster.id)


def test_feedback_handler():
    """测试 FeedbackHandler"""
    print("\n测试 3: FeedbackHandler...")
    from src.feedback.feishu_feedback import FeishuFeedbackHandler
    from src.feedback.feedback_handler import FeedbackHandler
    fh = FeedbackHandler()
    handler = FeishuFeedbackHandler(fh)
    print('✅ FeedbackHandler 导入成功')


def test_bitable_fields():
    """测试多维表格字段"""
    print("\n测试 4: 多维表格字段...")
    from src.bots.feishu_bitable import FeishuBitable
    fields = [f["field_name"] for f in FeishuBitable.ARTICLE_FIELDS]
    print('✅ 字段列表:', fields)
    assert "云文档" in fields, "缺少云文档字段"
    assert "用户反馈" in fields, "缺少用户反馈字段"
    print('✅ 云文档和用户反馈字段已添加')


if __name__ == "__main__":
    test_siliconflow_api()
    test_topic_cluster()
    test_feedback_handler()
    test_bitable_fields()
    print("\n🎉 所有测试通过!")
