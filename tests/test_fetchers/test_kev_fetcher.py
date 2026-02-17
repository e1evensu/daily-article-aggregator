"""
KEVFetcher 单元测试和属性测试
Unit tests and property-based tests for KEVFetcher

测试 CISA KEV 获取器的各项功能。
Tests for CISA KEV fetcher functionality.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.fetchers.kev_fetcher import KEVFetcher, parse_kev_entry


class TestKEVFetcherInit:
    """测试 KEVFetcher 初始化"""
    
    def test_default_config(self):
        """测试默认配置"""
        fetcher = KEVFetcher({})
        
        assert fetcher.enabled is True
        assert fetcher.days_back == 30
        assert fetcher.timeout == 30
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = {
            'enabled': False,
            'days_back': 60,
            'timeout': 45
        }
        fetcher = KEVFetcher(config)
        
        assert fetcher.enabled is False
        assert fetcher.days_back == 60
        assert fetcher.timeout == 45
    
    def test_is_enabled(self):
        """测试 is_enabled 方法"""
        fetcher_enabled = KEVFetcher({'enabled': True})
        fetcher_disabled = KEVFetcher({'enabled': False})
        
        assert fetcher_enabled.is_enabled() is True
        assert fetcher_disabled.is_enabled() is False


class TestKEVFetcherFetch:
    """测试 KEVFetcher fetch 方法"""
    
    def test_fetch_disabled(self):
        """测试禁用时的 fetch"""
        fetcher = KEVFetcher({'enabled': False})
        result = fetcher.fetch()
        
        assert result.is_success() is False
        assert result.error == 'Fetcher is disabled'
        assert len(result.items) == 0
    
    def test_fetch_with_mock(self):
        """使用 mock 测试 fetch"""
        from datetime import datetime
        # Use a recent date to pass the filter
        recent_date = datetime.now().strftime('%Y-%m-%d')
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'vulnerabilities': [
                {
                    'cveID': 'CVE-2024-1234',
                    'vulnerabilityName': 'Remote Code Execution',
                    'vendorProject': 'Microsoft',
                    'product': 'Windows',
                    'dateAdded': recent_date,
                    'shortDescription': 'A critical vulnerability',
                    'requiredAction': 'Apply updates',
                    'dueDate': '2024-02-15',
                    'knownRansomwareCampaignUse': 'Known'
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('src.fetchers.kev_fetcher.requests.get', return_value=mock_response):
            fetcher = KEVFetcher({'days_back': 30})
            result = fetcher.fetch()
            
            assert result.is_success() is True
            assert result.source_type == 'kev'
            assert len(result.items) == 1
            assert result.items[0]['cve_id'] == 'CVE-2024-1234'
            assert result.items[0]['vendor'] == 'Microsoft'


class TestParseKevEntry:
    """测试 parse_kev_entry 函数"""
    
    def test_parse_complete_entry(self):
        """测试解析完整条目"""
        entry = {
            'cveID': 'CVE-2024-1234',
            'vulnerabilityName': 'Remote Code Execution',
            'vendorProject': 'Microsoft',
            'product': 'Windows',
            'dateAdded': '2024-01-15',
            'shortDescription': 'A critical vulnerability',
            'requiredAction': 'Apply updates',
            'dueDate': '2024-02-15',
            'knownRansomwareCampaignUse': 'Known'
        }
        
        result = parse_kev_entry(entry)
        
        assert result is not None
        assert result['cve_id'] == 'CVE-2024-1234'
        assert result['vulnerability_name'] == 'Remote Code Execution'
        assert result['vendor'] == 'Microsoft'
        assert result['product'] == 'Windows'
        assert result['date_added'] == '2024-01-15'
        assert result['source_type'] == 'kev'
    
    def test_parse_entry_missing_cve_id(self):
        """测试缺少 CVE ID 的条目"""
        entry = {
            'cveID': '',
            'vulnerabilityName': 'Test',
        }
        
        result = parse_kev_entry(entry)
        
        assert result is None
    
    def test_parse_entry_minimal(self):
        """测试最小条目"""
        entry = {
            'cveID': 'CVE-2024-5678',
        }
        
        result = parse_kev_entry(entry)
        
        assert result is not None
        assert result['cve_id'] == 'CVE-2024-5678'
        assert result['vulnerability_name'] == ''
        assert result['vendor'] == ''
        assert result['product'] == ''
    
    def test_parse_entry_title_format(self):
        """测试标题格式"""
        entry_with_name = {
            'cveID': 'CVE-2024-1111',
            'vulnerabilityName': 'SQL Injection',
        }
        entry_without_name = {
            'cveID': 'CVE-2024-2222',
            'vulnerabilityName': '',
        }
        
        result_with = parse_kev_entry(entry_with_name)
        result_without = parse_kev_entry(entry_without_name)
        
        assert result_with['title'] == '[KEV] CVE-2024-1111: SQL Injection'
        assert result_without['title'] == '[KEV] CVE-2024-2222'


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# Strategy for generating valid CVE IDs
cve_id_strategy = st.from_regex(r'CVE-20[0-9]{2}-[0-9]{4,7}', fullmatch=True)

# Strategy for generating valid KEV entries
kev_entry_strategy = st.fixed_dictionaries({
    'cveID': cve_id_strategy,
    'vulnerabilityName': st.text(min_size=0, max_size=200),
    'vendorProject': st.text(min_size=0, max_size=100),
    'product': st.text(min_size=0, max_size=100),
    'dateAdded': st.from_regex(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]', fullmatch=True) | st.just(''),
    'shortDescription': st.text(min_size=0, max_size=500),
    'requiredAction': st.text(min_size=0, max_size=200),
    'dueDate': st.from_regex(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]', fullmatch=True) | st.just(''),
    'knownRansomwareCampaignUse': st.sampled_from(['Known', 'Unknown', '']),
})


@given(kev_entry_strategy)
@settings(max_examples=100)
def test_property_kev_entry_parsing_completeness(entry: dict):
    """
    Feature: aggregator-advanced-features, Property 5: KEV Entry Parsing Completeness
    
    **Validates: Requirements 2.4**
    
    对于任意有效的 CISA KEV JSON 条目，解析器应提取所有必需字段
    （cve_id, vulnerability_name, vendor, product, date_added）且类型正确。
    
    For any valid CISA KEV JSON entry, the parser SHALL extract all required fields
    (cve_id, vulnerability_name, vendor, product, date_added) with correct types.
    """
    result = parse_kev_entry(entry)
    
    # Property: Result should not be None for valid input (has CVE ID)
    assert result is not None, "Valid KEV entry should produce a result"
    
    # Property: CVE ID must be non-empty and match input
    assert result['cve_id'], "CVE ID must be non-empty"
    assert result['cve_id'] == entry['cveID'], \
        f"CVE ID {result['cve_id']} should match input {entry['cveID']}"
    
    # Property: CVE ID must match CVE format
    assert result['cve_id'].startswith('CVE-'), "CVE ID must start with 'CVE-'"
    
    # Property: Vulnerability name must be a string
    assert isinstance(result['vulnerability_name'], str), \
        "Vulnerability name must be a string"
    
    # Property: Vendor must be a string
    assert isinstance(result['vendor'], str), "Vendor must be a string"
    
    # Property: Product must be a string
    assert isinstance(result['product'], str), "Product must be a string"
    
    # Property: Date added must be a string
    assert isinstance(result['date_added'], str), "Date added must be a string"
    
    # Property: If date_added is non-empty, it should be in YYYY-MM-DD format
    if result['date_added']:
        assert len(result['date_added']) == 10, \
            f"Date added {result['date_added']} should be in YYYY-MM-DD format"
        assert result['date_added'][4] == '-' and result['date_added'][7] == '-', \
            "Date added should have dashes in correct positions"
    
    # Property: URL must be properly formatted
    assert result['url'], "URL must be non-empty"
    assert result['url'].startswith('https://nvd.nist.gov/vuln/detail/'), \
        "URL must point to NVD"
    assert result['cve_id'] in result['url'], \
        "URL must contain the CVE ID"
    
    # Property: Source type must be 'kev'
    assert result['source_type'] == 'kev', "Source type must be 'kev'"
    
    # Property: Title must contain CVE ID
    assert result['cve_id'] in result['title'], \
        "Title must contain CVE ID"
    
    # Property: Title must start with [KEV]
    assert result['title'].startswith('[KEV]'), \
        "Title must start with [KEV]"


@given(st.lists(kev_entry_strategy, min_size=0, max_size=20))
@settings(max_examples=50)
def test_property_kev_batch_parsing(entries: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 5: KEV Entry Parsing Completeness (Batch)
    
    **Validates: Requirements 2.4**
    
    对于任意 KEV 条目列表，每个有效的条目都应被正确解析。
    For any list of KEV entries, each valid entry should be correctly parsed.
    """
    for i, entry in enumerate(entries):
        result = parse_kev_entry(entry)
        
        # Property: Each valid entry should produce a result
        assert result is not None, f"KEV entry {i} should produce a result"
        
        # Property: Each result should have required fields
        assert 'cve_id' in result, f"KEV entry {i} result should have cve_id"
        assert 'vulnerability_name' in result, f"KEV entry {i} result should have vulnerability_name"
        assert 'vendor' in result, f"KEV entry {i} result should have vendor"
        assert 'product' in result, f"KEV entry {i} result should have product"
        assert 'date_added' in result, f"KEV entry {i} result should have date_added"
