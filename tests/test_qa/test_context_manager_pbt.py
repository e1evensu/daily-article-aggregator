"""
ContextManager 属性测试 (Property-Based Tests)

使用 Hypothesis 进行属性测试，验证 ContextManager 的正确性属性。

Feature: knowledge-qa-bot
Property 5: Context Management Preservation
**Validates: Requirements 2.4**

Property 5 states:
- For any sequence of conversation turns added for a user, the context SHALL 
  preserve the most recent N turns (where N = max_history) in chronological order.
- Context SHALL expire after the configured TTL.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Any

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume

from src.qa.context_manager import ContextManager


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# Simple alphanumeric text strategy to avoid slow filtering
alphanumeric_text = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '),
    min_size=1,
    max_size=50
).map(lambda x: x.strip() or 'default')

# User ID strategy - simple alphanumeric
user_id_strategy = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789_'),
    min_size=3,
    max_size=20
).map(lambda x: x.strip() or 'user')

# Conversation turn strategy (query, answer pair)
turn_strategy = st.tuples(alphanumeric_text, alphanumeric_text)

# List of turns strategy
turns_list_strategy = st.lists(turn_strategy, min_size=1, max_size=15)

# Max history configuration strategy
max_history_strategy = st.integers(min_value=1, max_value=10)


# =============================================================================
# Property 5: Context Management Preservation
# =============================================================================

class TestContextManagementPreservation:
    """
    Property 5: Context Management Preservation
    
    For any sequence of conversation turns added for a user, the context SHALL 
    preserve the most recent N turns (where N = max_history) in chronological 
    order, and older turns SHALL be discarded.
    
    Feature: knowledge-qa-bot, Property 5: Context preserves recent history
    **Validates: Requirements 2.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        turns=turns_list_strategy,
        max_history=max_history_strategy
    )
    def test_context_preserves_most_recent_n_turns(self, turns, max_history):
        """
        Feature: knowledge-qa-bot, Property 5: Context preserves most recent N turns
        **Validates: Requirements 2.4**
        
        Property: For any sequence of conversation turns added for a user, 
        retrieving the context SHALL return the most recent N turns (where N 
        is the configured max_history).
        """
        manager = ContextManager(max_history=max_history, ttl_minutes=30)
        user_id = "test_user"
        
        # Add all turns
        for query, answer in turns:
            manager.add_turn(user_id, query, answer)
        
        # Get context
        context = manager.get_context(user_id)
        
        # Calculate expected count
        expected_count = min(len(turns), max_history)
        
        # Verify the number of turns preserved
        assert len(context) == expected_count, \
            f"Expected {expected_count} turns, got {len(context)}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        turns=turns_list_strategy,
        max_history=max_history_strategy
    )
    def test_context_preserves_chronological_order(self, turns, max_history):
        """
        Feature: knowledge-qa-bot, Property 5: Context preserves chronological order
        **Validates: Requirements 2.4**
        
        Property: The context SHALL preserve turns in chronological order 
        (oldest first, newest last).
        """
        manager = ContextManager(max_history=max_history, ttl_minutes=30)
        user_id = "test_user"
        
        # Add all turns
        for query, answer in turns:
            manager.add_turn(user_id, query, answer)
        
        # Get context
        context = manager.get_context(user_id)
        
        if len(context) == 0:
            return  # Nothing to verify
        
        # Verify chronological order by checking timestamps
        timestamps = [turn["timestamp"] for turn in context]
        for i in range(len(timestamps) - 1):
            # Parse ISO format timestamps
            t1 = datetime.fromisoformat(timestamps[i])
            t2 = datetime.fromisoformat(timestamps[i + 1])
            assert t1 <= t2, \
                f"Turns should be in chronological order: {t1} should be <= {t2}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        turns=turns_list_strategy,
        max_history=max_history_strategy
    )
    def test_context_discards_older_turns(self, turns, max_history):
        """
        Feature: knowledge-qa-bot, Property 5: Context discards older turns
        **Validates: Requirements 2.4**
        
        Property: When more than max_history turns are added, older turns 
        SHALL be discarded and only the most recent N turns SHALL be preserved.
        """
        # Only test when we have more turns than max_history
        assume(len(turns) > max_history)
        
        manager = ContextManager(max_history=max_history, ttl_minutes=30)
        user_id = "test_user"
        
        # Add all turns
        for query, answer in turns:
            manager.add_turn(user_id, query, answer)
        
        # Get context
        context = manager.get_context(user_id)
        
        # Verify only max_history turns are preserved
        assert len(context) == max_history, \
            f"Expected exactly {max_history} turns, got {len(context)}"
        
        # Verify the preserved turns are the most recent ones
        expected_turns = turns[-max_history:]
        for i, (expected_query, expected_answer) in enumerate(expected_turns):
            assert context[i]["query"] == expected_query, \
                f"Turn {i}: expected query '{expected_query}', got '{context[i]['query']}'"
            assert context[i]["answer"] == expected_answer, \
                f"Turn {i}: expected answer '{expected_answer}', got '{context[i]['answer']}'"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        turns=turns_list_strategy,
        max_history=max_history_strategy
    )
    def test_context_content_integrity(self, turns, max_history):
        """
        Feature: knowledge-qa-bot, Property 5: Context content integrity
        **Validates: Requirements 2.4**
        
        Property: The content (query and answer) of preserved turns SHALL 
        match exactly what was added.
        """
        manager = ContextManager(max_history=max_history, ttl_minutes=30)
        user_id = "test_user"
        
        # Add all turns
        for query, answer in turns:
            manager.add_turn(user_id, query, answer)
        
        # Get context
        context = manager.get_context(user_id)
        
        # Get expected turns (most recent max_history)
        expected_turns = turns[-max_history:] if len(turns) > max_history else turns
        
        # Verify content integrity
        assert len(context) == len(expected_turns), \
            f"Expected {len(expected_turns)} turns, got {len(context)}"
        
        for i, (expected_query, expected_answer) in enumerate(expected_turns):
            assert context[i]["query"] == expected_query, \
                f"Turn {i}: query content mismatch"
            assert context[i]["answer"] == expected_answer, \
                f"Turn {i}: answer content mismatch"


class TestContextExpiration:
    """
    Property 5: Context Expiration
    
    Context SHALL expire after the configured TTL.
    
    Feature: knowledge-qa-bot, Property 5: Context expires after TTL
    **Validates: Requirements 2.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(turns=turns_list_strategy)
    def test_context_expires_after_ttl(self, turns):
        """
        Feature: knowledge-qa-bot, Property 5: Context expires after TTL
        **Validates: Requirements 2.4**
        
        Property: Context SHALL expire after the configured TTL (time-to-live).
        After expiration, get_context SHALL return an empty list.
        """
        # Use TTL of 0 minutes to test immediate expiration
        manager = ContextManager(max_history=10, ttl_minutes=0)
        user_id = "test_user"
        
        # Add turns
        for query, answer in turns:
            manager.add_turn(user_id, query, answer)
        
        # Wait a small amount to ensure expiration
        time.sleep(0.05)
        
        # Get context - should be empty due to expiration
        context = manager.get_context(user_id)
        
        assert context == [], \
            f"Context should be empty after TTL expiration, got {len(context)} turns"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(turns=turns_list_strategy)
    def test_context_not_expired_within_ttl(self, turns):
        """
        Feature: knowledge-qa-bot, Property 5: Context not expired within TTL
        **Validates: Requirements 2.4**
        
        Property: Context SHALL NOT expire before the configured TTL.
        Within the TTL window, get_context SHALL return the preserved turns.
        """
        # Use a long TTL to ensure no expiration
        manager = ContextManager(max_history=10, ttl_minutes=60)
        user_id = "test_user"
        
        # Add turns
        for query, answer in turns:
            manager.add_turn(user_id, query, answer)
        
        # Get context immediately - should not be expired
        context = manager.get_context(user_id)
        
        expected_count = min(len(turns), 10)
        assert len(context) == expected_count, \
            f"Context should have {expected_count} turns within TTL, got {len(context)}"


class TestMaxHistoryEnforcement:
    """
    Property 5: Max History Enforcement
    
    The max_history configuration SHALL be enforced correctly.
    
    Feature: knowledge-qa-bot, Property 5: Max history is enforced
    **Validates: Requirements 2.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_turns=st.integers(min_value=1, max_value=20),
        max_history=max_history_strategy
    )
    def test_max_history_never_exceeded(self, num_turns, max_history):
        """
        Feature: knowledge-qa-bot, Property 5: Max history never exceeded
        **Validates: Requirements 2.4**
        
        Property: The number of turns in context SHALL never exceed max_history,
        regardless of how many turns are added.
        """
        manager = ContextManager(max_history=max_history, ttl_minutes=30)
        user_id = "test_user"
        
        # Add specified number of turns
        for i in range(num_turns):
            manager.add_turn(user_id, f"query{i}", f"answer{i}")
        
        # Get context
        context = manager.get_context(user_id)
        
        # Verify max_history is never exceeded
        assert len(context) <= max_history, \
            f"Context length {len(context)} exceeds max_history {max_history}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(max_history=max_history_strategy)
    def test_max_history_exactly_filled(self, max_history):
        """
        Feature: knowledge-qa-bot, Property 5: Max history exactly filled
        **Validates: Requirements 2.4**
        
        Property: When exactly max_history turns are added, all turns SHALL 
        be preserved.
        """
        manager = ContextManager(max_history=max_history, ttl_minutes=30)
        user_id = "test_user"
        
        # Add exactly max_history turns
        for i in range(max_history):
            manager.add_turn(user_id, f"query{i}", f"answer{i}")
        
        # Get context
        context = manager.get_context(user_id)
        
        # Verify all turns are preserved
        assert len(context) == max_history, \
            f"Expected {max_history} turns, got {len(context)}"
        
        # Verify content
        for i in range(max_history):
            assert context[i]["query"] == f"query{i}", \
                f"Turn {i}: query mismatch"
            assert context[i]["answer"] == f"answer{i}", \
                f"Turn {i}: answer mismatch"


class TestThreadSafetyProperties:
    """
    Property 5: Thread Safety Under Concurrent Operations
    
    The ContextManager SHALL maintain data integrity under concurrent operations.
    
    Feature: knowledge-qa-bot, Property 5: Thread safety
    **Validates: Requirements 2.4**
    """
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_threads=st.integers(min_value=2, max_value=5),
        turns_per_thread=st.integers(min_value=3, max_value=10),
        max_history=st.integers(min_value=5, max_value=20)
    )
    def test_concurrent_writes_preserve_max_history(
        self, num_threads, turns_per_thread, max_history
    ):
        """
        Feature: knowledge-qa-bot, Property 5: Concurrent writes preserve max_history
        **Validates: Requirements 2.4**
        
        Property: Under concurrent write operations from multiple threads,
        the max_history constraint SHALL still be enforced for each user.
        """
        manager = ContextManager(max_history=max_history, ttl_minutes=30)
        
        def add_turns_for_user(user_id: str, num_turns: int):
            for i in range(num_turns):
                manager.add_turn(user_id, f"query{i}", f"answer{i}")
        
        # Create threads for different users
        threads = []
        for i in range(num_threads):
            user_id = f"user{i}"
            t = threading.Thread(
                target=add_turns_for_user, 
                args=(user_id, turns_per_thread)
            )
            threads.append(t)
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Verify max_history is enforced for each user
        for i in range(num_threads):
            user_id = f"user{i}"
            context = manager.get_context(user_id)
            assert len(context) <= max_history, \
                f"User {user_id}: context length {len(context)} exceeds max_history {max_history}"
    
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        num_operations=st.integers(min_value=10, max_value=30),
        max_history=st.integers(min_value=5, max_value=15)
    )
    def test_concurrent_read_write_consistency(self, num_operations, max_history):
        """
        Feature: knowledge-qa-bot, Property 5: Concurrent read/write consistency
        **Validates: Requirements 2.4**
        
        Property: Under concurrent read and write operations, the context
        SHALL remain consistent and not raise exceptions.
        """
        manager = ContextManager(max_history=max_history, ttl_minutes=30)
        user_id = "shared_user"
        errors = []
        
        def writer():
            try:
                for i in range(num_operations):
                    manager.add_turn(user_id, f"query{i}", f"answer{i}")
            except Exception as e:
                errors.append(f"Writer error: {e}")
        
        def reader():
            try:
                for _ in range(num_operations):
                    context = manager.get_context(user_id)
                    # Verify context is a valid list
                    if not isinstance(context, list):
                        errors.append(f"Context is not a list: {type(context)}")
                    # Verify max_history constraint
                    if len(context) > max_history:
                        errors.append(
                            f"Context length {len(context)} exceeds max_history {max_history}"
                        )
            except Exception as e:
                errors.append(f"Reader error: {e}")
        
        # Create and start threads
        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)
        
        writer_thread.start()
        reader_thread.start()
        
        writer_thread.join()
        reader_thread.join()
        
        # Verify no errors occurred
        assert len(errors) == 0, f"Errors during concurrent operations: {errors}"
        
        # Final verification
        final_context = manager.get_context(user_id)
        assert len(final_context) <= max_history, \
            f"Final context length {len(final_context)} exceeds max_history {max_history}"
