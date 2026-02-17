"""
QAEngine 属性测试 (Property-Based Tests)

使用 Hypothesis 进行属性测试，验证 QAEngine 的正确性属性。

Feature: knowledge-qa-bot
Property 6: Source Attribution in Answers
**Validates: Requirements 2.5**

Property 6 states:
- For any answer generated from retrieved documents, the response SHALL include 
  source URLs for all documents used in generating the answer.
- Source URLs SHALL be valid and match the original document metadata.
- No duplicate sources in response.
- Sources are properly deduplicated by URL.
"""

from typing import Any
from unittest.mock import Mock, MagicMock

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume

from src.qa.qa_engine import QAEngine
from src.qa.knowledge_base import KnowledgeBase
from src.qa.context_manager import ContextManager
from src.qa.query_processor import QueryProcessor, ParsedQuery
from src.qa.config import QAEngineConfig
from src.qa.models import QAResponse
from src.analyzers.ai_analyzer import AIAnalyzer


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# Simple alphanumeric text strategy to avoid slow filtering
alphanumeric_text = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '),
    min_size=5,
    max_size=100
).map(lambda x: x.strip() or 'default query')

# URL strategy - generate valid URLs
url_strategy = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789'),
    min_size=5,
    max_size=20
).map(lambda x: f'https://example.com/{x.strip() or "article"}')

# Source type strategy
source_type_strategy = st.sampled_from(['arxiv', 'rss', 'nvd', 'kev', 'blog'])

# Score strategy - relevance scores between 0 and 1
score_strategy = st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False)


def retrieved_doc_strategy():
    """
    生成检索文档的 Hypothesis 策略
    
    生成符合 KnowledgeBase.search() 返回格式的文档字典。
    """
    return st.fixed_dictionaries({
        'doc_id': st.text(
            alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789_'),
            min_size=3,
            max_size=20
        ).map(lambda x: x.strip() or 'doc_1'),
        'content': alphanumeric_text,
        'score': score_strategy,
        'metadata': st.fixed_dictionaries({
            'title': alphanumeric_text,
            'url': url_strategy,
            'source_type': source_type_strategy,
            'article_id': st.integers(min_value=1, max_value=10000),
            'chunk_index': st.integers(min_value=0, max_value=10)
        })
    })


def retrieved_docs_list_strategy(min_size: int = 1, max_size: int = 5):
    """
    生成检索文档列表的策略
    
    确保每个文档有唯一的 URL。
    """
    return st.lists(
        retrieved_doc_strategy(),
        min_size=min_size,
        max_size=max_size
    ).map(lambda docs: _ensure_unique_urls(docs))


def _ensure_unique_urls(docs: list[dict]) -> list[dict]:
    """确保文档列表中的 URL 唯一"""
    seen_urls = set()
    unique_docs = []
    for i, doc in enumerate(docs):
        url = doc['metadata']['url']
        if url in seen_urls:
            # 修改 URL 使其唯一
            new_url = f"{url}_{i}"
            doc = dict(doc)
            doc['metadata'] = dict(doc['metadata'])
            doc['metadata']['url'] = new_url
        seen_urls.add(doc['metadata']['url'])
        unique_docs.append(doc)
    return unique_docs


# =============================================================================
# Mock Fixtures
# =============================================================================

class MockKnowledgeBase:
    """Mock KnowledgeBase for property-based testing"""
    
    def __init__(self, docs_to_return: list[dict] | None = None):
        self.docs_to_return = docs_to_return or []
        self.search_calls = []
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        filters: dict | None = None
    ) -> list[dict]:
        """Return configured documents"""
        self.search_calls.append({
            'query': query,
            'n_results': n_results,
            'filters': filters
        })
        return self.docs_to_return[:n_results]
    
    def get_stats(self) -> dict:
        return {'total_documents': len(self.docs_to_return)}


class MockAIAnalyzer:
    """Mock AIAnalyzer for property-based testing"""
    
    def __init__(self, answer: str = "This is a generated answer."):
        self.answer = answer
        self.call_count = 0
    
    def _call_api(self, user_prompt: str, system_prompt: str) -> str:
        """Return configured answer"""
        self.call_count += 1
        return self.answer


# =============================================================================
# Property 6: Source Attribution in Answers
# =============================================================================

class TestSourceAttributionInAnswers:
    """
    Property 6: Source Attribution in Answers
    
    For any QA response generated from retrieved documents, the response SHALL 
    include source URLs for all documents used in generating the answer.
    
    Feature: knowledge-qa-bot, Property 6: Source Attribution in Answers
    **Validates: Requirements 2.5**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        retrieved_docs=retrieved_docs_list_strategy(min_size=1, max_size=5),
        query=alphanumeric_text
    )
    def test_all_retrieved_docs_with_valid_urls_appear_in_sources(
        self, retrieved_docs, query
    ):
        """
        Feature: knowledge-qa-bot, Property 6: All retrieved documents with valid URLs appear in sources
        **Validates: Requirements 2.5**
        
        Property: For any answer generated from retrieved documents, the response 
        SHALL include source URLs for all documents used in generating the answer.
        """
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer="Generated answer based on sources.")
        
        # Create QAEngine with low min_relevance_score to ensure docs pass filter
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,  # Accept all docs
            answer_max_length=2000
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Collect expected URLs from retrieved docs (only non-empty URLs)
        expected_urls = {
            doc['metadata']['url'] 
            for doc in retrieved_docs 
            if doc['metadata'].get('url')
        }
        
        # Collect actual URLs from response sources
        actual_urls = {
            source['url'] 
            for source in response.sources 
            if source.get('url')
        }
        
        # Verify all expected URLs are in response sources
        assert expected_urls == actual_urls, \
            f"Expected URLs {expected_urls} but got {actual_urls}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        retrieved_docs=retrieved_docs_list_strategy(min_size=1, max_size=5),
        query=alphanumeric_text
    )
    def test_source_urls_match_original_document_metadata(
        self, retrieved_docs, query
    ):
        """
        Feature: knowledge-qa-bot, Property 6: Source URLs match original document metadata
        **Validates: Requirements 2.5**
        
        Property: Source URLs SHALL be valid and match the original document metadata.
        """
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer="Generated answer.")
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=2000
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Build a map of URL -> metadata from original docs
        original_metadata_by_url = {
            doc['metadata']['url']: doc['metadata']
            for doc in retrieved_docs
            if doc['metadata'].get('url')
        }
        
        # Verify each source in response matches original metadata
        for source in response.sources:
            url = source.get('url')
            if url and url in original_metadata_by_url:
                original = original_metadata_by_url[url]
                
                # Verify title matches
                assert source['title'] == original['title'], \
                    f"Source title '{source['title']}' doesn't match original '{original['title']}'"
                
                # Verify source_type matches
                assert source['source_type'] == original['source_type'], \
                    f"Source type '{source['source_type']}' doesn't match original '{original['source_type']}'"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        retrieved_docs=retrieved_docs_list_strategy(min_size=1, max_size=5),
        query=alphanumeric_text
    )
    def test_no_duplicate_sources_in_response(self, retrieved_docs, query):
        """
        Feature: knowledge-qa-bot, Property 6: No duplicate sources in response
        **Validates: Requirements 2.5**
        
        Property: No duplicate sources in response. Sources are properly 
        deduplicated by URL.
        """
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer="Generated answer.")
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=2000
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Collect all URLs from sources
        urls = [source.get('url') for source in response.sources if source.get('url')]
        
        # Verify no duplicates
        assert len(urls) == len(set(urls)), \
            f"Duplicate URLs found in sources: {urls}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(query=alphanumeric_text)
    def test_sources_greater_than_zero_when_relevant_docs_exist(self, query):
        """
        Feature: knowledge-qa-bot, Property 6: Sources > 0 when relevant docs exist
        **Validates: Requirements 2.5**
        
        Property: The number of sources SHALL be greater than zero when relevant 
        documents exist.
        """
        # Create docs with valid URLs
        retrieved_docs = [
            {
                'doc_id': 'doc_1',
                'content': 'Test content about the topic.',
                'score': 0.9,
                'metadata': {
                    'title': 'Test Article',
                    'url': 'https://example.com/test1',
                    'source_type': 'arxiv',
                    'article_id': 1,
                    'chunk_index': 0
                }
            }
        ]
        
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer="Generated answer.")
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=2000
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Verify sources > 0
        assert len(response.sources) > 0, \
            "Sources should be greater than zero when relevant documents exist"


class TestSourceDeduplication:
    """
    Property 6: Source Deduplication
    
    Sources are properly deduplicated by URL.
    
    Feature: knowledge-qa-bot, Property 6: Source deduplication
    **Validates: Requirements 2.5**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_docs=st.integers(min_value=2, max_value=5),
        query=alphanumeric_text
    )
    def test_duplicate_urls_are_deduplicated(self, num_docs, query):
        """
        Feature: knowledge-qa-bot, Property 6: Duplicate URLs are deduplicated
        **Validates: Requirements 2.5**
        
        Property: When multiple documents have the same URL (e.g., different 
        chunks from the same article), only one source entry SHALL appear.
        """
        # Create docs with the SAME URL (simulating chunks from same article)
        shared_url = 'https://example.com/shared-article'
        retrieved_docs = [
            {
                'doc_id': f'doc_{i}',
                'content': f'Content chunk {i}',
                'score': 0.9 - (i * 0.05),
                'metadata': {
                    'title': 'Shared Article Title',
                    'url': shared_url,  # Same URL for all
                    'source_type': 'arxiv',
                    'article_id': 1,
                    'chunk_index': i
                }
            }
            for i in range(num_docs)
        ]
        
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer="Generated answer.")
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=2000
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Verify only ONE source with the shared URL
        urls_in_sources = [s['url'] for s in response.sources]
        assert urls_in_sources.count(shared_url) == 1, \
            f"Expected exactly 1 source with URL '{shared_url}', got {urls_in_sources.count(shared_url)}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(query=alphanumeric_text)
    def test_empty_urls_not_included_in_sources(self, query):
        """
        Feature: knowledge-qa-bot, Property 6: Empty URLs not included
        **Validates: Requirements 2.5**
        
        Property: Documents with empty URLs SHALL NOT appear in sources.
        """
        # Create docs with some empty URLs
        retrieved_docs = [
            {
                'doc_id': 'doc_1',
                'content': 'Content with valid URL',
                'score': 0.9,
                'metadata': {
                    'title': 'Valid Article',
                    'url': 'https://example.com/valid',
                    'source_type': 'arxiv',
                    'article_id': 1,
                    'chunk_index': 0
                }
            },
            {
                'doc_id': 'doc_2',
                'content': 'Content with empty URL',
                'score': 0.85,
                'metadata': {
                    'title': 'No URL Article',
                    'url': '',  # Empty URL
                    'source_type': 'rss',
                    'article_id': 2,
                    'chunk_index': 0
                }
            }
        ]
        
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer="Generated answer.")
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=2000
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Verify no empty URLs in sources
        for source in response.sources:
            assert source.get('url'), \
                f"Source with empty URL should not be included: {source}"
        
        # Verify only the valid URL is present
        urls = [s['url'] for s in response.sources]
        assert 'https://example.com/valid' in urls, \
            "Valid URL should be in sources"
        assert '' not in urls, \
            "Empty URL should not be in sources"


class TestSourceMetadataPreservation:
    """
    Property 6: Source Metadata Preservation
    
    Source metadata (title, url, source_type, score) SHALL be preserved correctly.
    
    Feature: knowledge-qa-bot, Property 6: Source metadata preservation
    **Validates: Requirements 2.5**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        retrieved_docs=retrieved_docs_list_strategy(min_size=1, max_size=3),
        query=alphanumeric_text
    )
    def test_source_score_preserved(self, retrieved_docs, query):
        """
        Feature: knowledge-qa-bot, Property 6: Source score preserved
        **Validates: Requirements 2.5**
        
        Property: The relevance score from retrieved documents SHALL be 
        preserved in the source metadata.
        """
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer="Generated answer.")
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=2000
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Build map of URL -> score from original docs
        original_scores_by_url = {
            doc['metadata']['url']: doc['score']
            for doc in retrieved_docs
            if doc['metadata'].get('url')
        }
        
        # Verify scores are preserved
        for source in response.sources:
            url = source.get('url')
            if url and url in original_scores_by_url:
                expected_score = original_scores_by_url[url]
                actual_score = source.get('score', 0)
                assert abs(actual_score - expected_score) < 0.001, \
                    f"Score mismatch for {url}: expected {expected_score}, got {actual_score}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        retrieved_docs=retrieved_docs_list_strategy(min_size=1, max_size=3),
        query=alphanumeric_text
    )
    def test_all_source_fields_present(self, retrieved_docs, query):
        """
        Feature: knowledge-qa-bot, Property 6: All source fields present
        **Validates: Requirements 2.5**
        
        Property: Each source in the response SHALL have title, url, 
        source_type, and score fields.
        """
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer="Generated answer.")
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=2000
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Verify all required fields are present in each source
        required_fields = ['title', 'url', 'source_type', 'score']
        for source in response.sources:
            for field in required_fields:
                assert field in source, \
                    f"Source missing required field '{field}': {source}"



# =============================================================================
# Property 8: Answer Length Constraint
# =============================================================================

class TestAnswerLengthConstraint:
    """
    Property 8: Answer Length Constraint
    
    For any generated answer, the length SHALL NOT exceed the configured 
    max_answer_length. If truncation is needed, it SHALL occur at a sentence 
    boundary when possible.
    
    Feature: knowledge-qa-bot, Property 8: Answer Length Constraint
    **Validates: Requirements 5.3**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        answer_length=st.integers(min_value=100, max_value=5000),
        max_length=st.integers(min_value=50, max_value=500),
        query=alphanumeric_text
    )
    def test_answer_length_never_exceeds_max_length_plus_truncation_message(
        self, answer_length, max_length, query
    ):
        """
        Feature: knowledge-qa-bot, Property 8: Answer length never exceeds max_answer_length (plus truncation message)
        **Validates: Requirements 5.3**
        
        Property: For any generated answer, the length SHALL NOT exceed the 
        configured max_answer_length. The truncation message is allowed as 
        additional content.
        """
        # Generate a long answer
        long_answer = "这是一个测试回答。" * (answer_length // 10 + 1)
        long_answer = long_answer[:answer_length]
        
        # Create docs that will trigger answer generation
        retrieved_docs = [
            {
                'doc_id': 'doc_1',
                'content': 'Test content about the topic.',
                'score': 0.9,
                'metadata': {
                    'title': 'Test Article',
                    'url': 'https://example.com/test1',
                    'source_type': 'arxiv',
                    'article_id': 1,
                    'chunk_index': 0
                }
            }
        ]
        
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer=long_answer)
        
        # Create QAEngine with specific max_answer_length
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=max_length
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # The truncation message
        truncation_message = "\n\n[回答已截断，如需更多信息请继续提问]"
        
        # Calculate the maximum allowed length (max_length + truncation message)
        max_allowed_length = max_length + len(truncation_message)
        
        # Verify answer length does not exceed max_length + truncation message
        assert len(response.answer) <= max_allowed_length, \
            f"Answer length {len(response.answer)} exceeds max allowed {max_allowed_length}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.filter_too_much]
    )
    @given(
        max_length=st.integers(min_value=30, max_value=80),
        query=alphanumeric_text
    )
    def test_truncation_occurs_at_sentence_boundary_when_possible(
        self, max_length, query
    ):
        """
        Feature: knowledge-qa-bot, Property 8: Truncation occurs at sentence boundaries when possible
        **Validates: Requirements 5.3**
        
        Property: If truncation is needed, it SHALL occur at a sentence boundary 
        when possible.
        """
        # Create an answer with clear sentence boundaries
        # Total length is about 90 characters (9 chars per sentence * 10 sentences)
        sentences = [
            "这是第一个句子。",
            "这是第二个句子。",
            "这是第三个句子。",
            "这是第四个句子。",
            "这是第五个句子。",
            "这是第六个句子。",
            "这是第七个句子。",
            "这是第八个句子。",
            "这是第九个句子。",
            "这是第十个句子。",
        ]
        long_answer = "".join(sentences)  # ~90 characters
        
        # max_length is 30-80, so long_answer (90 chars) will always be longer
        
        # Create docs
        retrieved_docs = [
            {
                'doc_id': 'doc_1',
                'content': 'Test content.',
                'score': 0.9,
                'metadata': {
                    'title': 'Test Article',
                    'url': 'https://example.com/test1',
                    'source_type': 'arxiv',
                    'article_id': 1,
                    'chunk_index': 0
                }
            }
        ]
        
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer=long_answer)
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=max_length
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # Remove the truncation message to check the actual content
        truncation_message = "\n\n[回答已截断，如需更多信息请继续提问]"
        answer_content = response.answer
        if answer_content.endswith(truncation_message):
            answer_content = answer_content[:-len(truncation_message)]
        
        # Check if truncation occurred at a sentence boundary
        # Sentence endings: 。！？.!?\n
        sentence_endings = ['。', '！', '？', '.', '!', '?', '\n']
        
        # If the answer was truncated (shorter than original), 
        # it should end with a sentence ending character
        if len(answer_content) < len(long_answer):
            ends_at_sentence = any(
                answer_content.endswith(ending) 
                for ending in sentence_endings
            )
            # The truncation should occur at sentence boundary when possible
            # (at least 70% of max_length should be preserved)
            if len(answer_content) >= max_length * 0.7:
                assert ends_at_sentence, \
                    f"Truncated answer should end at sentence boundary: '{answer_content[-20:]}'"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        max_length=st.integers(min_value=50, max_value=200),
        query=alphanumeric_text
    )
    def test_truncation_message_added_when_answer_is_truncated(
        self, max_length, query
    ):
        """
        Feature: knowledge-qa-bot, Property 8: Truncation message is added when answer is truncated
        **Validates: Requirements 5.3**
        
        Property: When an answer is truncated, a truncation indicator message 
        SHALL be appended.
        """
        # Create an answer that is definitely longer than max_length
        long_answer = "这是一个很长的测试回答内容。" * 50
        
        # Ensure the answer is longer than max_length
        assume(len(long_answer) > max_length)
        
        # Create docs
        retrieved_docs = [
            {
                'doc_id': 'doc_1',
                'content': 'Test content.',
                'score': 0.9,
                'metadata': {
                    'title': 'Test Article',
                    'url': 'https://example.com/test1',
                    'source_type': 'arxiv',
                    'article_id': 1,
                    'chunk_index': 0
                }
            }
        ]
        
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer=long_answer)
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=max_length
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # The truncation message
        truncation_message = "[回答已截断，如需更多信息请继续提问]"
        
        # Verify truncation message is present
        assert truncation_message in response.answer, \
            f"Truncation message should be present when answer is truncated. Answer: '{response.answer[-100:]}'"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        max_length=st.integers(min_value=500, max_value=2000),
        query=alphanumeric_text
    )
    def test_short_answer_not_truncated(self, max_length, query):
        """
        Feature: knowledge-qa-bot, Property 8: Short answers are not truncated
        **Validates: Requirements 5.3**
        
        Property: Answers shorter than max_answer_length SHALL NOT be truncated 
        and SHALL NOT have truncation message.
        """
        # Create a short answer
        short_answer = "这是一个简短的回答。"
        
        # Ensure the answer is shorter than max_length
        assume(len(short_answer) < max_length)
        
        # Create docs
        retrieved_docs = [
            {
                'doc_id': 'doc_1',
                'content': 'Test content.',
                'score': 0.9,
                'metadata': {
                    'title': 'Test Article',
                    'url': 'https://example.com/test1',
                    'source_type': 'arxiv',
                    'article_id': 1,
                    'chunk_index': 0
                }
            }
        ]
        
        # Setup mocks
        mock_kb = MockKnowledgeBase(docs_to_return=retrieved_docs)
        mock_cm = ContextManager(max_history=5, ttl_minutes=30)
        mock_qp = QueryProcessor()
        mock_ai = MockAIAnalyzer(answer=short_answer)
        
        config = QAEngineConfig(
            max_retrieved_docs=10,
            min_relevance_score=0.0,
            answer_max_length=max_length
        )
        engine = QAEngine(mock_kb, mock_cm, mock_qp, mock_ai, config=config)
        
        # Process query
        response = engine.process_query(query=query, user_id="test_user")
        
        # The truncation message
        truncation_message = "[回答已截断，如需更多信息请继续提问]"
        
        # Verify answer is not truncated
        assert response.answer == short_answer, \
            f"Short answer should not be modified. Expected: '{short_answer}', Got: '{response.answer}'"
        
        # Verify truncation message is NOT present
        assert truncation_message not in response.answer, \
            "Truncation message should not be present for short answers"
