"""
RateLimiter 属性测试 (Property-Based Tests)

使用 Hypothesis 进行属性测试，验证 RateLimiter 的正确性属性。

Feature: knowledge-qa-bot
Property 9: Rate Limiting Enforcement
**Validates: Requirements 5.4**

Property 9 states:
- For any user making requests, the system SHALL allow at most N requests per 
  minute (where N = configured limit).
- Requests exceeding the limit SHALL be rejected with a friendly error message.
"""

import threading
import time
from typing import Any

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume

from src.qa.rate_limiter import RateLimiter, RateLimitResult, GLOBAL_USER_ID
from src.qa.config import RateLimitConfig


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# User ID strategy - simple alphanumeric
user_id_strategy = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789_'),
    min_size=3,
    max_size=20
).map(lambda x: x.strip() or 'user')

# User limit strategy (requests per user per minute)
user_limit_strategy = st.integers(min_value=1, max_value=20)

# Global limit strategy (requests per minute globally)
global_limit_strategy = st.integers(min_value=1, max_value=100)

# Request count strategy
request_count_strategy = st.integers(min_value=1, max_value=30)

# Multiple users strategy
multiple_users_strategy = st.lists(
    user_id_strategy,
    min_size=1,
    max_size=10,
    unique=True
)


# =============================================================================
# Property 9: Rate Limiting Enforcement
# =============================================================================

class TestUserRateLimitEnforcement:
    """
    Property 9: User Rate Limit Enforcement
    
    For any user making requests, the system SHALL allow at most N requests 
    per minute (where N = configured user limit).
    
    Feature: knowledge-qa-bot, Property 9: User cannot exceed max_requests_per_minute
    **Validates: Requirements 5.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        user_limit=user_limit_strategy,
        request_count=request_count_strategy
    )
    def test_user_cannot_exceed_max_requests_per_minute(self, user_limit, request_count):
        """
        Feature: knowledge-qa-bot, Property 9: User cannot exceed max_requests_per_minute
        **Validates: Requirements 5.4**
        
        Property: For any user, the number of allowed requests SHALL NOT exceed
        the configured max_requests_per_minute limit.
        """
        # Use high global limit to isolate user limit testing
        limiter = RateLimiter(
            global_max_requests_per_minute=1000,
            max_requests_per_minute=user_limit,
            window_size=60
        )
        
        user_id = "test_user"
        accepted_count = 0
        
        # Make requests
        for _ in range(request_count):
            result = limiter.is_allowed(user_id)
            if result.allowed:
                accepted_count += 1
        
        # Verify: accepted requests SHALL NOT exceed user limit
        assert accepted_count <= user_limit, \
            f"Accepted {accepted_count} requests, but user limit is {user_limit}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        user_limit=user_limit_strategy,
        request_count=request_count_strategy
    )
    def test_user_limit_allows_exactly_n_requests(self, user_limit, request_count):
        """
        Feature: knowledge-qa-bot, Property 9: User limit allows exactly N requests
        **Validates: Requirements 5.4**
        
        Property: When a user makes requests, exactly N requests SHALL be allowed
        (where N = min(request_count, user_limit)).
        """
        # Use high global limit to isolate user limit testing
        limiter = RateLimiter(
            global_max_requests_per_minute=1000,
            max_requests_per_minute=user_limit,
            window_size=60
        )
        
        user_id = "test_user"
        accepted_count = 0
        
        # Make requests
        for _ in range(request_count):
            result = limiter.is_allowed(user_id)
            if result.allowed:
                accepted_count += 1
        
        # Verify: exactly min(request_count, user_limit) requests should be accepted
        expected_accepted = min(request_count, user_limit)
        assert accepted_count == expected_accepted, \
            f"Expected {expected_accepted} accepted requests, got {accepted_count}"


class TestGlobalRateLimitEnforcement:
    """
    Property 9: Global Rate Limit Enforcement
    
    The system SHALL enforce a global rate limit across all users.
    
    Feature: knowledge-qa-bot, Property 9: Global limit cannot be exceeded
    **Validates: Requirements 5.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        global_limit=global_limit_strategy,
        users=multiple_users_strategy
    )
    def test_global_limit_cannot_be_exceeded(self, global_limit, users):
        """
        Feature: knowledge-qa-bot, Property 9: Global limit cannot be exceeded
        **Validates: Requirements 5.4**
        
        Property: The total number of allowed requests across all users SHALL NOT
        exceed the configured global limit.
        """
        # Use high user limit to isolate global limit testing
        limiter = RateLimiter(
            global_max_requests_per_minute=global_limit,
            max_requests_per_minute=1000,
            window_size=60
        )
        
        total_accepted = 0
        requests_per_user = (global_limit // len(users)) + 5  # Ensure we exceed global limit
        
        # Each user makes requests
        for user_id in users:
            for _ in range(requests_per_user):
                result = limiter.is_allowed(user_id)
                if result.allowed:
                    total_accepted += 1
        
        # Verify: total accepted requests SHALL NOT exceed global limit
        assert total_accepted <= global_limit, \
            f"Total accepted {total_accepted} requests, but global limit is {global_limit}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(global_limit=global_limit_strategy)
    def test_global_limit_allows_exactly_n_requests(self, global_limit):
        """
        Feature: knowledge-qa-bot, Property 9: Global limit allows exactly N requests
        **Validates: Requirements 5.4**
        
        Property: When requests are made without user ID (global only), exactly N 
        requests SHALL be allowed (where N = global_limit).
        """
        limiter = RateLimiter(
            global_max_requests_per_minute=global_limit,
            max_requests_per_minute=1000,
            window_size=60
        )
        
        accepted_count = 0
        total_requests = global_limit + 10  # Request more than limit
        
        # Make requests without user ID
        for _ in range(total_requests):
            result = limiter.is_allowed(None)
            if result.allowed:
                accepted_count += 1
        
        # Verify: exactly global_limit requests should be accepted
        assert accepted_count == global_limit, \
            f"Expected {global_limit} accepted requests, got {accepted_count}"


class TestRejectedRequestsErrorMessage:
    """
    Property 9: Rejected Requests Error Message
    
    Requests exceeding the limit SHALL be rejected with a friendly error message.
    
    Feature: knowledge-qa-bot, Property 9: Rejected requests have friendly error messages
    **Validates: Requirements 5.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(user_limit=user_limit_strategy)
    def test_rejected_requests_have_friendly_error_message(self, user_limit):
        """
        Feature: knowledge-qa-bot, Property 9: Rejected requests have friendly error messages
        **Validates: Requirements 5.4**
        
        Property: When a request is rejected due to rate limiting, the response
        SHALL include a friendly error message.
        """
        limiter = RateLimiter(
            global_max_requests_per_minute=1000,
            max_requests_per_minute=user_limit,
            window_size=60
        )
        
        user_id = "test_user"
        
        # Exhaust the user's quota
        for _ in range(user_limit):
            limiter.is_allowed(user_id)
        
        # Next request should be rejected
        result = limiter.is_allowed(user_id)
        
        # Verify: rejected request has error with friendly message
        assert result.allowed is False, "Request should be rejected after limit exceeded"
        assert result.error is not None, "Rejected request should have error"
        assert result.error.error_code == "RATE_LIMITED", \
            f"Error code should be RATE_LIMITED, got {result.error.error_code}"
        assert result.error.message is not None and len(result.error.message) > 0, \
            "Error message should not be empty"
        # Verify message is user-friendly (contains Chinese or common phrases)
        assert "请求" in result.error.message or "频繁" in result.error.message or \
               "稍后" in result.error.message or "限" in result.error.message, \
            f"Error message should be user-friendly, got: {result.error.message}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(global_limit=st.integers(min_value=1, max_value=10))
    def test_global_rejection_has_friendly_error_message(self, global_limit):
        """
        Feature: knowledge-qa-bot, Property 9: Global rejection has friendly error message
        **Validates: Requirements 5.4**
        
        Property: When a request is rejected due to global rate limiting, the 
        response SHALL include a friendly error message indicating system-wide limit.
        """
        limiter = RateLimiter(
            global_max_requests_per_minute=global_limit,
            max_requests_per_minute=1000,
            window_size=60
        )
        
        # Exhaust global quota with different users
        for i in range(global_limit):
            limiter.is_allowed(f"user{i}")
        
        # Next request should be rejected due to global limit
        result = limiter.is_allowed("new_user")
        
        # Verify: rejected request has error with friendly message
        assert result.allowed is False, "Request should be rejected after global limit exceeded"
        assert result.error is not None, "Rejected request should have error"
        assert result.error.error_code == "RATE_LIMITED", \
            f"Error code should be RATE_LIMITED, got {result.error.error_code}"
        # Global rejection message should mention "系统" (system)
        assert "系统" in result.error.message, \
            f"Global rejection message should mention system, got: {result.error.message}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(user_limit=user_limit_strategy)
    def test_rejected_requests_include_retry_after(self, user_limit):
        """
        Feature: knowledge-qa-bot, Property 9: Rejected requests include retry_after
        **Validates: Requirements 5.4**
        
        Property: When a request is rejected, the error response SHALL include
        a retry_after value indicating when the user can retry.
        """
        limiter = RateLimiter(
            global_max_requests_per_minute=1000,
            max_requests_per_minute=user_limit,
            window_size=60
        )
        
        user_id = "test_user"
        
        # Exhaust the user's quota
        for _ in range(user_limit):
            limiter.is_allowed(user_id)
        
        # Next request should be rejected
        result = limiter.is_allowed(user_id)
        
        # Verify: rejected request has retry_after
        assert result.allowed is False, "Request should be rejected"
        assert result.error is not None, "Rejected request should have error"
        assert result.error.retry_after is not None, "Error should have retry_after"
        assert result.error.retry_after > 0, \
            f"retry_after should be positive, got {result.error.retry_after}"
        assert result.error.retry_after <= 61, \
            f"retry_after should be at most window_size + 1, got {result.error.retry_after}"


class TestRateLimitWindowReset:
    """
    Property 9: Rate Limit Window Reset
    
    Rate limit SHALL reset after the window expires.
    
    Feature: knowledge-qa-bot, Property 9: Rate limit resets after window expires
    **Validates: Requirements 5.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(user_limit=st.integers(min_value=1, max_value=5))
    def test_rate_limit_resets_after_window_expires(self, user_limit):
        """
        Feature: knowledge-qa-bot, Property 9: Rate limit resets after window expires
        **Validates: Requirements 5.4**
        
        Property: After the rate limit window expires, the user SHALL be able
        to make requests again up to the configured limit.
        """
        # Use a very short window for testing (1 second)
        limiter = RateLimiter(
            global_max_requests_per_minute=1000,
            max_requests_per_minute=user_limit,
            window_size=1  # 1 second window for fast testing
        )
        
        user_id = "test_user"
        
        # Exhaust the user's quota
        for _ in range(user_limit):
            result = limiter.is_allowed(user_id)
            assert result.allowed is True, "Initial requests should be allowed"
        
        # Verify quota is exhausted
        result = limiter.is_allowed(user_id)
        assert result.allowed is False, "Request should be rejected after limit exceeded"
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Verify: user can make requests again
        result = limiter.is_allowed(user_id)
        assert result.allowed is True, \
            "Request should be allowed after window expires"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(user_limit=st.integers(min_value=2, max_value=5))
    def test_sliding_window_partial_reset(self, user_limit):
        """
        Feature: knowledge-qa-bot, Property 9: Sliding window partial reset
        **Validates: Requirements 5.4**
        
        Property: The sliding window mechanism SHALL allow new requests as old
        requests expire, even before the full window resets.
        """
        # Use a 2 second window for testing
        window_size = 2
        limiter = RateLimiter(
            global_max_requests_per_minute=1000,
            max_requests_per_minute=user_limit,
            window_size=window_size
        )
        
        user_id = "test_user"
        
        # Make first request
        result = limiter.is_allowed(user_id)
        assert result.allowed is True, "First request should be allowed"
        
        # Wait half the window
        time.sleep(1.1)
        
        # Make remaining requests to fill quota
        for _ in range(user_limit - 1):
            result = limiter.is_allowed(user_id)
            assert result.allowed is True, "Requests within limit should be allowed"
        
        # Verify quota is exhausted
        result = limiter.is_allowed(user_id)
        assert result.allowed is False, "Request should be rejected after limit exceeded"
        
        # Wait for first request to expire (but not all)
        time.sleep(1.1)
        
        # Verify: one slot should be available due to sliding window
        result = limiter.is_allowed(user_id)
        assert result.allowed is True, \
            "Request should be allowed after oldest request expires"


class TestRemainingCountAccuracy:
    """
    Property 9: Remaining Count Accuracy
    
    The remaining count SHALL accurately reflect available requests.
    
    Feature: knowledge-qa-bot, Property 9: Remaining count is accurate
    **Validates: Requirements 5.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        user_limit=user_limit_strategy,
        request_count=st.integers(min_value=1, max_value=10)
    )
    def test_remaining_count_decreases_correctly(self, user_limit, request_count):
        """
        Feature: knowledge-qa-bot, Property 9: Remaining count decreases correctly
        **Validates: Requirements 5.4**
        
        Property: After each allowed request, the remaining count SHALL decrease
        by exactly 1.
        """
        # Ensure we don't exceed the limit
        actual_requests = min(request_count, user_limit)
        
        limiter = RateLimiter(
            global_max_requests_per_minute=1000,
            max_requests_per_minute=user_limit,
            window_size=60
        )
        
        user_id = "test_user"
        
        # Track remaining counts
        remaining_counts = []
        for _ in range(actual_requests):
            result = limiter.is_allowed(user_id)
            if result.allowed:
                remaining_counts.append(result.remaining)
        
        # Verify: remaining count decreases by 1 after each request
        for i in range(len(remaining_counts) - 1):
            expected_decrease = remaining_counts[i] - remaining_counts[i + 1]
            assert expected_decrease == 1, \
                f"Remaining count should decrease by 1, but decreased by {expected_decrease}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(user_limit=user_limit_strategy)
    def test_remaining_count_reaches_zero_at_limit(self, user_limit):
        """
        Feature: knowledge-qa-bot, Property 9: Remaining count reaches zero at limit
        **Validates: Requirements 5.4**
        
        Property: When the user reaches their limit, the remaining count SHALL be 0.
        """
        limiter = RateLimiter(
            global_max_requests_per_minute=1000,
            max_requests_per_minute=user_limit,
            window_size=60
        )
        
        user_id = "test_user"
        
        # Make requests up to the limit
        last_result = None
        for _ in range(user_limit):
            last_result = limiter.is_allowed(user_id)
        
        # Verify: remaining count is 0 after reaching limit
        assert last_result is not None
        assert last_result.remaining == 0, \
            f"Remaining count should be 0 at limit, got {last_result.remaining}"

