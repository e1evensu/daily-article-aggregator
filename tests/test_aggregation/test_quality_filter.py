"""
质量过滤器属性测试

Property 5: 黑名单过滤与原因记录
For any 文章，如果其来源域名在黑名单中，则该文章应被过滤，且 FilterResult 中应包含该文章 URL 到过滤原因的映射。
**Validates: Requirements 2.2, 2.5**

Property 6: 黑名单动态配置往返
For any 域名，添加到黑名单后应能被正确识别为黑名单域名，从黑名单移除后应不再被识别为黑名单域名。
**Validates: Requirements 2.3**

Property 8: 可信来源标记
For any 文章，如果其来源在可信来源列表中，则该文章应被标记为可信来源且不被过滤。
**Validates: Requirements 2.6**

Feature: topic-aggregation-system, Property 5, 6, 8: 质量过滤器属性测试
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.aggregation.quality_filter import QualityFilter, DEFAULT_BLACKLIST_DOMAINS
from src.aggregation.models import FilterResult
from src.models import Article


# =============================================================================
# Test Data Generators (Strategies)
# =============================================================================

# Strategy for generating valid domain names
domain_strategy = st.from_regex(
    r'[a-z]{3,10}\.[a-z]{2,5}',
    fullmatch=True
)

# Strategy for generating domain names that are NOT in the default blacklist
non_blacklisted_domain_strategy = domain_strategy.filter(
    lambda d: d not in DEFAULT_BLACKLIST_DOMAINS and not any(
        d.endswith(f".{bl}") for bl in DEFAULT_BLACKLIST_DOMAINS
    )
)


# Strategy for generating blacklisted domains (from default blacklist)
blacklisted_domain_strategy = st.sampled_from(list(DEFAULT_BLACKLIST_DOMAINS))

# Strategy for generating valid source types
source_type_strategy = st.sampled_from(['rss', 'nvd', 'kev', 'dblp', 'blog', 'arxiv', 'huggingface', 'pwc'])

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

# Strategy for generating keywords
keyword_strategy = st.lists(
    non_empty_safe_text_strategy,
    min_size=0,
    max_size=10
)


def build_url_from_domain(domain: str, path: str = "article") -> str:
    """Build a valid URL from a domain name."""
    return f"https://{domain}/{path}"


# Strategy for generating Article with a specific domain
def article_with_domain_strategy(domain_strat):
    """Generate an Article with URL from the given domain strategy."""
    return st.builds(
        lambda domain, title, source, source_type, keywords: Article(
            title=title,
            url=build_url_from_domain(domain),
            source=source,
            source_type=source_type,
            keywords=keywords,
        ),
        domain=domain_strat,
        title=non_empty_safe_text_strategy,
        source=safe_text_strategy,
        source_type=source_type_strategy,
        keywords=keyword_strategy,
    )


# Strategy for generating Article with blacklisted domain
blacklisted_article_strategy = article_with_domain_strategy(blacklisted_domain_strategy)

# Strategy for generating Article with non-blacklisted domain
non_blacklisted_article_strategy = article_with_domain_strategy(non_blacklisted_domain_strategy)


# =============================================================================
# Property 5: 黑名单过滤与原因记录
# =============================================================================

class TestProperty5BlacklistFilteringAndReasonRecording:
    """
    Property 5: 黑名单过滤与原因记录
    
    For any 文章，如果其来源域名在黑名单中，则该文章应被过滤，
    且 FilterResult 中应包含该文章 URL 到过滤原因的映射。
    
    **Validates: Requirements 2.2, 2.5**
    
    Feature: topic-aggregation-system, Property 5: 黑名单过滤与原因记录
    """

    @given(article=blacklisted_article_strategy)
    @settings(max_examples=100)
    def test_blacklisted_article_is_filtered(self, article: Article):
        """
        Test that articles from blacklisted domains are filtered.
        
        For any article with a blacklisted domain:
        1. The article should appear in the filtered list
        2. The article should NOT appear in the passed list
        
        **Validates: Requirements 2.2**
        
        Feature: topic-aggregation-system, Property 5: 黑名单过滤与原因记录
        """
        quality_filter = QualityFilter()
        
        result = quality_filter.filter_articles([article])
        
        # Article should be filtered
        assert article in result.filtered, (
            f"Article from blacklisted domain should be filtered.\n"
            f"Article URL: {article.url}\n"
            f"Filtered: {[a.url for a in result.filtered]}\n"
            f"Passed: {[a.url for a in result.passed]}"
        )
        
        # Article should NOT be in passed
        assert article not in result.passed, (
            f"Article from blacklisted domain should not be in passed list.\n"
            f"Article URL: {article.url}"
        )

    @given(article=blacklisted_article_strategy)
    @settings(max_examples=100)
    def test_blacklisted_article_has_filter_reason(self, article: Article):
        """
        Test that filtered articles have their filter reason recorded.
        
        For any article with a blacklisted domain:
        1. The FilterResult should contain a mapping from the article URL to filter reason
        2. The filter reason should be a non-empty string
        
        **Validates: Requirements 2.5**
        
        Feature: topic-aggregation-system, Property 5: 黑名单过滤与原因记录
        """
        quality_filter = QualityFilter()
        
        result = quality_filter.filter_articles([article])
        
        # Filter reason should be recorded
        assert article.url in result.filter_reasons, (
            f"Filter reason should be recorded for blacklisted article.\n"
            f"Article URL: {article.url}\n"
            f"Filter reasons: {result.filter_reasons}"
        )
        
        # Filter reason should be non-empty
        reason = result.filter_reasons[article.url]
        assert reason and len(reason) > 0, (
            f"Filter reason should be a non-empty string.\n"
            f"Article URL: {article.url}\n"
            f"Reason: {reason}"
        )


    @given(
        blacklisted_articles=st.lists(blacklisted_article_strategy, min_size=1, max_size=5),
        non_blacklisted_articles=st.lists(non_blacklisted_article_strategy, min_size=0, max_size=5)
    )
    @settings(max_examples=100)
    def test_mixed_articles_filtering(
        self, 
        blacklisted_articles: list[Article], 
        non_blacklisted_articles: list[Article]
    ):
        """
        Test filtering with a mix of blacklisted and non-blacklisted articles.
        
        For any mix of articles:
        1. All blacklisted articles should be filtered
        2. All non-blacklisted articles should pass
        3. Each filtered article should have a filter reason
        
        **Validates: Requirements 2.2, 2.5**
        
        Feature: topic-aggregation-system, Property 5: 黑名单过滤与原因记录
        """
        quality_filter = QualityFilter()
        all_articles = blacklisted_articles + non_blacklisted_articles
        
        result = quality_filter.filter_articles(all_articles)
        
        # All blacklisted articles should be filtered
        for article in blacklisted_articles:
            assert article in result.filtered, (
                f"Blacklisted article should be filtered.\n"
                f"Article URL: {article.url}"
            )
            assert article.url in result.filter_reasons, (
                f"Filter reason should be recorded.\n"
                f"Article URL: {article.url}"
            )
        
        # All non-blacklisted articles should pass
        for article in non_blacklisted_articles:
            assert article in result.passed, (
                f"Non-blacklisted article should pass.\n"
                f"Article URL: {article.url}"
            )
            assert article.url not in result.filter_reasons, (
                f"Non-blacklisted article should not have filter reason.\n"
                f"Article URL: {article.url}"
            )


# =============================================================================
# Property 6: 黑名单动态配置往返
# =============================================================================

class TestProperty6BlacklistDynamicConfigurationRoundtrip:
    """
    Property 6: 黑名单动态配置往返
    
    For any 域名，添加到黑名单后应能被正确识别为黑名单域名，
    从黑名单移除后应不再被识别为黑名单域名。
    
    **Validates: Requirements 2.3**
    
    Feature: topic-aggregation-system, Property 6: 黑名单动态配置往返
    """

    @given(domain=non_blacklisted_domain_strategy)
    @settings(max_examples=100)
    def test_add_domain_to_blacklist(self, domain: str):
        """
        Test that adding a domain to blacklist makes it recognized as blacklisted.
        
        For any domain not in the default blacklist:
        1. Initially, URLs from this domain should NOT be blacklisted
        2. After adding to blacklist, URLs from this domain SHOULD be blacklisted
        
        **Validates: Requirements 2.3**
        
        Feature: topic-aggregation-system, Property 6: 黑名单动态配置往返
        """
        quality_filter = QualityFilter()
        test_url = build_url_from_domain(domain)
        
        # Initially not blacklisted
        assert not quality_filter.is_blacklisted(test_url), (
            f"Domain should not be blacklisted initially.\n"
            f"Domain: {domain}\n"
            f"URL: {test_url}"
        )
        
        # Add to blacklist
        quality_filter.add_to_blacklist(domain)
        
        # Now should be blacklisted
        assert quality_filter.is_blacklisted(test_url), (
            f"Domain should be blacklisted after adding.\n"
            f"Domain: {domain}\n"
            f"URL: {test_url}\n"
            f"Current blacklist: {quality_filter.blacklist_domains}"
        )


    @given(domain=non_blacklisted_domain_strategy)
    @settings(max_examples=100)
    def test_remove_domain_from_blacklist(self, domain: str):
        """
        Test that removing a domain from blacklist makes it no longer recognized.
        
        For any domain:
        1. Add domain to blacklist - should be recognized as blacklisted
        2. Remove domain from blacklist - should no longer be recognized
        
        **Validates: Requirements 2.3**
        
        Feature: topic-aggregation-system, Property 6: 黑名单动态配置往返
        """
        quality_filter = QualityFilter()
        test_url = build_url_from_domain(domain)
        
        # Add to blacklist first
        quality_filter.add_to_blacklist(domain)
        assert quality_filter.is_blacklisted(test_url), (
            f"Domain should be blacklisted after adding.\n"
            f"Domain: {domain}"
        )
        
        # Remove from blacklist
        quality_filter.remove_from_blacklist(domain)
        
        # Should no longer be blacklisted
        assert not quality_filter.is_blacklisted(test_url), (
            f"Domain should not be blacklisted after removal.\n"
            f"Domain: {domain}\n"
            f"URL: {test_url}\n"
            f"Current blacklist: {quality_filter.blacklist_domains}"
        )

    @given(domain=non_blacklisted_domain_strategy)
    @settings(max_examples=100)
    def test_blacklist_roundtrip(self, domain: str):
        """
        Test complete roundtrip: add -> verify -> remove -> verify.
        
        For any domain:
        1. Initially not blacklisted
        2. Add to blacklist -> becomes blacklisted
        3. Remove from blacklist -> no longer blacklisted
        
        **Validates: Requirements 2.3**
        
        Feature: topic-aggregation-system, Property 6: 黑名单动态配置往返
        """
        quality_filter = QualityFilter()
        test_url = build_url_from_domain(domain)
        
        # Step 1: Initially not blacklisted
        initial_state = quality_filter.is_blacklisted(test_url)
        assert not initial_state, (
            f"Domain should not be blacklisted initially.\n"
            f"Domain: {domain}"
        )
        
        # Step 2: Add to blacklist
        quality_filter.add_to_blacklist(domain)
        after_add_state = quality_filter.is_blacklisted(test_url)
        assert after_add_state, (
            f"Domain should be blacklisted after adding.\n"
            f"Domain: {domain}"
        )
        
        # Step 3: Remove from blacklist
        quality_filter.remove_from_blacklist(domain)
        after_remove_state = quality_filter.is_blacklisted(test_url)
        assert not after_remove_state, (
            f"Domain should not be blacklisted after removal.\n"
            f"Domain: {domain}"
        )

    @given(domain=blacklisted_domain_strategy)
    @settings(max_examples=100)
    def test_remove_default_blacklisted_domain(self, domain: str):
        """
        Test removing a domain from the default blacklist.
        
        For any domain in the default blacklist:
        1. Initially should be blacklisted
        2. After removal, should no longer be blacklisted
        
        **Validates: Requirements 2.3**
        
        Feature: topic-aggregation-system, Property 6: 黑名单动态配置往返
        """
        quality_filter = QualityFilter()
        test_url = build_url_from_domain(domain)
        
        # Initially blacklisted (default)
        assert quality_filter.is_blacklisted(test_url), (
            f"Default blacklisted domain should be blacklisted.\n"
            f"Domain: {domain}"
        )
        
        # Remove from blacklist
        quality_filter.remove_from_blacklist(domain)
        
        # Should no longer be blacklisted
        assert not quality_filter.is_blacklisted(test_url), (
            f"Domain should not be blacklisted after removal.\n"
            f"Domain: {domain}\n"
            f"Current blacklist: {quality_filter.blacklist_domains}"
        )


# =============================================================================
# Property 8: 可信来源标记
# =============================================================================

class TestProperty8TrustedSourceMarking:
    """
    Property 8: 可信来源标记
    
    For any 文章，如果其来源在可信来源列表中，则该文章应被标记为可信来源且不被过滤。
    
    **Validates: Requirements 2.6**
    
    Feature: topic-aggregation-system, Property 8: 可信来源标记
    """

    @given(
        domain=blacklisted_domain_strategy,
        trusted_source=non_empty_safe_text_strategy
    )
    @settings(max_examples=100)
    def test_trusted_source_not_filtered_by_source_field(
        self, 
        domain: str, 
        trusted_source: str
    ):
        """
        Test that articles from trusted sources (by source field) are not filtered.
        
        For any article with a blacklisted domain but trusted source:
        1. The article should be marked as trusted
        2. The article should NOT be filtered (even if domain is blacklisted)
        3. The article should appear in the passed list
        
        **Validates: Requirements 2.6**
        
        Feature: topic-aggregation-system, Property 8: 可信来源标记
        """
        # Create filter with trusted source
        quality_filter = QualityFilter({
            "trusted_sources": [trusted_source]
        })
        
        # Create article with blacklisted domain but trusted source
        article = Article(
            title="Test Article",
            url=build_url_from_domain(domain),
            source=trusted_source,
            source_type="rss",
        )
        
        # Article should be trusted
        assert quality_filter.is_trusted(article), (
            f"Article with trusted source should be marked as trusted.\n"
            f"Article source: {article.source}\n"
            f"Trusted sources: {quality_filter.trusted_sources}"
        )
        
        # Article should pass filtering (not be filtered)
        result = quality_filter.filter_articles([article])
        
        assert article in result.passed, (
            f"Trusted article should be in passed list.\n"
            f"Article URL: {article.url}\n"
            f"Article source: {article.source}"
        )
        
        assert article not in result.filtered, (
            f"Trusted article should NOT be in filtered list.\n"
            f"Article URL: {article.url}"
        )

    @given(trusted_domain=non_blacklisted_domain_strategy)
    @settings(max_examples=100)
    def test_trusted_source_by_domain(self, trusted_domain: str):
        """
        Test that articles from trusted domains are not filtered.
        
        For any article with a domain in the trusted sources list:
        1. The article should be marked as trusted
        2. The article should NOT be filtered
        
        **Validates: Requirements 2.6**
        
        Feature: topic-aggregation-system, Property 8: 可信来源标记
        """
        # Create filter with trusted domain
        quality_filter = QualityFilter({
            "trusted_sources": [trusted_domain]
        })
        
        # Create article with trusted domain
        article = Article(
            title="Test Article",
            url=build_url_from_domain(trusted_domain),
            source="Some Source",
            source_type="rss",
        )
        
        # Article should be trusted
        assert quality_filter.is_trusted(article), (
            f"Article from trusted domain should be marked as trusted.\n"
            f"Article URL: {article.url}\n"
            f"Trusted sources: {quality_filter.trusted_sources}"
        )
        
        # Article should pass filtering
        result = quality_filter.filter_articles([article])
        
        assert article in result.passed, (
            f"Article from trusted domain should be in passed list.\n"
            f"Article URL: {article.url}"
        )


    @given(
        domain=blacklisted_domain_strategy,
        trusted_source=non_empty_safe_text_strategy
    )
    @settings(max_examples=100)
    def test_trusted_source_overrides_blacklist(
        self, 
        domain: str, 
        trusted_source: str
    ):
        """
        Test that trusted source status overrides blacklist filtering.
        
        For any article with BOTH a blacklisted domain AND a trusted source:
        1. The trusted source status should take precedence
        2. The article should NOT be filtered
        3. The article should NOT have a filter reason recorded
        
        **Validates: Requirements 2.6**
        
        Feature: topic-aggregation-system, Property 8: 可信来源标记
        """
        # Create filter with trusted source
        quality_filter = QualityFilter({
            "trusted_sources": [trusted_source]
        })
        
        # Create article with blacklisted domain but trusted source
        article = Article(
            title="Test Article",
            url=build_url_from_domain(domain),
            source=trusted_source,
            source_type="rss",
        )
        
        # Verify domain is blacklisted
        assert quality_filter.is_blacklisted(article.url), (
            f"Domain should be blacklisted.\n"
            f"Domain: {domain}"
        )
        
        # But article should be trusted
        assert quality_filter.is_trusted(article), (
            f"Article should be trusted.\n"
            f"Source: {trusted_source}"
        )
        
        # Filter articles
        result = quality_filter.filter_articles([article])
        
        # Trusted source should override blacklist
        assert article in result.passed, (
            f"Trusted article should pass even with blacklisted domain.\n"
            f"Article URL: {article.url}\n"
            f"Article source: {article.source}"
        )
        
        assert article not in result.filtered, (
            f"Trusted article should not be filtered.\n"
            f"Article URL: {article.url}"
        )
        
        assert article.url not in result.filter_reasons, (
            f"Trusted article should not have filter reason.\n"
            f"Article URL: {article.url}"
        )

    @given(
        trusted_sources=st.lists(non_empty_safe_text_strategy, min_size=1, max_size=5),
        article_source_index=st.integers(min_value=0)
    )
    @settings(max_examples=100)
    def test_multiple_trusted_sources(
        self, 
        trusted_sources: list[str], 
        article_source_index: int
    ):
        """
        Test that any source in the trusted sources list is recognized.
        
        For any list of trusted sources:
        1. Articles from any of these sources should be marked as trusted
        2. Articles from any of these sources should not be filtered
        
        **Validates: Requirements 2.6**
        
        Feature: topic-aggregation-system, Property 8: 可信来源标记
        """
        # Ensure we have at least one trusted source
        assume(len(trusted_sources) > 0)
        
        # Create filter with multiple trusted sources
        quality_filter = QualityFilter({
            "trusted_sources": trusted_sources
        })
        
        # Pick one of the trusted sources
        selected_source = trusted_sources[article_source_index % len(trusted_sources)]
        
        # Create article with the selected trusted source
        article = Article(
            title="Test Article",
            url="https://example.com/article",
            source=selected_source,
            source_type="rss",
        )
        
        # Article should be trusted
        assert quality_filter.is_trusted(article), (
            f"Article with trusted source should be marked as trusted.\n"
            f"Article source: {article.source}\n"
            f"Trusted sources: {quality_filter.trusted_sources}"
        )
        
        # Article should pass filtering
        result = quality_filter.filter_articles([article])
        
        assert article in result.passed, (
            f"Article from trusted source should be in passed list.\n"
            f"Article source: {article.source}"
        )

    @given(
        domain=non_blacklisted_domain_strategy,
        source=safe_text_strategy
    )
    @settings(max_examples=100)
    def test_non_trusted_non_blacklisted_article_passes(
        self, 
        domain: str, 
        source: str
    ):
        """
        Test that articles that are neither trusted nor blacklisted pass filtering.
        
        For any article with a non-blacklisted domain and non-trusted source:
        1. The article should NOT be marked as trusted
        2. The article should still pass filtering (not blacklisted)
        
        **Validates: Requirements 2.6**
        
        Feature: topic-aggregation-system, Property 8: 可信来源标记
        """
        # Create filter with no trusted sources
        quality_filter = QualityFilter({
            "trusted_sources": []
        })
        
        # Create article with non-blacklisted domain
        article = Article(
            title="Test Article",
            url=build_url_from_domain(domain),
            source=source,
            source_type="rss",
        )
        
        # Article should NOT be trusted (no trusted sources configured)
        assert not quality_filter.is_trusted(article), (
            f"Article should not be trusted when no trusted sources configured.\n"
            f"Article source: {article.source}"
        )
        
        # Article should still pass (not blacklisted)
        result = quality_filter.filter_articles([article])
        
        assert article in result.passed, (
            f"Non-blacklisted article should pass even if not trusted.\n"
            f"Article URL: {article.url}"
        )
