"""
NVDFetcher 单元测试和属性测试
Unit tests and property-based tests for NVDFetcher

测试 NVD API 获取器的各项功能。
Tests for NVD API fetcher functionality.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.fetchers.nvd_fetcher import NVDFetcher, parse_cve


class TestNVDFetcherInit:
    """测试 NVDFetcher 初始化"""
    
    def test_default_config(self):
        """测试默认配置"""
        fetcher = NVDFetcher({})
        
        assert fetcher.enabled is True
        assert fetcher.api_key is None
        assert fetcher.days_back == 7
        assert fetcher.timeout == 60
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = {
            'enabled': False,
            'api_key': 'test-api-key',
            'days_back': 14,
            'timeout': 120
        }
        fetcher = NVDFetcher(config)
        
        assert fetcher.enabled is False
        assert fetcher.api_key == 'test-api-key'
        assert fetcher.days_back == 14
        assert fetcher.timeout == 120
    
    def test_empty_api_key_becomes_none(self):
        """测试空 API 密钥转换为 None"""
        fetcher = NVDFetcher({'api_key': ''})
        assert fetcher.api_key is None
    
    def test_is_enabled(self):
        """测试 is_enabled 方法"""
        fetcher_enabled = NVDFetcher({'enabled': True})
        fetcher_disabled = NVDFetcher({'enabled': False})
        
        assert fetcher_enabled.is_enabled() is True
        assert fetcher_disabled.is_enabled() is False


class TestNVDFetcherFetch:
    """测试 NVDFetcher fetch 方法"""
    
    def test_fetch_disabled(self):
        """测试禁用时的 fetch"""
        fetcher = NVDFetcher({'enabled': False})
        result = fetcher.fetch()
        
        assert result.is_success() is False
        assert result.error == 'Fetcher is disabled'
        assert len(result.items) == 0
    
    def test_fetch_with_mock(self):
        """使用 mock 测试 fetch"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'vulnerabilities': [
                {
                    'cve': {
                        'id': 'CVE-2024-1234',
                        'descriptions': [
                            {'lang': 'en', 'value': 'A test vulnerability'}
                        ],
                        'metrics': {
                            'cvssMetricV31': [{
                                'cvssData': {
                                    'baseScore': 7.5,
                                    'vectorString': 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H'
                                }
                            }]
                        },
                        'published': '2024-01-15T00:00:00.000'
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('src.fetchers.nvd_fetcher.requests.get', return_value=mock_response):
            fetcher = NVDFetcher({})
            result = fetcher.fetch()
            
            assert result.is_success() is True
            assert result.source_type == 'nvd'
            assert len(result.items) == 1
            assert result.items[0]['cve_id'] == 'CVE-2024-1234'
            assert result.items[0]['cvss_score'] == 7.5


class TestParseCve:
    """测试 parse_cve 函数"""
    
    def test_parse_complete_cve(self):
        """测试解析完整 CVE"""
        cve_item = {
            'id': 'CVE-2024-1234',
            'descriptions': [
                {'lang': 'en', 'value': 'A test vulnerability in product X'}
            ],
            'metrics': {
                'cvssMetricV31': [{
                    'cvssData': {
                        'baseScore': 7.5,
                        'vectorString': 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H'
                    }
                }]
            },
            'published': '2024-01-15T00:00:00.000',
            'configurations': [{
                'nodes': [{
                    'cpeMatch': [{
                        'criteria': 'cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*'
                    }]
                }]
            }]
        }
        
        result = parse_cve(cve_item)
        
        assert result is not None
        assert result['cve_id'] == 'CVE-2024-1234'
        assert result['description'] == 'A test vulnerability in product X'
        assert result['cvss_score'] == 7.5
        assert result['published_date'] == '2024-01-15'
        assert 'vendor:product' in result['affected_products']
        assert result['source_type'] == 'nvd'
    
    def test_parse_cve_missing_id(self):
        """测试缺少 ID 的 CVE"""
        cve_item = {
            'id': '',
            'descriptions': [{'lang': 'en', 'value': 'Test'}]
        }
        
        result = parse_cve(cve_item)
        
        assert result is None
    
    def test_parse_cve_no_cvss(self):
        """测试没有 CVSS 评分的 CVE"""
        cve_item = {
            'id': 'CVE-2024-5678',
            'descriptions': [{'lang': 'en', 'value': 'Test vulnerability'}],
            'metrics': {},
            'published': '2024-01-20T00:00:00.000'
        }
        
        result = parse_cve(cve_item)
        
        assert result is not None
        assert result['cve_id'] == 'CVE-2024-5678'
        assert result['cvss_score'] is None
        assert result['cvss_vector'] is None
    
    def test_parse_cve_cvss_v2_fallback(self):
        """测试 CVSS 2.0 回退"""
        cve_item = {
            'id': 'CVE-2024-9999',
            'descriptions': [{'lang': 'en', 'value': 'Old vulnerability'}],
            'metrics': {
                'cvssMetricV2': [{
                    'cvssData': {
                        'baseScore': 5.0,
                        'vectorString': 'AV:N/AC:L/Au:N/C:N/I:N/A:P'
                    }
                }]
            },
            'published': '2024-01-25T00:00:00.000'
        }
        
        result = parse_cve(cve_item)
        
        assert result is not None
        assert result['cvss_score'] == 5.0
    
    def test_parse_cve_non_english_description(self):
        """测试非英文描述回退"""
        cve_item = {
            'id': 'CVE-2024-1111',
            'descriptions': [
                {'lang': 'es', 'value': 'Una vulnerabilidad de prueba'}
            ],
            'metrics': {},
            'published': '2024-01-30T00:00:00.000'
        }
        
        result = parse_cve(cve_item)
        
        assert result is not None
        assert result['description'] == 'Una vulnerabilidad de prueba'


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# Strategy for generating valid CVE IDs
cve_id_strategy = st.from_regex(r'CVE-20[0-9]{2}-[0-9]{4,7}', fullmatch=True)

# Strategy for generating valid CVSS scores
cvss_score_strategy = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)

# Strategy for generating valid CVE items
cve_item_strategy = st.fixed_dictionaries({
    'id': cve_id_strategy,
    'descriptions': st.lists(
        st.fixed_dictionaries({
            'lang': st.sampled_from(['en', 'es', 'fr', 'de']),
            'value': st.text(min_size=1, max_size=500).filter(lambda s: s.strip())
        }),
        min_size=1,
        max_size=3
    ),
    'metrics': st.fixed_dictionaries({
        'cvssMetricV31': st.lists(
            st.fixed_dictionaries({
                'cvssData': st.fixed_dictionaries({
                    'baseScore': cvss_score_strategy,
                    'vectorString': st.just('CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H')
                })
            }),
            min_size=0,
            max_size=1
        )
    }),
    'published': st.from_regex(r'20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]\.[0-9]{3}', fullmatch=True),
    'configurations': st.just([]),  # Simplified for testing
})


@given(cve_item_strategy)
@settings(max_examples=100)
def test_property_cve_parsing_completeness(cve_item: dict):
    """
    Feature: aggregator-advanced-features, Property 4: CVE Parsing Completeness
    
    **Validates: Requirements 2.2**
    
    对于任意有效的 NVD CVE JSON 对象，解析器应提取所有必需字段
    （cve_id, description, cvss_score, published_date, affected_products）且类型正确。
    
    For any valid NVD CVE JSON object, the parser SHALL extract all required fields
    (cve_id, description, cvss_score, published_date, affected_products) with correct types.
    """
    result = parse_cve(cve_item)
    
    # Property: Result should not be None for valid input
    assert result is not None, "Valid CVE item should produce a result"
    
    # Property: CVE ID must be non-empty and match input
    assert result['cve_id'], "CVE ID must be non-empty"
    assert result['cve_id'] == cve_item['id'], \
        f"CVE ID {result['cve_id']} should match input {cve_item['id']}"
    
    # Property: CVE ID must match CVE format
    assert result['cve_id'].startswith('CVE-'), "CVE ID must start with 'CVE-'"
    
    # Property: Description must be a string (can be empty if no descriptions)
    assert isinstance(result['description'], str), "Description must be a string"
    
    # Property: If descriptions exist, description should be non-empty
    if cve_item.get('descriptions'):
        assert result['description'], "Description should be non-empty when descriptions exist"
    
    # Property: CVSS score must be None or a valid float in range [0, 10]
    if result['cvss_score'] is not None:
        assert isinstance(result['cvss_score'], (int, float)), \
            "CVSS score must be a number"
        assert 0.0 <= result['cvss_score'] <= 10.0, \
            f"CVSS score {result['cvss_score']} must be in range [0, 10]"
    
    # Property: Published date must be a string in YYYY-MM-DD format or empty
    assert isinstance(result['published_date'], str), "Published date must be a string"
    if result['published_date']:
        assert len(result['published_date']) == 10, \
            f"Published date {result['published_date']} should be in YYYY-MM-DD format"
        assert result['published_date'][4] == '-' and result['published_date'][7] == '-', \
            "Published date should have dashes in correct positions"
    
    # Property: Affected products must be a list
    assert isinstance(result['affected_products'], list), \
        "Affected products must be a list"
    
    # Property: URL must be properly formatted
    assert result['url'], "URL must be non-empty"
    assert result['url'].startswith('https://nvd.nist.gov/vuln/detail/'), \
        "URL must point to NVD"
    assert result['cve_id'] in result['url'], \
        "URL must contain the CVE ID"
    
    # Property: Source type must be 'nvd'
    assert result['source_type'] == 'nvd', "Source type must be 'nvd'"


@given(st.lists(cve_item_strategy, min_size=0, max_size=20))
@settings(max_examples=50)
def test_property_cve_batch_parsing(cve_items: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 4: CVE Parsing Completeness (Batch)
    
    **Validates: Requirements 2.2**
    
    对于任意 CVE 列表，每个有效的 CVE 都应被正确解析。
    For any list of CVEs, each valid CVE should be correctly parsed.
    """
    for i, cve_item in enumerate(cve_items):
        result = parse_cve(cve_item)
        
        # Property: Each valid CVE should produce a result
        assert result is not None, f"CVE item {i} should produce a result"
        
        # Property: Each result should have required fields
        assert 'cve_id' in result, f"CVE item {i} result should have cve_id"
        assert 'description' in result, f"CVE item {i} result should have description"
        assert 'cvss_score' in result, f"CVE item {i} result should have cvss_score"
        assert 'published_date' in result, f"CVE item {i} result should have published_date"
        assert 'affected_products' in result, f"CVE item {i} result should have affected_products"
