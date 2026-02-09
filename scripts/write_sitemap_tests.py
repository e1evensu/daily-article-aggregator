#!/usr/bin/env python3
"""Script to write the complete sitemap importer test file."""

TEST_CONTENT = '''"""
SitemapParser 单元测试
Unit tests for SitemapParser

测试 Sitemap XML 解析器的各项功能，包括标准 sitemap 格式、
sitemap index 格式和 gzip 压缩处理。

Tests for Sitemap XML parser functionality, including standard sitemap format,
sitemap index format, and gzip compression handling.

Requirements:
- 5.1: WHEN a valid sitemap.xml URL is provided, THE Sitemap_Importer SHALL parse and extract all page URLs
- 5.2: THE Sitemap_Importer SHALL support standard sitemap format with loc, lastmod, changefreq, and priority elements
- 5.3: THE Sitemap_Importer SHALL support sitemap index files containing references to multiple sitemaps
- 5.4: IF sitemap.xml is malformed, THEN THE Sitemap_Importer SHALL return a descriptive parsing error
- 5.5: THE Sitemap_Importer SHALL handle gzip-compressed sitemaps transparently
"""

import gzip
import re
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
    SitemapImporter,
    SitemapImporterConfig,
    ImportResult,
    FileCrawlStateStore,
)


# =============================================================================
# Test Data
# =============================================================================

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
        <lastmod>2024-01-10</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>https://example.com/page3</loc>
    </url>
</urlset>
"""

VALID_SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <sitemap>
        <loc>https://example.com/sitemap1.xml</loc>
        <lastmod>2024-01-15</lastmod>
    </sitemap>
    <sitemap>
        <loc>https://example.com/sitemap2.xml</loc>
    </sitemap>
</sitemapindex>
"""

MALFORMED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://example.com/page1</loc>
    <!-- Missing closing tags -->
"""

EMPTY_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
</urlset>
"""


# =============================================================================
# SitemapEntry Tests
# =============================================================================

class TestSitemapEntry:
    """测试 SitemapEntry 数据类"""
    
    def test_create_with_all_fields(self):
        entry = SitemapEntry(
            loc='https://example.com/page1',
            lastmod=datetime(2024, 1, 15, 10, 30, 0),
            changefreq='weekly',
            priority=0.8
        )
        assert entry.loc == 'https://example.com/page1'
        assert entry.lastmod == datetime(2024, 1, 15, 10, 30, 0)
        assert entry.changefreq == 'weekly'
        assert entry.priority == 0.8
    
    def test_create_with_required_only(self):
        entry = SitemapEntry(loc='https://example.com/page1')
        assert entry.loc == 'https://example.com/page1'
        assert entry.lastmod is None


# =============================================================================
# SitemapParser Tests
# =============================================================================

class TestSitemapParser:
    """测试 SitemapParser"""
    
    def test_default_init(self):
        parser = SitemapParser()
        assert parser.timeout == 30
        assert 'PandaWiki' in parser.user_agent
    
    def test_parse_valid_sitemap(self):
        parser = SitemapParser()
        entries = parser.parse_content(VALID_SITEMAP_XML)
        assert len(entries) == 3
        assert entries[0].loc == 'https://example.com/page1'
        assert entries[0].priority == 0.8
    
    def test_parse_empty_sitemap(self):
        parser = SitemapParser()
        entries = parser.parse_content(EMPTY_SITEMAP_XML)
        assert len(entries) == 0
    
    def test_parse_malformed_xml(self):
        parser = SitemapParser()
        with pytest.raises(SitemapParseError):
            parser.parse_content(MALFORMED_XML)
    
    def test_parse_gzipped_content(self):
        parser = SitemapParser()
        compressed = gzip.compress(VALID_SITEMAP_XML.encode('utf-8'))
        entries = parser.parse_content(compressed, is_gzipped=True)
        assert len(entries) == 3
    
    def test_parse_sitemap_index(self):
        parser = SitemapParser()
        sitemap_urls = parser.parse_index_content(VALID_SITEMAP_INDEX_XML)
        assert len(sitemap_urls) == 2
        assert 'https://example.com/sitemap1.xml' in sitemap_urls


# =============================================================================
# CrawlRules Tests
# =============================================================================

class TestCrawlRules:
    """测试 CrawlRules 数据类"""
    
    def test_default_values(self):
        rules = CrawlRules()
        assert rules.include_patterns == []
        assert rules.exclude_patterns == []
        assert rules.use_regex is False
    
    def test_create_with_patterns(self):
        rules = CrawlRules(
            include_patterns=['/docs/*', '/blog/*'],
            exclude_patterns=['*/archive/*']
        )
        assert len(rules.include_patterns) == 2


# =============================================================================
# CrawlRuleEngine Tests
# =============================================================================

class TestCrawlRuleEngine:
    """测试 CrawlRuleEngine"""
    
    def test_no_rules_crawl_all(self):
        rules = CrawlRules()
        engine = CrawlRuleEngine(rules)
        assert engine.should_crawl('https://example.com/any/path') is True
    
    def test_include_only_matches(self):
        rules = CrawlRules(include_patterns=['/docs/*'])
        engine = CrawlRuleEngine(rules)
        assert engine.should_crawl('https://example.com/docs/guide') is True
        assert engine.should_crawl('https://example.com/blog/post') is False
    
    def test_exclude_only_blocks(self):
        rules = CrawlRules(exclude_patterns=['*/archive/*'])
        engine = CrawlRuleEngine(rules)
        assert engine.should_crawl('https://example.com/docs/guide') is True
        assert engine.should_crawl('https://example.com/docs/archive/old') is False
    
    def test_exclude_takes_precedence(self):
        rules = CrawlRules(
            include_patterns=['/docs/*'],
            exclude_patterns=['*/archive/*']
        )
        engine = CrawlRuleEngine(rules)
        assert engine.should_crawl('https://example.com/docs/guide') is True
        assert engine.should_crawl('https://example.com/docs/archive/old') is False
    
    def test_invalid_regex(self):
        rules = CrawlRules(include_patterns=['[invalid'], use_regex=True)
        with pytest.raises(ConfigurationError):
            CrawlRuleEngine(rules)


# =============================================================================
# CrawlState Tests
# =============================================================================

class TestCrawlState:
    """测试 CrawlState 数据类"""
    
    def test_create_with_all_fields(self):
        state = CrawlState(
            url='https://example.com/page1',
            last_crawl=datetime(2024, 1, 15),
            content_hash='abc123'
        )
        assert state.url == 'https://example.com/page1'
        assert state.content_hash == 'abc123'


# =============================================================================
# CrawlStats Tests
# =============================================================================

class TestCrawlStats:
    """测试 CrawlStats 数据类"""
    
    def test_default_values(self):
        stats = CrawlStats()
        assert stats.new_pages == 0
        assert stats.total_pages == 0
    
    def test_total_pages_property(self):
        stats = CrawlStats(new_pages=5, updated_pages=3, skipped_pages=10, failed_pages=2)
        assert stats.total_pages == 20


# =============================================================================
# InMemoryCrawlStateStore Tests
# =============================================================================

class TestInMemoryCrawlStateStore:
    """测试 InMemoryCrawlStateStore"""
    
    def test_save_and_get_state(self):
        store = InMemoryCrawlStateStore()
        state = CrawlState(url='https://example.com/page1', content_hash='abc123')
        store.save_state(state)
        retrieved = store.get_state('https://example.com/page1')
        assert retrieved is not None
        assert retrieved.content_hash == 'abc123'
    
    def test_clear_states(self):
        store = InMemoryCrawlStateStore()
        store.save_state(CrawlState(url='https://example.com/page1'))
        store.clear()
        assert store.get_state('https://example.com/page1') is None


# =============================================================================
# IncrementalCrawler Tests
# =============================================================================

class TestIncrementalCrawler:
    """测试 IncrementalCrawler"""
    
    def test_crawl_new_pages(self):
        store = InMemoryCrawlStateStore()
        crawler = IncrementalCrawler(store)
        entries = [
            SitemapEntry(loc='https://example.com/page1'),
            SitemapEntry(loc='https://example.com/page2'),
        ]
        pages, stats = crawler.crawl(entries)
        assert stats.new_pages == 2
        assert len(pages) == 2
    
    def test_skip_unchanged_pages(self):
        store = InMemoryCrawlStateStore()
        store.save_state(CrawlState(
            url='https://example.com/page1',
            last_crawl=datetime(2024, 1, 20),
            content_hash='abc123'
        ))
        crawler = IncrementalCrawler(store)
        entries = [SitemapEntry(loc='https://example.com/page1', lastmod=datetime(2024, 1, 15))]
        pages, stats = crawler.crawl(entries)
        assert stats.skipped_pages == 1
    
    def test_force_refresh(self):
        store = InMemoryCrawlStateStore()
        store.save_state(CrawlState(
            url='https://example.com/page1',
            last_crawl=datetime(2024, 1, 20),
            content_hash='abc123'
        ))
        crawler = IncrementalCrawler(store)
        entries = [SitemapEntry(loc='https://example.com/page1', lastmod=datetime(2024, 1, 15))]
        pages, stats = crawler.crawl(entries, force_refresh=True)
        assert len(pages) == 1


# =============================================================================
# HTMLToMarkdownConverter Tests
# =============================================================================

class TestHTMLToMarkdownConverter:
    """测试 HTMLToMarkdownConverter"""
    
    def test_convert_empty_html(self):
        converter = HTMLToMarkdownConverter()
        assert converter.convert('') == ''
    
    def test_convert_headings(self):
        converter = HTMLToMarkdownConverter()
        html = '<h1>Heading 1</h1><h2>Heading 2</h2>'
        result = converter.convert(html)
        assert '# Heading 1' in result
        assert '## Heading 2' in result
    
    def test_convert_bold_italic(self):
        converter = HTMLToMarkdownConverter()
        html = '<p><strong>bold</strong> and <em>italic</em></p>'
        result = converter.convert(html)
        assert '**bold**' in result
        assert '*italic*' in result
    
    def test_convert_links(self):
        converter = HTMLToMarkdownConverter()
        html = '<a href="https://example.com">Example</a>'
        result = converter.convert(html)
        assert '[Example](https://example.com)' in result
    
    def test_convert_lists(self):
        converter = HTMLToMarkdownConverter()
        html = '<ul><li>Item 1</li><li>Item 2</li></ul>'
        result = converter.convert(html)
        assert '- Item 1' in result
        assert '- Item 2' in result
    
    def test_convert_code_block(self):
        converter = HTMLToMarkdownConverter()
        html = '<pre><code class="language-python">print("Hello")</code></pre>'
        result = converter.convert(html)
        assert '```python' in result
    
    def test_convert_table(self):
        converter = HTMLToMarkdownConverter()
        html = '<table><tr><th>A</th></tr><tr><td>1</td></tr></table>'
        result = converter.convert(html)
        assert '| A |' in result
    
    def test_remove_script(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert('<p>OK</p><script>bad</script>')
        assert 'OK' in result
        assert 'bad' not in result
    
    def test_remove_nav_footer(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert('<nav>Nav</nav><p>Main</p><footer>Foot</footer>')
        assert 'Main' in result
        assert 'Nav' not in result
        assert 'Foot' not in result
    
    def test_malformed_html(self):
        converter = HTMLToMarkdownConverter()
        result = converter.convert('<p>Unclosed<div>Nested')
        assert 'Unclosed' in result or 'Nested' in result


# =============================================================================
# SitemapImporterConfig Tests
# =============================================================================

class TestSitemapImporterConfig:
    """测试 SitemapImporterConfig 数据类"""
    
    def test_create_with_required_only(self):
        config = SitemapImporterConfig(sitemap_url='https://example.com/sitemap.xml')
        assert config.sitemap_url == 'https://example.com/sitemap.xml'
        assert config.include_patterns == []
        assert config.timeout == 30
    
    def test_create_with_all_fields(self):
        config = SitemapImporterConfig(
            sitemap_url='https://example.com/sitemap.xml',
            include_patterns=['/docs/*'],
            exclude_patterns=['*/archive/*'],
            timeout=60,
            force_refresh=True
        )
        assert config.include_patterns == ['/docs/*']
        assert config.timeout == 60
        assert config.force_refresh is True


# =============================================================================
# ImportResult Tests
# =============================================================================

class TestImportResult:
    """测试 ImportResult 数据类"""
    
    def test_default_values(self):
        result = ImportResult()
        assert result.total_urls == 0
        assert result.crawled_urls == 0
        assert result.errors == []
    
    def test_success_rate_calculation(self):
        result = ImportResult(filtered_urls=100, crawled_urls=80)
        assert result.success_rate == 0.8
    
    def test_success_rate_zero_filtered(self):
        result = ImportResult(filtered_urls=0, crawled_urls=0)
        assert result.success_rate == 0.0


# =============================================================================
# SitemapImporter Tests
# =============================================================================

class TestSitemapImporter:
    """测试 SitemapImporter"""
    
    def test_init_with_config_object(self):
        config = SitemapImporterConfig(
            sitemap_url='https://example.com/sitemap.xml',
            include_patterns=['/docs/*']
        )
        importer = SitemapImporter(config)
        assert importer.config.sitemap_url == 'https://example.com/sitemap.xml'
    
    def test_init_with_dict_config(self):
        config = {
            'sitemap_url': 'https://example.com/sitemap.xml',
            'include_patterns': ['/blog/*'],
            'timeout': 60
        }
        importer = SitemapImporter(config)
        assert importer.config.sitemap_url == 'https://example.com/sitemap.xml'
        assert importer.config.timeout == 60
    
    def test_init_without_sitemap_url_raises_error(self):
        with pytest.raises(ConfigurationError):
            SitemapImporter({'include_patterns': ['/docs/*']})
    
    def test_filter_entries_with_include_patterns(self):
        config = SitemapImporterConfig(
            sitemap_url='https://example.com/sitemap.xml',
            include_patterns=['/docs/*']
        )
        importer = SitemapImporter(config)
        entries = [
            SitemapEntry(loc='https://example.com/docs/guide'),
            SitemapEntry(loc='https://example.com/blog/post'),
        ]
        filtered = importer._filter_entries(entries)
        assert len(filtered) == 1
        assert '/docs/' in filtered[0].loc
    
    def test_generate_id_from_url(self):
        config = SitemapImporterConfig(sitemap_url='https://example.com/sitemap.xml')
        importer = SitemapImporter(config)
        id1 = importer._generate_id('https://example.com/page1')
        id2 = importer._generate_id('https://example.com/page1')
        assert id1 == id2
        assert len(id1) == 16
    
    def test_extract_title_from_title_tag(self):
        config = SitemapImporterConfig(sitemap_url='https://example.com/sitemap.xml')
        importer = SitemapImporter(config)
        html = '<html><head><title>Page Title</title></head></html>'
        title = importer._extract_title(html, 'https://example.com/page')
        assert title == 'Page Title'
    
    def test_reset_state(self):
        config = SitemapImporterConfig(sitemap_url='https://example.com/sitemap.xml')
        store = InMemoryCrawlStateStore()
        store.save_state(CrawlState(url='https://example.com/page1', content_hash='abc'))
        importer = SitemapImporter(config, state_store=store)
        importer.reset_state()
        assert store.get_state('https://example.com/page1') is None


# =============================================================================
# FileCrawlStateStore Tests
# =============================================================================

class TestFileCrawlStateStore:
    """测试 FileCrawlStateStore"""
    
    def test_save_and_get_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, 'state.json')
            store = FileCrawlStateStore(file_path)
            state = CrawlState(
                url='https://example.com/page1',
                content_hash='abc123',
                last_crawl=datetime(2024, 1, 15)
            )
            store.save(state)
            retrieved = store.get('https://example.com/page1')
            assert retrieved is not None
            assert retrieved.content_hash == 'abc123'
    
    def test_persistence_across_instances(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, 'state.json')
            store1 = FileCrawlStateStore(file_path)
            store1.save(CrawlState(url='https://example.com/page1', content_hash='abc123'))
            store2 = FileCrawlStateStore(file_path)
            retrieved = store2.get('https://example.com/page1')
            assert retrieved is not None
            assert retrieved.content_hash == 'abc123'
    
    def test_clear_states(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, 'state.json')
            store = FileCrawlStateStore(file_path)
            store.save(CrawlState(url='https://example.com/page1', content_hash='abc'))
            store.clear()
            assert store.get('https://example.com/page1') is None
'''

if __name__ == '__main__':
    with open('tests/test_fetchers/test_sitemap_importer.py', 'w', encoding='utf-8') as f:
        f.write(TEST_CONTENT)
    print('Test file written successfully!')
