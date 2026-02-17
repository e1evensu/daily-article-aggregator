"""
测试知识库检索
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.qa.knowledge_base import KnowledgeBase
from src.qa.embedding_service import EmbeddingService
from src.qa.config import QAConfig
import yaml


def test_knowledge_base_retrieve():
    with open('config.yaml') as f:
        config = yaml.safe_load(f)

    kb_config = config.get('knowledge_qa', {}).get('chroma', {})
    kb = KnowledgeBase(kb_config)

    embedding_config = config.get('knowledge_qa', {}).get('embedding', {})
    es = EmbeddingService(embedding_config)
    kb.set_embedding_service(es)

    stats = kb.get_stats()
    print('知识库统计:', stats)

    results = kb.search('先知 补天', n_results=5)
    print('检索结果:', results)


if __name__ == '__main__':
    test_knowledge_base_retrieve()
