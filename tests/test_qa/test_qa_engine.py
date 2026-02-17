"""
QAEngine 单元测试

测试 RAG 问答引擎的核心功能。

Requirements:
    - 3.1: 使用 RAG（检索增强生成）架构
    - 3.3: 使用 LLM 生成综合回答
    - 2.5: 回答中包含来源链接
    - 3.5: 无相关内容时明确告知用户
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.qa.qa_engine import QAEngine, DEFAULT_RAG_SYSTEM_PROMPT
from src.qa.knowledge_base import KnowledgeBase
from src.qa.context_manager import ContextManager
from src.qa.query_processor import QueryProcessor, ParsedQuery
from src.qa.config import QAEngineConfig
from src.qa.models import QAResponse, ERROR_CODES
from src.analyzers.ai_analyzer import AIAnalyzer


class TestQAEngineInit:
    """测试 QAEngine 初始化"""
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        # 创建 mock 对象
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        
        engine = QAEngine(kb, cm, qp, ai)
        
        assert engine.knowledge_base is kb
        assert engine.context_manager is cm
        assert engine.query_processor is qp
        assert engine.ai_analyzer is ai
        assert engine.config.max_retrieved_docs == 5
        assert engine.config.min_relevance_score == 0.5
        assert engine.config.answer_max_length == 1000
    
    def test_init_with_custom_config_dict(self):
        """测试使用自定义配置字典初始化"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        
        config = {
            'max_retrieved_docs': 10,
            'min_relevance_score': 0.7,
            'answer_max_length': 2000
        }
        
        engine = QAEngine(kb, cm, qp, ai, config=config)
        
        assert engine.config.max_retrieved_docs == 10
        assert engine.config.min_relevance_score == 0.7
        assert engine.config.answer_max_length == 2000
    
    def test_init_with_qa_engine_config(self):
        """测试使用 QAEngineConfig 对象初始化"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        
        config = QAEngineConfig(
            max_retrieved_docs=8,
            min_relevance_score=0.6,
            answer_max_length=1500
        )
        
        engine = QAEngine(kb, cm, qp, ai, config=config)
        
        assert engine.config.max_retrieved_docs == 8
        assert engine.config.min_relevance_score == 0.6
        assert engine.config.answer_max_length == 1500


class TestProcessQuery:
    """测试 process_query 方法"""
    
    @pytest.fixture
    def mock_engine(self):
        """创建带有 mock 依赖的 QAEngine"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        
        # 配置 mock 返回值
        qp.parse_query.return_value = ParsedQuery(
            query_type="general",
            keywords=["RAG", "检索"],
            filters={},
            original_query="什么是RAG?"
        )
        qp.build_search_filters.return_value = {}
        
        kb.search.return_value = [
            {
                'doc_id': 'doc1',
                'content': 'RAG是检索增强生成的缩写...',
                'score': 0.85,
                'metadata': {
                    'title': 'RAG介绍',
                    'url': 'https://example.com/rag',
                    'source_type': 'blog'
                }
            }
        ]
        
        cm.get_context.return_value = []
        
        ai._call_api.return_value = "RAG（检索增强生成）是一种结合检索和生成的技术..."
        
        engine = QAEngine(kb, cm, qp, ai)
        return engine
    
    def test_process_query_success(self, mock_engine):
        """测试成功处理查询"""
        response = mock_engine.process_query(
            query="什么是RAG?",
            user_id="user123"
        )
        
        assert isinstance(response, QAResponse)
        assert response.answer != ""
        assert response.query_type == "general"
        assert response.confidence > 0
        
        # 验证调用链
        mock_engine.query_processor.parse_query.assert_called_once_with("什么是RAG?")
        mock_engine.knowledge_base.search.assert_called_once()
        mock_engine.context_manager.get_context.assert_called_once_with("user123")
        mock_engine.context_manager.add_turn.assert_called_once()
    
    def test_process_query_empty_query(self, mock_engine):
        """测试空查询"""
        response = mock_engine.process_query(
            query="",
            user_id="user123"
        )
        
        assert response.answer == ERROR_CODES["INVALID_QUERY"]
        assert response.confidence == 0.0
    
    def test_process_query_whitespace_query(self, mock_engine):
        """测试只有空白字符的查询"""
        response = mock_engine.process_query(
            query="   ",
            user_id="user123"
        )
        
        assert response.answer == ERROR_CODES["INVALID_QUERY"]
        assert response.confidence == 0.0
    
    def test_process_query_no_results(self, mock_engine):
        """测试无检索结果的情况"""
        mock_engine.knowledge_base.search.return_value = []
        
        response = mock_engine.process_query(
            query="一个非常奇怪的问题",
            user_id="user123"
        )
        
        assert "没有找到" in response.answer or "无相关" in response.answer
        assert response.confidence == 0.0
        assert len(response.sources) == 0
    
    def test_process_query_low_relevance_filtered(self, mock_engine):
        """测试低相关性文档被过滤"""
        mock_engine.knowledge_base.search.return_value = [
            {
                'doc_id': 'doc1',
                'content': '不太相关的内容...',
                'score': 0.3,  # 低于默认阈值 0.5
                'metadata': {'title': '标题', 'url': 'https://example.com'}
            }
        ]
        
        response = mock_engine.process_query(
            query="测试问题",
            user_id="user123"
        )
        
        # 所有文档都被过滤，应该返回无结果响应
        assert response.confidence == 0.0
    
    def test_process_query_with_context(self, mock_engine):
        """测试带有对话上下文的查询"""
        mock_engine.context_manager.get_context.return_value = [
            {
                'query': '之前的问题',
                'answer': '之前的回答',
                'timestamp': datetime.now().isoformat(),
                'sources': []
            }
        ]
        
        response = mock_engine.process_query(
            query="继续上面的话题",
            user_id="user123"
        )
        
        assert isinstance(response, QAResponse)
        # 验证上下文被获取
        mock_engine.context_manager.get_context.assert_called_with("user123")


class TestSourceExtraction:
    """测试来源提取功能"""
    
    @pytest.fixture
    def engine(self):
        """创建 QAEngine 实例"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        return QAEngine(kb, cm, qp, ai)
    
    def test_extract_sources_basic(self, engine):
        """测试基本来源提取"""
        docs = [
            {
                'doc_id': 'doc1',
                'content': '内容1',
                'score': 0.9,
                'metadata': {
                    'title': '标题1',
                    'url': 'https://example.com/1',
                    'source_type': 'blog'
                }
            },
            {
                'doc_id': 'doc2',
                'content': '内容2',
                'score': 0.8,
                'metadata': {
                    'title': '标题2',
                    'url': 'https://example.com/2',
                    'source_type': 'arxiv'
                }
            }
        ]
        
        sources = engine._extract_sources(docs)
        
        assert len(sources) == 2
        assert sources[0]['title'] == '标题1'
        assert sources[0]['url'] == 'https://example.com/1'
        assert sources[1]['title'] == '标题2'
    
    def test_extract_sources_deduplication(self, engine):
        """测试来源去重"""
        docs = [
            {
                'doc_id': 'doc1',
                'content': '内容1',
                'score': 0.9,
                'metadata': {
                    'title': '标题1',
                    'url': 'https://example.com/same',
                    'source_type': 'blog'
                }
            },
            {
                'doc_id': 'doc2',
                'content': '内容2',
                'score': 0.8,
                'metadata': {
                    'title': '标题1（重复）',
                    'url': 'https://example.com/same',  # 相同 URL
                    'source_type': 'blog'
                }
            }
        ]
        
        sources = engine._extract_sources(docs)
        
        assert len(sources) == 1  # 去重后只有一个
    
    def test_extract_sources_empty_url(self, engine):
        """测试空 URL 的处理"""
        docs = [
            {
                'doc_id': 'doc1',
                'content': '内容1',
                'score': 0.9,
                'metadata': {
                    'title': '标题1',
                    'url': '',  # 空 URL
                    'source_type': 'blog'
                }
            }
        ]
        
        sources = engine._extract_sources(docs)
        
        assert len(sources) == 0  # 空 URL 不应该被包含


class TestAnswerTruncation:
    """测试回答截断功能"""
    
    @pytest.fixture
    def engine(self):
        """创建 QAEngine 实例"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        
        config = QAEngineConfig(answer_max_length=100)
        return QAEngine(kb, cm, qp, ai, config=config)
    
    def test_truncate_short_answer(self, engine):
        """测试短回答不被截断"""
        short_answer = "这是一个简短的回答。"
        result = engine._truncate_answer(short_answer)
        
        assert result == short_answer
    
    def test_truncate_long_answer(self, engine):
        """测试长回答被截断"""
        long_answer = "这是一个很长的回答。" * 20
        result = engine._truncate_answer(long_answer)
        
        assert len(result) <= engine.config.answer_max_length + 50  # 允许截断提示的额外长度
        assert "[回答已截断" in result
    
    def test_truncate_at_sentence_boundary(self, engine):
        """测试在句子边界处截断"""
        # 构造一个在句子边界处可以截断的回答
        answer = "第一句话。第二句话。第三句话。" + "x" * 100
        result = engine._truncate_answer(answer)
        
        # 应该在某个句号处截断
        assert "。" in result.split("[回答已截断")[0]
    
    def test_truncate_empty_answer(self, engine):
        """测试空回答"""
        result = engine._truncate_answer("")
        assert result == ""
    
    def test_truncate_none_answer(self, engine):
        """测试 None 回答"""
        result = engine._truncate_answer(None)
        assert result == ""


class TestConfidenceCalculation:
    """测试置信度计算"""
    
    @pytest.fixture
    def engine(self):
        """创建 QAEngine 实例"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        return QAEngine(kb, cm, qp, ai)
    
    def test_calculate_confidence_empty_docs(self, engine):
        """测试空文档列表的置信度"""
        confidence = engine._calculate_confidence([])
        assert confidence == 0.0
    
    def test_calculate_confidence_high_scores(self, engine):
        """测试高分文档的置信度"""
        docs = [
            {'score': 0.95},
            {'score': 0.90},
            {'score': 0.85}
        ]
        confidence = engine._calculate_confidence(docs)
        
        assert confidence > 0.5
        assert confidence <= 1.0
    
    def test_calculate_confidence_low_scores(self, engine):
        """测试低分文档的置信度"""
        docs = [
            {'score': 0.3},
            {'score': 0.2}
        ]
        confidence = engine._calculate_confidence(docs)
        
        assert confidence < 0.5
        assert confidence >= 0.0
    
    def test_calculate_confidence_more_docs_higher(self, engine):
        """测试更多文档导致更高置信度"""
        few_docs = [{'score': 0.8}]
        many_docs = [{'score': 0.8}] * 5
        
        conf_few = engine._calculate_confidence(few_docs)
        conf_many = engine._calculate_confidence(many_docs)
        
        # 相同分数下，更多文档应该有更高置信度
        assert conf_many >= conf_few


class TestContextBuilding:
    """测试上下文构建"""
    
    @pytest.fixture
    def engine(self):
        """创建 QAEngine 实例"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        return QAEngine(kb, cm, qp, ai)
    
    def test_build_context_text_with_docs(self, engine):
        """测试有文档时的上下文构建"""
        docs = [
            {
                'content': '文档内容1',
                'score': 0.9,
                'metadata': {
                    'title': '标题1',
                    'url': 'https://example.com/1'
                }
            }
        ]
        
        context_text = engine._build_context_text(docs)
        
        assert '标题1' in context_text
        assert '文档内容1' in context_text
        assert 'https://example.com/1' in context_text
        assert '0.90' in context_text  # 相关度分数
    
    def test_build_context_text_empty_docs(self, engine):
        """测试空文档列表的上下文构建"""
        context_text = engine._build_context_text([])
        
        assert "无相关参考资料" in context_text
    
    def test_build_history_text_with_context(self, engine):
        """测试有历史对话时的历史构建"""
        context = [
            {'query': '问题1', 'answer': '回答1'},
            {'query': '问题2', 'answer': '回答2'}
        ]
        
        history_text = engine._build_history_text(context)
        
        assert '问题1' in history_text
        assert '回答1' in history_text
        assert '问题2' in history_text
    
    def test_build_history_text_empty_context(self, engine):
        """测试空历史的历史构建"""
        history_text = engine._build_history_text([])
        
        assert "无历史对话" in history_text
    
    def test_build_history_text_truncates_long_answers(self, engine):
        """测试长回答被截断"""
        context = [
            {'query': '问题', 'answer': 'x' * 500}  # 很长的回答
        ]
        
        history_text = engine._build_history_text(context)
        
        # 回答应该被截断
        assert '...' in history_text


class TestClearUserContext:
    """测试清除用户上下文"""
    
    def test_clear_user_context(self):
        """测试清除用户上下文"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        
        engine = QAEngine(kb, cm, qp, ai)
        engine.clear_user_context("user123")
        
        cm.clear_context.assert_called_once_with("user123")


class TestGetStats:
    """测试获取统计信息"""
    
    def test_get_stats(self):
        """测试获取统计信息"""
        kb = Mock(spec=KnowledgeBase)
        cm = Mock(spec=ContextManager)
        qp = Mock(spec=QueryProcessor)
        ai = Mock(spec=AIAnalyzer)
        
        kb.get_stats.return_value = {'total_documents': 100}
        cm.get_stats.return_value = {'total_users': 5}
        
        engine = QAEngine(kb, cm, qp, ai)
        stats = engine.get_stats()
        
        assert 'knowledge_base' in stats
        assert 'context_manager' in stats
        assert 'config' in stats
        assert stats['knowledge_base']['total_documents'] == 100
        assert stats['context_manager']['total_users'] == 5
