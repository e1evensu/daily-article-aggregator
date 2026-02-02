"""
FetcherManager - 统一的 Fetcher 管理器
FetcherManager - Unified Fetcher Manager

管理所有数据源 Fetcher 的并发获取和错误处理。
Manages concurrent fetching and error handling for all data source Fetchers.

需求 Requirements:
- 1.3: RSS 请求失败时记录错误并继续处理其他数据源
- 2.5: 漏洞数据源请求失败时记录错误并继续处理其他数据源
- 3.4: AI 预印本数据源请求失败时记录错误并继续处理其他数据源
- 4.3: 博客 RSS 请求失败时记录错误并继续处理其他数据源
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class FetcherManager:
    """
    统一的 Fetcher 管理器
    Unified Fetcher Manager
    
    管理多个数据源 Fetcher 的并发获取，确保单个源失败不影响其他源。
    Manages concurrent fetching from multiple data sources, ensuring
    single source failure doesn't affect others.
    
    Attributes:
        fetchers: 已注册的 Fetcher 列表
        max_workers: 并发获取的最大线程数
    """
    
    def __init__(self, max_workers: int = 5):
        """
        初始化 Fetcher 管理器
        Initialize Fetcher Manager
        
        Args:
            max_workers: 最大并发线程数 (int, default=5)
        """
        self.fetchers: list[BaseFetcher] = []
        self.max_workers: int = max_workers
    
    def register(self, fetcher: BaseFetcher) -> None:
        """
        注册一个 Fetcher
        Register a Fetcher
        
        Args:
            fetcher: 要注册的 Fetcher 实例
        """
        self.fetchers.append(fetcher)
    
    def register_all(self, fetchers: list[BaseFetcher]) -> None:
        """
        批量注册 Fetcher
        Register multiple Fetchers
        
        Args:
            fetchers: 要注册的 Fetcher 实例列表
        """
        self.fetchers.extend(fetchers)
    
    def fetch_all(self) -> list[FetchResult]:
        """
        并发获取所有启用的数据源
        Fetch from all enabled data sources concurrently
        
        对所有已注册且启用的 Fetcher 并发执行 fetch 操作。
        单个 Fetcher 失败不会影响其他 Fetcher 的执行。
        
        Returns:
            所有 FetchResult 的列表（包括成功和失败的结果）
        """
        # 过滤出启用的 Fetcher
        # Filter enabled Fetchers
        enabled_fetchers = [f for f in self.fetchers if f.is_enabled()]
        
        if not enabled_fetchers:
            logger.warning("No enabled fetchers to run")
            return []
        
        results: list[FetchResult] = []
        
        # 并发获取
        # Concurrent fetching
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_fetcher = {
                executor.submit(self._safe_fetch, fetcher): fetcher
                for fetcher in enabled_fetchers
            }
            
            for future in as_completed(future_to_fetcher):
                fetcher = future_to_fetcher[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result.is_success():
                        logger.info(
                            f"Fetcher {result.source_name} completed: "
                            f"{len(result.items)} items"
                        )
                    else:
                        logger.warning(
                            f"Fetcher {result.source_name} failed: {result.error}"
                        )
                except Exception as e:
                    # 即使 future.result() 抛出异常，也要记录并继续
                    # Even if future.result() raises, log and continue
                    fetcher_name = getattr(fetcher, '__class__', type(fetcher)).__name__
                    logger.error(f"Unexpected error from {fetcher_name}: {str(e)}")
                    results.append(FetchResult(
                        items=[],
                        source_name=fetcher_name,
                        source_type='unknown',
                        error=f"Unexpected error: {str(e)}"
                    ))
        
        # 统计结果
        # Summarize results
        total_items = sum(len(r.items) for r in results)
        success_count = sum(1 for r in results if r.is_success())
        fail_count = len(results) - success_count
        
        logger.info(
            f"FetcherManager completed: {success_count} succeeded, "
            f"{fail_count} failed, {total_items} total items"
        )
        
        return results
    
    def _safe_fetch(self, fetcher: BaseFetcher) -> FetchResult:
        """
        安全地执行 Fetcher 的 fetch 方法
        Safely execute Fetcher's fetch method
        
        捕获所有异常并返回包含错误信息的 FetchResult。
        Catches all exceptions and returns FetchResult with error info.
        
        Args:
            fetcher: 要执行的 Fetcher
        
        Returns:
            FetchResult，成功时包含数据，失败时包含错误信息
        """
        fetcher_name = getattr(fetcher, '__class__', type(fetcher)).__name__
        
        try:
            return fetcher.fetch()
        except Exception as e:
            error_msg = f"Error in {fetcher_name}: {str(e)}"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name=fetcher_name,
                source_type='unknown',
                error=error_msg
            )
    
    def get_all_items(self) -> list[dict[str, Any]]:
        """
        获取所有数据源的条目并合并
        Fetch and merge items from all data sources
        
        Returns:
            所有成功获取的条目列表
        """
        results = self.fetch_all()
        
        all_items: list[dict[str, Any]] = []
        for result in results:
            if result.is_success():
                all_items.extend(result.items)
        
        return all_items


def fetch_with_error_recovery(
    fetchers: list[BaseFetcher],
    max_workers: int = 5
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    带错误恢复的批量获取（独立函数，用于属性测试）
    Batch fetch with error recovery (standalone function for property testing)
    
    Args:
        fetchers: Fetcher 实例列表
        max_workers: 最大并发线程数
    
    Returns:
        (成功获取的条目列表, 错误信息列表) 元组
    
    Examples:
        >>> from src.fetchers.dblp_fetcher import DBLPFetcher
        >>> fetchers = [DBLPFetcher({'enabled': True})]
        >>> items, errors = fetch_with_error_recovery(fetchers)
    """
    manager = FetcherManager(max_workers=max_workers)
    manager.register_all(fetchers)
    
    results = manager.fetch_all()
    
    all_items: list[dict[str, Any]] = []
    errors: list[str] = []
    
    for result in results:
        if result.is_success():
            all_items.extend(result.items)
        else:
            errors.append(result.error or "Unknown error")
    
    return all_items, errors
