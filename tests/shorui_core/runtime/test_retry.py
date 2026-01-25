"""Unit tests for RetryPolicy and retry decorators."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from shorui_core.runtime.errors import RetryableError, TerminalError
from shorui_core.runtime.retry import (
    DEFAULT_RETRY_POLICY,
    RetryPolicy,
    sync_with_retry,
    with_retry,
)


class TestRetryPolicy:
    """Tests for RetryPolicy configuration."""

    def test_default_values(self):
        """Should have sensible defaults."""
        policy = RetryPolicy()

        assert policy.max_attempts == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.exponential_base == 2.0
        assert policy.jitter is True
        assert policy.retry_on_status == (429, 502, 503, 504)

    def test_custom_values(self):
        """Should accept custom configuration."""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
            jitter=False,
            retry_on_status=(500, 502),
        )

        assert policy.max_attempts == 5
        assert policy.base_delay == 0.5
        assert policy.max_delay == 30.0
        assert policy.exponential_base == 3.0
        assert policy.jitter is False
        assert policy.retry_on_status == (500, 502)

    def test_is_frozen(self):
        """Should be immutable."""
        policy = RetryPolicy()
        with pytest.raises(Exception):
            policy.max_attempts = 10


class TestCalculateDelay:
    """Tests for delay calculation."""

    def test_first_attempt_uses_base_delay(self):
        """Attempt 0 should use base_delay."""
        policy = RetryPolicy(base_delay=2.0, jitter=False)

        delay = policy.calculate_delay(0)

        assert delay == 2.0

    def test_exponential_backoff(self):
        """Delay should increase exponentially."""
        policy = RetryPolicy(base_delay=1.0, exponential_base=2.0, jitter=False)

        assert policy.calculate_delay(0) == 1.0  # 1 * 2^0
        assert policy.calculate_delay(1) == 2.0  # 1 * 2^1
        assert policy.calculate_delay(2) == 4.0  # 1 * 2^2
        assert policy.calculate_delay(3) == 8.0  # 1 * 2^3

    def test_max_delay_caps_backoff(self):
        """Delay should not exceed max_delay."""
        policy = RetryPolicy(base_delay=1.0, max_delay=5.0, jitter=False)

        delay = policy.calculate_delay(10)  # Would be 1024 without cap

        assert delay == 5.0

    def test_jitter_adds_randomness(self):
        """Jitter should add variance to delays."""
        policy = RetryPolicy(base_delay=1.0, jitter=True)

        # Run multiple times and check for variance
        delays = [policy.calculate_delay(0) for _ in range(10)]

        # With jitter, delays should have some variance
        assert len(set(delays)) > 1  # Not all identical


class TestShouldRetryStatus:
    """Tests for status code checking."""

    def test_429_is_retryable(self):
        """Rate limit (429) should trigger retry."""
        policy = RetryPolicy()
        assert policy.should_retry_status(429) is True

    def test_502_is_retryable(self):
        """Bad gateway (502) should trigger retry."""
        policy = RetryPolicy()
        assert policy.should_retry_status(502) is True

    def test_503_is_retryable(self):
        """Service unavailable (503) should trigger retry."""
        policy = RetryPolicy()
        assert policy.should_retry_status(503) is True

    def test_504_is_retryable(self):
        """Gateway timeout (504) should trigger retry."""
        policy = RetryPolicy()
        assert policy.should_retry_status(504) is True

    def test_200_is_not_retryable(self):
        """Success (200) should not trigger retry."""
        policy = RetryPolicy()
        assert policy.should_retry_status(200) is False

    def test_400_is_not_retryable(self):
        """Bad request (400) should not trigger retry."""
        policy = RetryPolicy()
        assert policy.should_retry_status(400) is False

    def test_500_is_not_retryable_by_default(self):
        """Internal error (500) is not in default retry list."""
        policy = RetryPolicy()
        assert policy.should_retry_status(500) is False


class TestWithRetryDecorator:
    """Tests for async retry decorator."""

    @pytest.mark.asyncio
    async def test_returns_value_on_success(self):
        """Should return function result when successful."""

        @with_retry()
        async def success_func():
            return "success"

        result = await success_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retries_on_retryable_error(self):
        """Should retry when RetryableError is raised."""
        call_count = 0

        @with_retry(RetryPolicy(max_attempts=3, base_delay=0.01))
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError(code="RETRY", message_safe="Try again")
            return "success"

        result = await flaky_func()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        """Should raise after exhausting retries."""

        @with_retry(RetryPolicy(max_attempts=2, base_delay=0.01))
        async def always_fails():
            raise RetryableError(code="ALWAYS_FAIL", message_safe="Never works")

        with pytest.raises(RetryableError) as exc_info:
            await always_fails()

        assert exc_info.value.code == "ALWAYS_FAIL"

    @pytest.mark.asyncio
    async def test_does_not_retry_terminal_error(self):
        """Should not retry TerminalError."""
        call_count = 0

        @with_retry(RetryPolicy(max_attempts=3, base_delay=0.01))
        async def terminal_func():
            nonlocal call_count
            call_count += 1
            raise TerminalError(code="TERMINAL", message_safe="Stop")

        with pytest.raises(TerminalError):
            await terminal_func()

        assert call_count == 1  # Only called once

    @pytest.mark.asyncio
    async def test_calls_on_retry_callback(self):
        """Should call on_retry callback before each retry."""
        retry_calls = []

        def on_retry(attempt, exc, delay):
            retry_calls.append((attempt, exc.code))

        call_count = 0

        @with_retry(RetryPolicy(max_attempts=3, base_delay=0.01), on_retry=on_retry)
        async def callback_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError(code=f"RETRY_{call_count}", message_safe="Retry")
            return "done"

        await callback_func()

        assert len(retry_calls) == 2
        assert retry_calls[0][1] == "RETRY_1"
        assert retry_calls[1][1] == "RETRY_2"


class TestDefaultRetryPolicy:
    """Tests for the global default policy."""

    def test_default_policy_exists(self):
        """Should have a default policy."""
        assert DEFAULT_RETRY_POLICY is not None
        assert isinstance(DEFAULT_RETRY_POLICY, RetryPolicy)
