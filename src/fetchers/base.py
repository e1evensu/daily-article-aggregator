"""
BaseFetcher - Fetcher 基类和 FetchResult 数据类
BaseFetcher - Base Fetcher Class and FetchResult Data Class

定义所有数据源 Fetcher 的统一接口和获取结果的数据结构。
Defines the unified interface for all data source Fetchers and the data structure for fetch results.

需求 Requirements:
- 1.1: 安全四大顶会数据源 - 统一 Fetcher 接口
- 2.1: 漏洞数据库数据源 - 统一 Fetcher 接口
- 3.1: AI 领域预印本数据源 - 统一 Fetcher 接口
- 4.1: 大厂博客数据源 - 统一 Fetcher 接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FetchResult:
    """
    获取结果数据类
    Fetch Result Data Class
    
    封装 Fetcher 获取数据的结果，包括获取的条目列表、数据源信息和错误信息。
    Encapsulates the result of a Fetcher's data retrieval, including fetched items,
    source information, and error details.
    
    Attributes:
        items: 获取的条目列表，每个条目为字典格式
               List of fetched items, each item is a dictionary
        source_name: 数据源名称，如 'IEEE S&P', 'NVD', 'HuggingFace Papers'
                     Name of the data source
        source_type: 数据源类型，如 'dblp', 'nvd', 'kev', 'huggingface', 'pwc', 'blog'
                     Type of the data source
        error: 错误信息（如有），获取成功时为 None
               Error message if any, None when fetch is successful
    
    Examples:
        >>> # 成功获取的结果
        >>> result = FetchResult(
        ...     items=[{'title': 'Paper 1', 'url': 'https://example.com/1'}],
        ...     source_name='IEEE S&P',
        ...     source_type='dblp'
        ... )
        >>> result.error is None
        True
        >>> len(result.items)
        1
        
        >>> # 获取失败的结果
        >>> error_result = FetchResult(
        ...     items=[],
        ...     source_name='NVD',
        ...     source_type='nvd',
        ...     error='Connection timeout'
        ... )
        >>> error_result.error
        'Connection timeout'
    """
    items: list[dict[str, Any]] = field(default_factory=list)
    source_name: str = ""
    source_type: str = ""
    error: str | None = None
    
    def is_success(self) -> bool:
        """
        检查获取是否成功
        Check if the fetch was successful
        
        Returns:
            True 如果没有错误，False 如果有错误
            True if no error, False if there is an error
        
        Examples:
            >>> result = FetchResult(items=[], source_name='Test', source_type='test')
            >>> result.is_success()
            True
            >>> error_result = FetchResult(items=[], source_name='Test', source_type='test', error='Failed')
            >>> error_result.is_success()
            False
        """
        return self.error is None
    
    def __len__(self) -> int:
        """
        返回获取的条目数量
        Return the number of fetched items
        
        Returns:
            条目数量
            Number of items
        
        Examples:
            >>> result = FetchResult(
            ...     items=[{'title': 'A'}, {'title': 'B'}],
            ...     source_name='Test',
            ...     source_type='test'
            ... )
            >>> len(result)
            2
        """
        return len(self.items)


class BaseFetcher(ABC):
    """
    Fetcher 抽象基类
    Abstract Base Class for Fetchers
    
    定义所有数据源 Fetcher 必须实现的接口。所有新的数据源 Fetcher（如 DBLPFetcher、
    NVDFetcher、KEVFetcher 等）都应继承此基类并实现抽象方法。
    
    Defines the interface that all data source Fetchers must implement. All new
    data source Fetchers (such as DBLPFetcher, NVDFetcher, KEVFetcher, etc.)
    should inherit from this base class and implement the abstract methods.
    
    设计原则 Design Principles:
    - 统一接口：所有 Fetcher 通过相同的 fetch() 方法获取数据
    - 可配置性：通过 is_enabled() 方法支持配置启用/禁用
    - 容错性：fetch() 返回 FetchResult，错误信息通过 error 字段传递
    
    Examples:
        >>> from src.fetchers.base import BaseFetcher, FetchResult
        >>> 
        >>> class MyFetcher(BaseFetcher):
        ...     def __init__(self, config: dict):
        ...         self.enabled = config.get('enabled', True)
        ...     
        ...     def fetch(self) -> FetchResult:
        ...         if not self.is_enabled():
        ...             return FetchResult(
        ...                 items=[],
        ...                 source_name='MySource',
        ...                 source_type='my_type',
        ...                 error='Fetcher is disabled'
        ...             )
        ...         # 实际获取逻辑
        ...         return FetchResult(
        ...             items=[{'title': 'Item 1'}],
        ...             source_name='MySource',
        ...             source_type='my_type'
        ...         )
        ...     
        ...     def is_enabled(self) -> bool:
        ...         return self.enabled
    """
    
    @abstractmethod
    def fetch(self) -> FetchResult:
        """
        获取数据
        Fetch data from the data source
        
        从数据源获取数据并返回 FetchResult。实现类应处理所有可能的异常，
        并通过 FetchResult.error 字段报告错误，而不是抛出异常。
        
        Fetches data from the data source and returns a FetchResult. Implementations
        should handle all possible exceptions and report errors through the
        FetchResult.error field instead of raising exceptions.
        
        Returns:
            FetchResult: 包含获取的条目列表、数据源信息和可能的错误信息
                        Contains fetched items, source information, and possible error
        
        Note:
            - 即使获取失败，也应返回 FetchResult 而不是抛出异常
            - 错误信息应通过 FetchResult.error 字段传递
            - items 列表中的每个条目应为字典格式，包含数据源特定的字段
        """
        pass
    
    @abstractmethod
    def is_enabled(self) -> bool:
        """
        检查 Fetcher 是否启用
        Check if the Fetcher is enabled
        
        根据配置检查此 Fetcher 是否应该执行获取操作。这允许用户通过配置
        文件启用或禁用特定的数据源。
        
        Checks if this Fetcher should perform fetch operations based on configuration.
        This allows users to enable or disable specific data sources through the
        configuration file.
        
        Returns:
            bool: True 如果 Fetcher 已启用，False 如果已禁用
                 True if the Fetcher is enabled, False if disabled
        
        Examples:
            >>> fetcher = SomeFetcher(config={'enabled': True})
            >>> fetcher.is_enabled()
            True
            >>> fetcher = SomeFetcher(config={'enabled': False})
            >>> fetcher.is_enabled()
            False
        """
        pass
