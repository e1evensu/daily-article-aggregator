"""
RateLimiter 单元测试

测试频率限制器的核心功能：
- 用户级别限流
- 全局限流
- 滑动窗口机制
- 重置功能
- 统计信息

Requirements: 5.4
"""

import time
import threading
import pytest
from unittest.mock import patch

from src.qa.rate_limiter import RateLimiter, RateLimitResult, GLOBAL_USER_ID
from src.qa.config import RateLimitConfig


class TestRateLimiterBasic:
    """基本功能测试"""
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        limiter = RateLimiter()
        
        assert limiter.global_max_requests_per_minute == 20
        assert limiter.max_requests_per_minute == 5
        assert limiter.window_size == 60
    
    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=10
        )
        limiter = RateLimiter(config)
        
        assert limiter.global_max_requests_per_minute == 100
        assert limiter.max_requests_per_minute == 10
    
    def test_init_with_override_params(self):
        """测试参数覆盖配置"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=10
        )
        limiter = RateLimiter(
            config,
            global_max_requests_per_minute=50,
            max_requests_per_minute=5
        )
        
        assert limiter.global_max_requests_per_minute == 50
        assert limiter.max_requests_per_minute == 5
    
    def test_first_request_allowed(self):
        """测试第一个请求应该被允许"""
        limiter = RateLimiter()
        result = limiter.is_allowed("user1")
        
        assert result.allowed is True
        assert result.remaining >= 0
        assert result.error is None
    
    def test_is_allowed_returns_rate_limit_result(self):
        """测试 is_allowed 返回 RateLimitResult"""
        limiter = RateLimiter()
        result = limiter.is_allowed("user1")
        
        assert isinstance(result, RateLimitResult)
        assert hasattr(result, 'allowed')
        assert hasattr(result, 'remaining')
        assert hasattr(result, 'reset_after')
        assert hasattr(result, 'error')


class TestUserLevelRateLimiting:
    """用户级别限流测试"""
    
    def test_user_limit_enforced(self):
        """测试用户级别限制被正确执行"""
        config = RateLimitConfig(
            requests_per_minute=100,  # 高全局限制
            requests_per_user_minute=3  # 低用户限制
        )
        limiter = RateLimiter(config)
        
        # 前3个请求应该被允许
        for i in range(3):
            result = limiter.is_allowed("user1")
            assert result.allowed is True, f"Request {i+1} should be allowed"
        
        # 第4个请求应该被拒绝
        result = limiter.is_allowed("user1")
        assert result.allowed is False
        assert result.error is not None
        assert result.error.error_code == "RATE_LIMITED"
    
    def test_different_users_independent(self):
        """测试不同用户的限制是独立的"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=2
        )
        limiter = RateLimiter(config)
        
        # user1 用完配额
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")
        result = limiter.is_allowed("user1")
        assert result.allowed is False
        
        # user2 应该仍然可以请求
        result = limiter.is_allowed("user2")
        assert result.allowed is True
    
    def test_remaining_count_decreases(self):
        """测试剩余请求数正确递减"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=5
        )
        limiter = RateLimiter(config)
        
        result1 = limiter.is_allowed("user1")
        result2 = limiter.is_allowed("user1")
        
        # 剩余数应该递减
        assert result2.remaining < result1.remaining


class TestGlobalRateLimiting:
    """全局限流测试"""
    
    def test_global_limit_enforced(self):
        """测试全局限制被正确执行"""
        config = RateLimitConfig(
            requests_per_minute=3,  # 低全局限制
            requests_per_user_minute=10  # 高用户限制
        )
        limiter = RateLimiter(config)
        
        # 前3个请求应该被允许（来自不同用户）
        for i in range(3):
            result = limiter.is_allowed(f"user{i}")
            assert result.allowed is True
        
        # 第4个请求应该被拒绝（全局限制）
        result = limiter.is_allowed("user4")
        assert result.allowed is False
        assert "系统请求过于频繁" in result.error.message
    
    def test_global_only_request(self):
        """测试只有全局限制的请求（无用户ID）"""
        config = RateLimitConfig(
            requests_per_minute=2,
            requests_per_user_minute=10
        )
        limiter = RateLimiter(config)
        
        # 前2个请求应该被允许
        result1 = limiter.is_allowed(None)
        result2 = limiter.is_allowed(None)
        assert result1.allowed is True
        assert result2.allowed is True
        
        # 第3个请求应该被拒绝
        result3 = limiter.is_allowed(None)
        assert result3.allowed is False


class TestSlidingWindow:
    """滑动窗口机制测试"""
    
    def test_requests_expire_after_window(self):
        """测试请求在窗口过期后被清理"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=2
        )
        # 使用1秒的窗口便于测试
        limiter = RateLimiter(config, window_size=1)
        
        # 用完配额
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")
        result = limiter.is_allowed("user1")
        assert result.allowed is False
        
        # 等待窗口过期
        time.sleep(1.1)
        
        # 现在应该可以请求了
        result = limiter.is_allowed("user1")
        assert result.allowed is True
    
    def test_reset_after_time_is_correct(self):
        """测试重置时间计算正确"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=1
        )
        limiter = RateLimiter(config, window_size=60)
        
        # 发送一个请求
        limiter.is_allowed("user1")
        
        # 第二个请求被拒绝
        result = limiter.is_allowed("user1")
        assert result.allowed is False
        
        # reset_after 应该接近 60 秒
        assert 0 < result.reset_after <= 60


class TestCheckMethod:
    """check 方法测试"""
    
    def test_check_does_not_record_request(self):
        """测试 check 方法不记录请求"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=2
        )
        limiter = RateLimiter(config)
        
        # 多次调用 check 不应该消耗配额
        for _ in range(10):
            assert limiter.check("user1") is True
        
        # 实际请求仍然可以
        result = limiter.is_allowed("user1")
        assert result.allowed is True
    
    def test_check_returns_false_when_limited(self):
        """测试 check 在限流时返回 False"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=1
        )
        limiter = RateLimiter(config)
        
        # 用完配额
        limiter.is_allowed("user1")
        
        # check 应该返回 False
        assert limiter.check("user1") is False


class TestGetRemaining:
    """get_remaining 方法测试"""
    
    def test_get_remaining_initial(self):
        """测试初始剩余数"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=5
        )
        limiter = RateLimiter(config)
        
        remaining = limiter.get_remaining("user1")
        assert remaining == 5  # 用户限制更严格
    
    def test_get_remaining_decreases(self):
        """测试剩余数递减"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=5
        )
        limiter = RateLimiter(config)
        
        initial = limiter.get_remaining("user1")
        limiter.is_allowed("user1")
        after = limiter.get_remaining("user1")
        
        assert after == initial - 1
    
    def test_get_remaining_global_only(self):
        """测试只获取全局剩余数"""
        config = RateLimitConfig(
            requests_per_minute=10,
            requests_per_user_minute=5
        )
        limiter = RateLimiter(config)
        
        remaining = limiter.get_remaining(None)
        assert remaining == 10


class TestReset:
    """reset 方法测试"""
    
    def test_reset_single_user(self):
        """测试重置单个用户"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=2
        )
        limiter = RateLimiter(config)
        
        # 用完 user1 的配额
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")
        assert limiter.check("user1") is False
        
        # 重置 user1
        limiter.reset("user1")
        
        # user1 现在可以请求了
        assert limiter.check("user1") is True
    
    def test_reset_all_users(self):
        """测试重置所有用户"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=1
        )
        limiter = RateLimiter(config)
        
        # 多个用户用完配额
        limiter.is_allowed("user1")
        limiter.is_allowed("user2")
        assert limiter.check("user1") is False
        assert limiter.check("user2") is False
        
        # 重置所有
        limiter.reset()
        
        # 所有用户现在可以请求了
        assert limiter.check("user1") is True
        assert limiter.check("user2") is True


class TestGetStats:
    """get_stats 方法测试"""
    
    def test_get_stats_initial(self):
        """测试初始统计信息"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=10
        )
        limiter = RateLimiter(config)
        
        stats = limiter.get_stats()
        
        assert stats["global_requests"] == 0
        assert stats["user_count"] == 0
        assert stats["total_requests"] == 0
        assert stats["config"]["global_max_requests_per_minute"] == 100
        assert stats["config"]["max_requests_per_minute"] == 10
    
    def test_get_stats_after_requests(self):
        """测试请求后的统计信息"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=10
        )
        limiter = RateLimiter(config)
        
        # 发送一些请求
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")
        limiter.is_allowed("user2")
        
        stats = limiter.get_stats()
        
        assert stats["global_requests"] == 3
        assert stats["user_count"] == 2
        assert stats["total_requests"] == 3


class TestThreadSafety:
    """线程安全测试"""
    
    def test_concurrent_requests(self):
        """测试并发请求的线程安全性"""
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_user_minute=50
        )
        limiter = RateLimiter(config)
        
        results = []
        errors = []
        
        def make_request(user_id):
            try:
                result = limiter.is_allowed(user_id)
                results.append(result.allowed)
            except Exception as e:
                errors.append(e)
        
        # 创建多个线程同时请求
        threads = []
        for i in range(20):
            t = threading.Thread(target=make_request, args=(f"user{i % 5}",))
            threads.append(t)
        
        # 启动所有线程
        for t in threads:
            t.start()
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        # 不应该有错误
        assert len(errors) == 0
        # 应该有20个结果
        assert len(results) == 20


class TestRateLimitResult:
    """RateLimitResult 测试"""
    
    def test_to_dict(self):
        """测试转换为字典"""
        result = RateLimitResult(
            allowed=True,
            remaining=5,
            reset_after=30.0,
            error=None
        )
        
        d = result.to_dict()
        
        assert d["allowed"] is True
        assert d["remaining"] == 5
        assert d["reset_after"] == 30.0
        assert "error" not in d
    
    def test_to_dict_with_error(self):
        """测试带错误的转换"""
        from src.qa.models import ErrorResponse
        
        error = ErrorResponse(
            error_code="RATE_LIMITED",
            message="请求过于频繁",
            retry_after=30
        )
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_after=30.0,
            error=error
        )
        
        d = result.to_dict()
        
        assert d["allowed"] is False
        assert "error" in d
        assert d["error"]["error_code"] == "RATE_LIMITED"


class TestEdgeCases:
    """边界情况测试"""
    
    def test_zero_limit(self):
        """测试零限制"""
        limiter = RateLimiter(
            global_max_requests_per_minute=0,
            max_requests_per_minute=0
        )
        
        # 所有请求都应该被拒绝
        result = limiter.is_allowed("user1")
        assert result.allowed is False
    
    def test_very_high_limit(self):
        """测试非常高的限制"""
        limiter = RateLimiter(
            global_max_requests_per_minute=1000000,
            max_requests_per_minute=1000000
        )
        
        # 大量请求应该都被允许
        for i in range(100):
            result = limiter.is_allowed(f"user{i}")
            assert result.allowed is True
    
    def test_empty_user_id(self):
        """测试空用户ID"""
        limiter = RateLimiter()
        
        # 空字符串作为用户ID应该正常工作
        result = limiter.is_allowed("")
        assert result.allowed is True
