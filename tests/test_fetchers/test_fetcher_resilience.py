"""
Fetcher 错误恢复测试
Fetcher Error Resilience Tests

测试 Fetcher 的错误恢复机制，确保单个源失败不影响其他源。
Tests for Fetcher error recovery, ensuring single source failure doesn't affect others.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.fetchers.base import BaseFetcher, FetchResult
from src.fetchers.fetcher_manager import FetcherManager, fetch_with_error_recovery


class MockSuccessFetcher(BaseFetcher):
    """模拟成功的 Fetcher"""
    
    def __init__(self, name: str, items: list):
        self.name = name
        self._items = items
        self._enabled = True
    
    def fetch(self) -> FetchResult:
        return FetchResult(
            items=self._items,
            source_name=self.name,
            source_type='mock'
        )
    
    def is_enabled(self) -> bool:
        return self._enabled


class MockFailingFetcher(BaseFetcher):
    """模拟失败的 Fetcher"""
    
    def __init__(self, name: str, error_msg: str):
        self.name = name
        self.error_msg = error_msg
        self._enabled = True
    
    def fetch(self) -> FetchResult:
        return FetchResult(
            items=[],
            source_name=self.name,
            source_type='mock',
            error=self.error_msg
        )
    
    def is_enabled(self) -> bool:
        return self._enabled


class MockExceptionFetcher(BaseFetcher):
    """模拟抛出异常的 Fetcher"""
    
    def __init__(self, name: str, exception: Exception):
        self.name = name
        self.exception = exception
        self._enabled = True
    
    def fetch(self) -> FetchResult:
        raise self.exception
    
    def is_enabled(self) -> bool:
        return self._enabled


class MockDisabledFetcher(BaseFetcher):
    """模拟禁用的 Fetcher"""
    
    def __init__(self, name: str):
        self.name = name
    
    def fetch(self) -> FetchResult:
        return FetchResult(
            items=[{'title': 'Should not appear'}],
            source_name=self.name,
            source_type='mock'
        )
    
    def is_enabled(self) -> bool:
        return False


class TestFetcherManager:
    """测试 FetcherManager"""
    
    def test_all_success(self):
        """测试所有 Fetcher 都成功的情况"""
        manager = FetcherManager()
        manager.register(MockSuccessFetcher('Source1', [{'title': 'A'}]))
        manager.register(MockSuccessFetcher('Source2', [{'title': 'B'}]))
        
        results = manager.fetch_all()
        
        assert len(results) == 2
        assert all(r.is_success() for r in results)
        assert sum(len(r.items) for r in results) == 2
    
    def test_partial_failure(self):
        """测试部分 Fetcher 失败的情况"""
        manager = FetcherManager()
        manager.register(MockSuccessFetcher('Success', [{'title': 'A'}]))
        manager.register(MockFailingFetcher('Failure', 'Network error'))
        
        results = manager.fetch_all()
        
        assert len(results) == 2
        
        success_results = [r for r in results if r.is_success()]
        fail_results = [r for r in results if not r.is_success()]
        
        assert len(success_results) == 1
        assert len(fail_results) == 1
        assert success_results[0].source_name == 'Success'
        assert fail_results[0].source_name == 'Failure'
    
    def test_exception_handling(self):
        """测试异常处理"""
        manager = FetcherManager()
        manager.register(MockSuccessFetcher('Success', [{'title': 'A'}]))
        manager.register(MockExceptionFetcher('Exception', RuntimeError('Crash!')))
        
        results = manager.fetch_all()
        
        assert len(results) == 2
        
        success_results = [r for r in results if r.is_success()]
        fail_results = [r for r in results if not r.is_success()]
        
        assert len(success_results) == 1
        assert len(fail_results) == 1
    
    def test_disabled_fetchers_skipped(self):
        """测试禁用的 Fetcher 被跳过"""
        manager = FetcherManager()
        manager.register(MockSuccessFetcher('Enabled', [{'title': 'A'}]))
        manager.register(MockDisabledFetcher('Disabled'))
        
        results = manager.fetch_all()
        
        # 只有启用的 Fetcher 被执行
        assert len(results) == 1
        assert results[0].source_name == 'Enabled'
    
    def test_get_all_items(self):
        """测试 get_all_items 方法"""
        manager = FetcherManager()
        manager.register(MockSuccessFetcher('Source1', [{'title': 'A'}]))
        manager.register(MockSuccessFetcher('Source2', [{'title': 'B'}, {'title': 'C'}]))
        manager.register(MockFailingFetcher('Failure', 'Error'))
        
        items = manager.get_all_items()
        
        # 只返回成功获取的条目
        assert len(items) == 3
        titles = [item['title'] for item in items]
        assert 'A' in titles
        assert 'B' in titles
        assert 'C' in titles


class TestFetchWithErrorRecovery:
    """测试 fetch_with_error_recovery 函数"""
    
    def test_basic_recovery(self):
        """测试基本的错误恢复"""
        fetchers = [
            MockSuccessFetcher('Success', [{'title': 'A'}]),
            MockFailingFetcher('Failure', 'Error'),
        ]
        
        items, errors = fetch_with_error_recovery(fetchers)
        
        assert len(items) == 1
        assert len(errors) == 1
        assert items[0]['title'] == 'A'
        assert 'Error' in errors[0]
    
    def test_all_failures(self):
        """测试所有 Fetcher 都失败的情况"""
        fetchers = [
            MockFailingFetcher('Failure1', 'Error1'),
            MockFailingFetcher('Failure2', 'Error2'),
        ]
        
        items, errors = fetch_with_error_recovery(fetchers)
        
        assert len(items) == 0
        assert len(errors) == 2


# =============================================================================
# Property-Based Tests (属性测试)
# =============================================================================

from hypothesis import given, strategies as st, settings


# Strategy for generating mock fetcher configurations
fetcher_config_strategy = st.fixed_dictionaries({
    'name': st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
    'success': st.booleans(),
    'item_count': st.integers(min_value=0, max_value=10),
})


def create_mock_fetcher(config: dict) -> BaseFetcher:
    """根据配置创建模拟 Fetcher"""
    if config['success']:
        items = [{'title': f"Item {i}"} for i in range(config['item_count'])]
        return MockSuccessFetcher(config['name'], items)
    else:
        return MockFailingFetcher(config['name'], f"Error from {config['name']}")


@given(st.lists(fetcher_config_strategy, min_size=1, max_size=10))
@settings(max_examples=100)
def test_property_fetcher_error_resilience(configs: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 1: Fetcher Error Resilience
    
    **Validates: Requirements 1.3, 2.5, 3.4, 4.3**
    
    对于任意配置的数据源集合，当一个或多个源失败时，Aggregator 应成功处理
    所有剩余的源并返回它们的结果，不会中断。
    
    For any set of configured data sources where one or more sources fail to respond,
    the Aggregator SHALL successfully process all remaining sources and return their
    results without interruption.
    """
    # 创建模拟 Fetcher
    fetchers = [create_mock_fetcher(config) for config in configs]
    
    # 执行获取
    items, errors = fetch_with_error_recovery(fetchers)
    
    # 计算预期结果
    expected_success_count = sum(1 for c in configs if c['success'])
    expected_fail_count = sum(1 for c in configs if not c['success'])
    expected_item_count = sum(c['item_count'] for c in configs if c['success'])
    
    # Property: 错误数量应等于失败的 Fetcher 数量
    assert len(errors) == expected_fail_count, \
        f"Error count {len(errors)} should match failed fetcher count {expected_fail_count}"
    
    # Property: 成功获取的条目数量应等于所有成功 Fetcher 的条目总数
    assert len(items) == expected_item_count, \
        f"Item count {len(items)} should match expected {expected_item_count}"
    
    # Property: 即使有失败，也应该返回成功的结果
    if expected_success_count > 0:
        assert len(items) > 0 or expected_item_count == 0, \
            "Should have items from successful fetchers"


@given(st.lists(fetcher_config_strategy, min_size=0, max_size=10))
@settings(max_examples=50)
def test_property_fetcher_manager_completeness(configs: list[dict]):
    """
    Feature: aggregator-advanced-features, Property 1: Fetcher Error Resilience (Manager)
    
    **Validates: Requirements 1.3, 2.5, 3.4, 4.3**
    
    FetcherManager 应该为每个注册的 Fetcher 返回一个结果，无论成功还是失败。
    FetcherManager should return a result for each registered Fetcher,
    regardless of success or failure.
    """
    # 创建模拟 Fetcher
    fetchers = [create_mock_fetcher(config) for config in configs]
    
    manager = FetcherManager()
    manager.register_all(fetchers)
    
    results = manager.fetch_all()
    
    # Property: 结果数量应等于 Fetcher 数量
    assert len(results) == len(fetchers), \
        f"Result count {len(results)} should match fetcher count {len(fetchers)}"
    
    # Property: 每个结果都应该有 source_name
    for result in results:
        assert result.source_name, "Each result should have a source_name"
    
    # Property: 成功的结果应该没有错误
    for result in results:
        if result.is_success():
            assert result.error is None, "Successful result should have no error"
        else:
            assert result.error is not None, "Failed result should have an error"
