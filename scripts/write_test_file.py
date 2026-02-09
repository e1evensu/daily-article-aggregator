"""Write the test file."""

content = '''"""
SitemapParser Unit Tests
"""

import gzip
import tempfile
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from src.fetchers.sitemap_importer import (
    SitemapEntry,
    SitemapParser,
    SitemapParseError,
    CrawlRules,
    CrawlRuleEngine,
    ConfigurationError,
    CrawlState,
    CrawlStats,
    CrawledPage,
    InMemoryCrawlStateStore,
    JsonFileCrawlStateStore,
    IncrementalCrawler,
    HTMLToMarkdownConverter,
)


VALID_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://example.com/page1</loc>
        <lastmod>2024-01-15T10:30:00+00:00</lastmod>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>https://example.com/page2</loc>
    </url>
</urlset>
"""

MALFORMED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset>
    <url>
        <loc>https://example.com/page1</loc>
"""


class TestSitemapEntry:
    def test_create_with_all_fields(self):
        entry = SitemapEntry(
            loc="https://example.com/page1",
            lastmod=datetime(2024, 1, 15),
            changefreq="weekly",
            priority=0.8
        )
        assert entry.loc == "https://example.com/page1"
        assert entry.priority == 0.8

    def test_create_with_required_only(self):
        entry = SitemapEntry(loc="https://example.com/page1")
        assert entry.lastmod is None


class TestSitemapParser:
    def test_parse_valid_sitemap(self):
        parser = SitemapParser()
        entries = parser.parse_content(VALID_SITEMAP_XML)
        assert len(entries) == 2
        assert entries[0].loc == "https://example.com/page1"

    def test_parse_malformed_xml(self):
        parser = SitemapParser()
        with pytest.raises(SitemapParseError):
            parser.parse_content(MALFORMED_XML)

    def test_parse_gzipped_content(self):
        parser = SitemapParser()
        compressed = gzip.compress(VALID_SITEMAP_XML.encode("utf-8"))
        entries = parser.parse_content(compressed, is_gzipped=True)
        assert len(entries) == 2


class TestCrawlRules:
    def test_default_values(self):
        rules = CrawlRules()
        assert rules.include_patterns == []
        assert rules.use_regex is False


class TestCrawlRuleEngine:
    def test_no_rules_crawl_all(self):
        rules = CrawlRules()
        engine = CrawlRuleEngine(rules)
        assert engine.should_crawl("https://example.com/any") is True

    def test_include_only_matches(self):
        rules = CrawlRules(include_patterns=["/docs/*"])
        engine = CrawlRuleEngine(rules)
        assert engine.should_crawl("https://example.com/docs/guide") is True
        assert engine.should_crawl("https://example.com/blog/post") is False

    def test_exclude_takes_precedence(self):
        rules = CrawlRules(
            include_patterns=["/docs/*"],
            exclude_patterns=["*/archive/*"]
        )
        engine = CrawlRuleEngine(rules)
        assert engine.should_crawl("https://example.com/docs/guide") is True
        assert engine.should_crawl("https://example.com/docs/archive/old") is False

    def test_invalid_regex(self):
        rules = CrawlRules(include_patterns=["[invalid"], use_regex=True)
        with pytest.raises(ConfigurationError):
            CrawlRuleEngine(rules)


class TestCrawlState:
    def test_create_with_all_fields(self):
        state = CrawlState(
            url="https://example.com/page1",
            last_crawl=datetime(2024, 1, 15),
            content_hash="abc123"
        )
        assert state.url == "https://example.com/page1"
        assert state.content_hash == "abc123"


class TestCrawlStats:
    def test_default_values(self):
        stats = CrawlStats()
        assert stats.new_pages == 0
        assert stats.total_pages == 0

    def test_total_pages_property(self):
        stats = CrawlStats(new_pages=5, updated_pages=3, skipped_pages=10, failed_pages=2)
        assert stats.total_pages == 20


class TestInMemoryCrawlStateStore:
    def test_save_and_get_state(self):
        store = InMemoryCrawlStateStore()
        state = CrawlState(url="https://example.com/page1", content_hash="abc123")
        store.save_state(state)
        retrieved = store.get_state("https://example.com/page1")
        assert retrieved is not None
        assert retrieved.content_hash == "abc123"

    def test_clear_states(self):
        store = InMemoryCrawlStateStore()
        store.save_state(CrawlState(url="https://example.com/page1"))
        store.clear()
        assert store.get_state("https://example.com/page1") is None


class TestIncrementalCrawler:
    def test_crawl_new_pages(self):
        store = InMemoryCrawlStateStore()
        crawler = IncrementalCrawler(store)
        entries = [SitemapEntry(loc="https://example.com/page1")]
        pages, stats = crawler.crawl(entries)
        assert stats.new_pages == 1
        assert len(pages) == 1

    def test_skip_unchanged_pages(self):
        store = InMemoryCrawlStateStore()
        store.save_state(CrawlState(
            url="https://example.com/page1",
            last_crawl=datetime(2024, 1, 20),
            content_hash="abc123"
        ))
        crawler = IncrementalCrawler(store)
        entries = [SitemapEntry(loc="https://example.com/page1", lastmod=datetime(2024, 1, 15))]
        pages, stats = crawler.crawl(entries)
        assert stats.skipped_pages == 1

    def test_force_refresh(self):
        store = InMemoryCrawlStateStore()
        store.save_state(CrawlState(
            url="https://example.com/page1",
            last_crawl=datetime(2024, 1, 20),
            content_hash="abc123"
        ))
        crawler = IncrementalCrawler(store)
        entries = [SitemapEntry(loc="https://example.com/page1", lastmod=datetime(2024, 1, 15))]
        pages, stats = crawler.crawl(entries, force_refresh=True)
        assert len(pages) == 1


class TestHTMLToMarkdownConverter:
    """Tests for HTMLToMarkdownConverter - Validates Requirements 7.1-7.5"""

    def test_convert_empty_html(self):
        converter = HTMLToMarkdownConverter()
        assert converter.convert("") == ""

    def test_convert_headings(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert("<h1>Title</h1><h2>Subtitle</h2>")
        assert "# Title" in result
        assert "## Subtitle" in result

    def test_convert_bold_italic(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert("<strong>Bold</strong> <em>Italic</em>")
        assert "**Bold**" in result
        assert "*Italic*" in result

    def test_convert_links(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert('<a href="https://example.com">Link</a>')
        assert "[Link](https://example.com)" in result

    def test_convert_lists(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert("<ul><li>A</li><li>B</li></ul>")
        assert "- A" in result
        assert "- B" in result

    def test_convert_code_block(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert('<pre><code class="language-python">print(1)</code></pre>')
        assert "```python" in result

    def test_convert_table(self):
        converter = HTMLToMarkdownConverter()
        html = "<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"
        result = converter.convert(html)
        assert "| A |" in result

    def test_remove_script(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert("<p>OK</p><script>bad</script>")
        assert "OK" in result
        assert "bad" not in result

    def test_remove_nav_footer(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert("<nav>Nav</nav><p>Main</p><footer>Foot</footer>")
        assert "Main" in result
        assert "Nav" not in result
        assert "Foot" not in result

    def test_malformed_html(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert("<p>Unclosed<div>Nested")
        assert "Unclosed" in result or "Nested" in result
'''

with open('tests/test_fetchers/test_sitemap_importer.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('File written successfully')
print(f'File size: {len(content)} bytes')
