"""
频率限制模块

实现基于内存的滑动窗口限流，支持全局和用户级别限制。

Requirements:
    - 5.4: 支持设置问答频率限制
        - 支持配置每分钟最大请求数（默认10次/分钟）
        - 支持全局限制和用户级别限制
        - 超过限制时返回友好提示
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .config import RateLimitConfig
from .models import ErrorResponse


# 全局用户标识，用于全局限流
GLOBAL_USER_ID = "__global__"


@dataclass
class RateLimitResult:
    """
    频率限制检查结果
    
    Attributes:
        allowed: 是否允许请求
        remaining: 剩余请求数
        reset_after: 重置等待时间（秒）
        error: 错误响应（如果被限制）
    """
    allowed: bool
    remaining: int
    reset_after: float
    error: ErrorResponse | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "reset_after": self.reset_after,
        }
        if self.error:
            result["error"] = self.error.to_dict()
        return result


class RateLimiter:
    """
    基于内存的滑动窗口限流器
    
    实现滑动窗口算法进行频率限制，支持全局和用户级别限制。
    使用线程锁确保线程安全。
    
    Attributes:
        global_max_requests_per_minute: 全局每分钟最大请求数
        max_requests_per_minute: 每用户每分钟最大请求数
        window_size: 滑动窗口大小（秒），默认60秒
    
    Example:
        >>> config = RateLimitConfig(requests_per_minute=100, requests_per_user_minute=10)
        >>> limiter = RateLimiter(config)
        >>> result = limiter.is_allowed("user123")
        >>> if result.allowed:
        ...     print(f"Request allowed, {result.remaining} remaining")
        ... else:
        ...     print(f"Rate limited, retry after {result.reset_after}s")
    
    Requirements: 5.4
    """
    
    def __init__(
        self,
        config: RateLimitConfig | None = None,
        global_max_requests_per_minute: int | None = None,
        max_requests_per_minute: int | None = None,
        window_size: int = 60,
    ):
        """
        初始化限流器
        
        Args:
            config: 频率限制配置对象
            global_max_requests_per_minute: 全局每分钟最大请求数（覆盖配置）
            max_requests_per_minute: 每用户每分钟最大请求数（覆盖配置）
            window_size: 滑动窗口大小（秒），默认60秒
        
        Requirements: 5.4
        """
        if config is None:
            config = RateLimitConfig()
        
        # 使用参数覆盖配置值
        self.global_max_requests_per_minute = (
            global_max_requests_per_minute 
            if global_max_requests_per_minute is not None 
            else config.requests_per_minute
        )
        self.max_requests_per_minute = (
            max_requests_per_minute 
            if max_requests_per_minute is not None 
            else config.requests_per_user_minute
        )
        self.window_size = window_size
        
        # 存储每个用户的请求时间戳列表
        # key: user_id, value: list of timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)
        
        # 线程锁，确保线程安全
        self._lock = threading.Lock()
    
    def _cleanup_old_requests(self, user_id: str, current_time: float) -> None:
        """
        清理过期的请求记录
        
        移除滑动窗口之外的旧请求时间戳。
        
        Args:
            user_id: 用户 ID
            current_time: 当前时间戳
        
        Note:
            此方法应在持有锁的情况下调用
        """
        cutoff_time = current_time - self.window_size
        self._requests[user_id] = [
            ts for ts in self._requests[user_id] if ts > cutoff_time
        ]
    
    def _get_request_count(self, user_id: str, current_time: float) -> int:
        """
        获取用户在当前窗口内的请求数
        
        Args:
            user_id: 用户 ID
            current_time: 当前时间戳
            
        Returns:
            当前窗口内的请求数
        
        Note:
            此方法应在持有锁的情况下调用
        """
        self._cleanup_old_requests(user_id, current_time)
        return len(self._requests[user_id])
    
    def _get_reset_time(self, user_id: str, current_time: float) -> float:
        """
        获取限流重置时间
        
        计算最早的请求何时会过期，从而释放一个请求配额。
        
        Args:
            user_id: 用户 ID
            current_time: 当前时间戳
            
        Returns:
            重置等待时间（秒）
        
        Note:
            此方法应在持有锁的情况下调用
        """
        if not self._requests[user_id]:
            return 0.0
        
        oldest_request = min(self._requests[user_id])
        reset_time = oldest_request + self.window_size - current_time
        return max(0.0, reset_time)
    
    def is_allowed(self, user_id: str | None = None) -> RateLimitResult:
        """
        检查请求是否被允许
        
        同时检查全局限制和用户级别限制。如果任一限制被触发，
        则拒绝请求。
        
        Args:
            user_id: 用户 ID，如果为 None 则只检查全局限制
            
        Returns:
            RateLimitResult 包含是否允许、剩余请求数和重置时间
        
        Example:
            >>> limiter = RateLimiter()
            >>> result = limiter.is_allowed("user123")
            >>> result.allowed
            True
            >>> result.remaining
            9
        
        Requirements: 5.4
        """
        current_time = time.time()
        
        with self._lock:
            # 检查全局限制
            global_count = self._get_request_count(GLOBAL_USER_ID, current_time)
            global_remaining = self.global_max_requests_per_minute - global_count
            global_reset = self._get_reset_time(GLOBAL_USER_ID, current_time)
            
            if global_remaining <= 0:
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_after=global_reset,
                    error=ErrorResponse(
                        error_code="RATE_LIMITED",
                        message="系统请求过于频繁，请稍后再试",
                        retry_after=int(global_reset) + 1,
                    ),
                )
            
            # 如果提供了用户 ID，检查用户级别限制
            if user_id is not None:
                user_count = self._get_request_count(user_id, current_time)
                user_remaining = self.max_requests_per_minute - user_count
                user_reset = self._get_reset_time(user_id, current_time)
                
                if user_remaining <= 0:
                    return RateLimitResult(
                        allowed=False,
                        remaining=0,
                        reset_after=user_reset,
                        error=ErrorResponse(
                            error_code="RATE_LIMITED",
                            message="请求过于频繁，请稍后再试",
                            retry_after=int(user_reset) + 1,
                        ),
                    )
                
                # 记录请求
                self._requests[GLOBAL_USER_ID].append(current_time)
                self._requests[user_id].append(current_time)
                
                # 返回用户级别的剩余数（通常更严格）
                return RateLimitResult(
                    allowed=True,
                    remaining=min(global_remaining - 1, user_remaining - 1),
                    reset_after=max(global_reset, user_reset),
                )
            else:
                # 只有全局限制
                self._requests[GLOBAL_USER_ID].append(current_time)
                
                return RateLimitResult(
                    allowed=True,
                    remaining=global_remaining - 1,
                    reset_after=global_reset,
                )
    
    def check(self, user_id: str | None = None) -> bool:
        """
        简化的限流检查方法
        
        只返回是否允许请求，不记录请求。用于预检查。
        
        Args:
            user_id: 用户 ID
            
        Returns:
            是否允许请求
        
        Example:
            >>> limiter = RateLimiter()
            >>> if limiter.check("user123"):
            ...     # 执行请求
            ...     pass
        
        Requirements: 5.4
        """
        current_time = time.time()
        
        with self._lock:
            # 检查全局限制
            global_count = self._get_request_count(GLOBAL_USER_ID, current_time)
            if global_count >= self.global_max_requests_per_minute:
                return False
            
            # 检查用户级别限制
            if user_id is not None:
                user_count = self._get_request_count(user_id, current_time)
                if user_count >= self.max_requests_per_minute:
                    return False
            
            return True
    
    def get_remaining(self, user_id: str | None = None) -> int:
        """
        获取剩余请求数
        
        返回用户在当前窗口内还可以发送的请求数。
        
        Args:
            user_id: 用户 ID，如果为 None 则返回全局剩余数
            
        Returns:
            剩余请求数
        
        Example:
            >>> limiter = RateLimiter()
            >>> limiter.get_remaining("user123")
            10
        
        Requirements: 5.4
        """
        current_time = time.time()
        
        with self._lock:
            global_count = self._get_request_count(GLOBAL_USER_ID, current_time)
            global_remaining = self.global_max_requests_per_minute - global_count
            
            if user_id is not None:
                user_count = self._get_request_count(user_id, current_time)
                user_remaining = self.max_requests_per_minute - user_count
                return min(global_remaining, user_remaining)
            
            return global_remaining
    
    def reset(self, user_id: str | None = None) -> None:
        """
        重置用户的请求记录
        
        清除指定用户的所有请求时间戳。如果 user_id 为 None，
        则重置所有用户的记录（包括全局记录）。
        
        Args:
            user_id: 用户 ID，如果为 None 则重置所有记录
        
        Example:
            >>> limiter = RateLimiter()
            >>> limiter.reset("user123")  # 重置单个用户
            >>> limiter.reset()  # 重置所有
        
        Requirements: 5.4
        """
        with self._lock:
            if user_id is None:
                self._requests.clear()
            else:
                if user_id in self._requests:
                    del self._requests[user_id]
    
    def get_stats(self) -> dict[str, Any]:
        """
        获取限流器统计信息
        
        返回当前限流器的状态统计。
        
        Returns:
            统计信息字典，包含:
                - global_requests: 全局请求数
                - user_count: 活跃用户数
                - total_requests: 总请求数
                - config: 配置信息
        
        Example:
            >>> limiter = RateLimiter()
            >>> stats = limiter.get_stats()
            >>> stats["global_requests"]
            0
        """
        current_time = time.time()
        
        with self._lock:
            # 清理所有用户的过期请求
            for user_id in list(self._requests.keys()):
                self._cleanup_old_requests(user_id, current_time)
            
            global_requests = len(self._requests.get(GLOBAL_USER_ID, []))
            
            # 计算活跃用户数（排除全局标识）
            active_users = [
                uid for uid in self._requests.keys() 
                if uid != GLOBAL_USER_ID and self._requests[uid]
            ]
            
            total_requests = sum(
                len(reqs) for uid, reqs in self._requests.items() 
                if uid != GLOBAL_USER_ID
            )
            
            return {
                "global_requests": global_requests,
                "user_count": len(active_users),
                "total_requests": total_requests,
                "config": {
                    "global_max_requests_per_minute": self.global_max_requests_per_minute,
                    "max_requests_per_minute": self.max_requests_per_minute,
                    "window_size": self.window_size,
                },
            }
