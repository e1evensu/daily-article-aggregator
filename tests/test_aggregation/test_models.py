"""
话题聚合系统数据模型属性测试

Property 17: 数据持久化往返
For any TopicCluster 或 Synthesis 对象，保存到数据库后再加载应得到等价的对象。

**Validates: Requirements 6.6**

Feature: topic-aggregation-system, Property 17: 数据持久化往返
"""

import pytest
from datetime import datetime
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.aggregation.models import (
    TopicCluster,
    Synthesis,
    FilterResult,
    PublishResult,
    RSSItem,
)
from src.models import Article


# =============================================================================
# Test Data Generators (Strategies)
# =============================================================================

# Strategy for generating valid source types
source_type_strategy = st.sampled_from(['rss', 'nvd', 'kev', 'dblp', 'blog', 'arxiv', 'huggingface', 'pwc'])

# Strategy for generating valid status values
status_strategy = st.sampled_from(['pending', 'processing', 'completed', 'failed'])

# Strategy for generating safe text (avoiding problematic characters)
safe_text_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Z'),
        blacklist_characters='\x00'
    ),
    min_size=0,
    max_size=200
)

# Strategy for generating non-empty safe text
non_empty_safe_text_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Z'),
        blacklist_characters='\x00'
    ),
    min_size=1,
    max_size=200
)

# Strategy for generating valid URLs
url_strategy = st.from_regex(
    r'https://[a-z]{3,10}\.[a-z]{2,5}/[a-z0-9]{1,20}',
    fullmatch=True
)

# Strategy for generating valid datetime objects
# Using a reasonable range to avoid edge cases with datetime serialization
datetime_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 12, 31)
)

# Strategy for generating keywords
keyword_strategy = st.lists(
    non_empty_safe_text_strategy,
    min_size=0,
    max_size=10
)

# Strategy for generating CVE IDs
cve_id_strategy = st.from_regex(r'CVE-20[0-9]{2}-[0-9]{4,7}', fullmatch=True)

# Strategy for generating Article objects
article_strategy = st.builds(
    Article,
    id=st.one_of(st.none(), st.integers(min_value=1, max_value=1000000)),
    title=non_empty_safe_text_strategy,
    url=url_strategy,
    source=safe_text_strategy,
    source_type=source_type_strategy,
    published_date=st.text(min_size=0, max_size=30),
    fetched_at=st.text(min_size=0, max_size=30),
    content=safe_text_strategy,
    summary=safe_text_strategy,
    zh_summary=safe_text_strategy,
    category=safe_text_strategy,
    is_pushed=st.booleans(),
    pushed_at=st.one_of(st.none(), st.text(min_size=0, max_size=30)),
    priority_score=st.integers(min_value=0, max_value=100),
    push_level=st.integers(min_value=1, max_value=3),
    brief_summary=safe_text_strategy,
    keywords=keyword_strategy,
    cve_id=st.one_of(st.none(), cve_id_strategy),
    cvss_score=st.one_of(st.none(), st.floats(min_value=0.0, max_value=10.0, allow_nan=False)),
    github_stars=st.one_of(st.none(), st.integers(min_value=0, max_value=1000000)),
    ip_asset_count=st.one_of(st.none(), st.integers(min_value=0, max_value=1000000)),
    ai_assessment=st.one_of(st.none(), safe_text_strategy),
    is_filtered=st.booleans(),
    filter_reasons=st.lists(safe_text_strategy, min_size=0, max_size=5),
)

# Strategy for generating similarity matrix keys (tuple of URLs)
def similarity_matrix_strategy():
    """Generate a similarity matrix with tuple keys"""
    return st.dictionaries(
        keys=st.tuples(url_strategy, url_strategy),
        values=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=0,
        max_size=5
    )

# Strategy for generating TopicCluster objects
topic_cluster_strategy = st.builds(
    TopicCluster,
    id=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    topic_keywords=keyword_strategy,
    cve_ids=st.lists(cve_id_strategy, min_size=0, max_size=5),
    articles=st.lists(article_strategy, min_size=0, max_size=5),
    created_at=datetime_strategy,
    updated_at=datetime_strategy,
    status=status_strategy,
    similarity_matrix=similarity_matrix_strategy(),
    aggregation_threshold=st.integers(min_value=1, max_value=10),
)

# Strategy for generating Synthesis objects
synthesis_strategy = st.builds(
    Synthesis,
    id=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    title=non_empty_safe_text_strategy,
    cluster_id=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    background=safe_text_strategy,
    impact_analysis=safe_text_strategy,
    technical_details=safe_text_strategy,
    mitigation=safe_text_strategy,
    keywords=keyword_strategy,
    source_articles=st.lists(article_strategy, min_size=0, max_size=5),
    additional_sources=st.lists(url_strategy, min_size=0, max_size=5),
    created_at=datetime_strategy,
    published_at=st.one_of(st.none(), datetime_strategy),
    feishu_doc_url=st.one_of(st.none(), url_strategy),
    feishu_doc_token=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
)

# Strategy for generating FilterResult objects
filter_result_strategy = st.builds(
    FilterResult,
    passed=st.lists(article_strategy, min_size=0, max_size=5),
    filtered=st.lists(article_strategy, min_size=0, max_size=5),
    filter_reasons=st.dictionaries(
        keys=url_strategy,
        values=safe_text_strategy,
        min_size=0,
        max_size=5
    ),
)

# Strategy for generating PublishResult objects
publish_result_strategy = st.builds(
    PublishResult,
    success=st.booleans(),
    doc_url=st.one_of(st.none(), url_strategy),
    doc_token=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    error=st.one_of(st.none(), safe_text_strategy),
    local_backup_path=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
)

# Strategy for generating RSSItem objects
rss_item_strategy = st.builds(
    RSSItem,
    title=non_empty_safe_text_strategy,
    link=url_strategy,
    description=safe_text_strategy,
    pub_date=datetime_strategy,
    guid=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    categories=keyword_strategy,
)


# =============================================================================
# Helper Functions for Comparison
# =============================================================================

def articles_equal(a1: Article, a2: Article) -> bool:
    """Compare two Article objects for equality"""
    return a1.to_dict() == a2.to_dict()


def topic_clusters_equal(tc1: TopicCluster, tc2: TopicCluster) -> bool:
    """
    Compare two TopicCluster objects for equality.
    
    Compares all fields including nested articles and similarity matrix.
    """
    # Compare basic fields
    if tc1.id != tc2.id:
        return False
    if tc1.topic_keywords != tc2.topic_keywords:
        return False
    if tc1.cve_ids != tc2.cve_ids:
        return False
    if tc1.status != tc2.status:
        return False
    if tc1.aggregation_threshold != tc2.aggregation_threshold:
        return False
    
    # Compare datetime fields (using isoformat for consistency)
    if tc1.created_at.isoformat() != tc2.created_at.isoformat():
        return False
    if tc1.updated_at.isoformat() != tc2.updated_at.isoformat():
        return False
    
    # Compare articles
    if len(tc1.articles) != len(tc2.articles):
        return False
    for a1, a2 in zip(tc1.articles, tc2.articles):
        if not articles_equal(a1, a2):
            return False
    
    # Compare similarity matrix
    if tc1.similarity_matrix != tc2.similarity_matrix:
        return False
    
    return True


def syntheses_equal(s1: Synthesis, s2: Synthesis) -> bool:
    """
    Compare two Synthesis objects for equality.
    
    Compares all fields including nested articles.
    """
    # Compare basic fields
    if s1.id != s2.id:
        return False
    if s1.title != s2.title:
        return False
    if s1.cluster_id != s2.cluster_id:
        return False
    if s1.background != s2.background:
        return False
    if s1.impact_analysis != s2.impact_analysis:
        return False
    if s1.technical_details != s2.technical_details:
        return False
    if s1.mitigation != s2.mitigation:
        return False
    if s1.keywords != s2.keywords:
        return False
    if s1.additional_sources != s2.additional_sources:
        return False
    if s1.feishu_doc_url != s2.feishu_doc_url:
        return False
    if s1.feishu_doc_token != s2.feishu_doc_token:
        return False
    
    # Compare datetime fields
    if s1.created_at.isoformat() != s2.created_at.isoformat():
        return False
    
    # Handle published_at (can be None)
    if s1.published_at is None and s2.published_at is None:
        pass
    elif s1.published_at is None or s2.published_at is None:
        return False
    elif s1.published_at.isoformat() != s2.published_at.isoformat():
        return False
    
    # Compare source articles
    if len(s1.source_articles) != len(s2.source_articles):
        return False
    for a1, a2 in zip(s1.source_articles, s2.source_articles):
        if not articles_equal(a1, a2):
            return False
    
    return True


def filter_results_equal(fr1: FilterResult, fr2: FilterResult) -> bool:
    """Compare two FilterResult objects for equality"""
    # Compare passed articles
    if len(fr1.passed) != len(fr2.passed):
        return False
    for a1, a2 in zip(fr1.passed, fr2.passed):
        if not articles_equal(a1, a2):
            return False
    
    # Compare filtered articles
    if len(fr1.filtered) != len(fr2.filtered):
        return False
    for a1, a2 in zip(fr1.filtered, fr2.filtered):
        if not articles_equal(a1, a2):
            return False
    
    # Compare filter reasons
    if fr1.filter_reasons != fr2.filter_reasons:
        return False
    
    return True


def publish_results_equal(pr1: PublishResult, pr2: PublishResult) -> bool:
    """Compare two PublishResult objects for equality"""
    return (
        pr1.success == pr2.success and
        pr1.doc_url == pr2.doc_url and
        pr1.doc_token == pr2.doc_token and
        pr1.error == pr2.error and
        pr1.local_backup_path == pr2.local_backup_path
    )


def rss_items_equal(ri1: RSSItem, ri2: RSSItem) -> bool:
    """Compare two RSSItem objects for equality"""
    return (
        ri1.title == ri2.title and
        ri1.link == ri2.link and
        ri1.description == ri2.description and
        ri1.pub_date.isoformat() == ri2.pub_date.isoformat() and
        ri1.guid == ri2.guid and
        ri1.categories == ri2.categories
    )


# =============================================================================
# Property 17: 数据持久化往返 (Data Persistence Roundtrip)
# =============================================================================

class TestProperty17DataPersistenceRoundtrip:
    """
    Property 17: 数据持久化往返
    
    For any TopicCluster 或 Synthesis 对象，保存到数据库后再加载应得到等价的对象。
    
    **Validates: Requirements 6.6**
    
    Feature: topic-aggregation-system, Property 17: 数据持久化往返
    """

    @given(topic_cluster=topic_cluster_strategy)
    @settings(max_examples=100)
    def test_topic_cluster_roundtrip(self, topic_cluster: TopicCluster):
        """
        Test that TopicCluster objects survive serialization roundtrip.
        
        For any TopicCluster object:
        1. Convert to dict using to_dict()
        2. Reconstruct from dict using from_dict()
        3. The reconstructed object should be equivalent to the original
        
        **Validates: Requirements 6.6**
        
        Feature: topic-aggregation-system, Property 17: 数据持久化往返
        """
        # Serialize to dict
        serialized = topic_cluster.to_dict()
        
        # Deserialize back to object
        reconstructed = TopicCluster.from_dict(serialized)
        
        # Verify equivalence
        assert topic_clusters_equal(topic_cluster, reconstructed), (
            f"TopicCluster roundtrip failed.\n"
            f"Original: {topic_cluster}\n"
            f"Reconstructed: {reconstructed}"
        )

    @given(synthesis=synthesis_strategy)
    @settings(max_examples=100)
    def test_synthesis_roundtrip(self, synthesis: Synthesis):
        """
        Test that Synthesis objects survive serialization roundtrip.
        
        For any Synthesis object:
        1. Convert to dict using to_dict()
        2. Reconstruct from dict using from_dict()
        3. The reconstructed object should be equivalent to the original
        
        **Validates: Requirements 6.6**
        
        Feature: topic-aggregation-system, Property 17: 数据持久化往返
        """
        # Serialize to dict
        serialized = synthesis.to_dict()
        
        # Deserialize back to object
        reconstructed = Synthesis.from_dict(serialized)
        
        # Verify equivalence
        assert syntheses_equal(synthesis, reconstructed), (
            f"Synthesis roundtrip failed.\n"
            f"Original: {synthesis}\n"
            f"Reconstructed: {reconstructed}"
        )

    @given(filter_result=filter_result_strategy)
    @settings(max_examples=100)
    def test_filter_result_roundtrip(self, filter_result: FilterResult):
        """
        Test that FilterResult objects survive serialization roundtrip.
        
        For any FilterResult object:
        1. Convert to dict using to_dict()
        2. Reconstruct from dict using from_dict()
        3. The reconstructed object should be equivalent to the original
        
        **Validates: Requirements 6.6**
        
        Feature: topic-aggregation-system, Property 17: 数据持久化往返
        """
        # Serialize to dict
        serialized = filter_result.to_dict()
        
        # Deserialize back to object
        reconstructed = FilterResult.from_dict(serialized)
        
        # Verify equivalence
        assert filter_results_equal(filter_result, reconstructed), (
            f"FilterResult roundtrip failed.\n"
            f"Original: {filter_result}\n"
            f"Reconstructed: {reconstructed}"
        )

    @given(publish_result=publish_result_strategy)
    @settings(max_examples=100)
    def test_publish_result_roundtrip(self, publish_result: PublishResult):
        """
        Test that PublishResult objects survive serialization roundtrip.
        
        For any PublishResult object:
        1. Convert to dict using to_dict()
        2. Reconstruct from dict using from_dict()
        3. The reconstructed object should be equivalent to the original
        
        **Validates: Requirements 6.6**
        
        Feature: topic-aggregation-system, Property 17: 数据持久化往返
        """
        # Serialize to dict
        serialized = publish_result.to_dict()
        
        # Deserialize back to object
        reconstructed = PublishResult.from_dict(serialized)
        
        # Verify equivalence
        assert publish_results_equal(publish_result, reconstructed), (
            f"PublishResult roundtrip failed.\n"
            f"Original: {publish_result}\n"
            f"Reconstructed: {reconstructed}"
        )

    @given(rss_item=rss_item_strategy)
    @settings(max_examples=100)
    def test_rss_item_roundtrip(self, rss_item: RSSItem):
        """
        Test that RSSItem objects survive serialization roundtrip.
        
        For any RSSItem object:
        1. Convert to dict using to_dict()
        2. Reconstruct from dict using from_dict()
        3. The reconstructed object should be equivalent to the original
        
        **Validates: Requirements 6.6**
        
        Feature: topic-aggregation-system, Property 17: 数据持久化往返
        """
        # Serialize to dict
        serialized = rss_item.to_dict()
        
        # Deserialize back to object
        reconstructed = RSSItem.from_dict(serialized)
        
        # Verify equivalence
        assert rss_items_equal(rss_item, reconstructed), (
            f"RSSItem roundtrip failed.\n"
            f"Original: {rss_item}\n"
            f"Reconstructed: {reconstructed}"
        )

    @given(article=article_strategy)
    @settings(max_examples=100)
    def test_article_roundtrip(self, article: Article):
        """
        Test that Article objects survive serialization roundtrip.
        
        This is a supporting test to ensure the base Article model
        also maintains roundtrip consistency, which is essential for
        the composite models (TopicCluster, Synthesis, FilterResult).
        
        **Validates: Requirements 6.6**
        
        Feature: topic-aggregation-system, Property 17: 数据持久化往返
        """
        # Serialize to dict
        serialized = article.to_dict()
        
        # Deserialize back to object
        reconstructed = Article.from_dict(serialized)
        
        # Verify equivalence
        assert articles_equal(article, reconstructed), (
            f"Article roundtrip failed.\n"
            f"Original: {article}\n"
            f"Reconstructed: {reconstructed}"
        )
