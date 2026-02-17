"""测试 Synthesis 模型初始化"""

from src.aggregation.models import Synthesis, Article

# 测试 Synthesis 初始化
try:
    s = Synthesis(
        id="test_1",
        cluster_id="cluster_1",
        title="测试标题",
        content="测试内容",
        key_points=["要点1", "要点2"],
        references=[{"title": "文章1", "url": "http://example.com"}],
        generated_at=None
    )
    print("✅ Synthesis 初始化成功")
    print(f"   id: {s.id}")
    print(f"   content: {s.content}")
    print(f"   key_points: {s.key_points}")
except Exception as e:
    print(f"❌ Synthesis 初始化失败: {e}")

# 测试 TopicCluster 初始化
try:
    from src.aggregation.models import TopicCluster
    cluster = TopicCluster(
        id="test_cluster",
        topic_keywords=["AI", "安全"],
        articles=[]
    )
    print("✅ TopicCluster 初始化成功")
    print(f"   id: {cluster.id}")
    print(f"   topic_keywords: {cluster.topic_keywords}")
except Exception as e:
    print(f"❌ TopicCluster 初始化失败: {e}")

# 测试 Synthesis 生成器
try:
    from src.aggregation.synthesis_generator import SynthesisGenerator
    print("✅ SynthesisGenerator 导入成功")
except Exception as e:
    print(f"❌ SynthesisGenerator 导入失败: {e}")
