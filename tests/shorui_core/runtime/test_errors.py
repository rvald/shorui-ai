"""Unit tests for ServiceError hierarchy."""

import pytest

from shorui_core.runtime.errors import (
    ErrorCode,
    RetryableError,
    ServiceError,
    TerminalError,
)


class TestServiceError:
    """Tests for ServiceError base class."""

    def test_create_with_required_fields(self):
        """Should create error with required fields."""
        error = ServiceError(
            code="TEST_ERROR",
            message_safe="Something went wrong",
        )

        assert error.code == "TEST_ERROR"
        assert error.message_safe == "Something went wrong"
        assert error.message_debug is None
        assert error.retryable is False
        assert error.cause is None
        assert error.debug_id is not None  # Auto-generated

    def test_create_with_all_fields(self):
        """Should create error with all fields."""
        cause = ValueError("underlying error")
        error = ServiceError(
            code="FULL_ERROR",
            message_safe="Safe message",
            message_debug="Detailed debug info",
            retryable=True,
            cause=cause,
            debug_id="custom-id",
        )

        assert error.code == "FULL_ERROR"
        assert error.message_safe == "Safe message"
        assert error.message_debug == "Detailed debug info"
        assert error.retryable is True
        assert error.cause is cause
        assert error.debug_id == "custom-id"

    def test_str_representation(self):
        """Should format as [CODE] message."""
        error = ServiceError(
            code="MY_CODE",
            message_safe="My message",
        )

        assert str(error) == "[MY_CODE] My message"

    def test_is_exception(self):
        """Should be raiseable as an exception."""
        error = ServiceError(
            code="RAISE_TEST",
            message_safe="Can be raised",
        )

        with pytest.raises(ServiceError) as exc_info:
            raise error

        assert exc_info.value.code == "RAISE_TEST"

    def test_to_dict(self):
        """Should convert to API-safe dictionary."""
        error = ServiceError(
            code="DICT_TEST",
            message_safe="API message",
            message_debug="Debug only",
            debug_id="debug-123",
        )

        result = error.to_dict()

        assert result == {
            "code": "DICT_TEST",
            "message": "API message",
            "debug_id": "debug-123",
        }
        # Should NOT include debug message
        assert "message_debug" not in result


class TestRetryableError:
    """Tests for RetryableError class."""

    def test_is_retryable_by_default(self):
        """Should have retryable=True."""
        error = RetryableError(
            code="RETRY_ME",
            message_safe="Try again",
        )

        assert error.retryable is True

    def test_inherits_from_service_error(self):
        """Should be a ServiceError."""
        error = RetryableError(
            code="RETRY_TEST",
            message_safe="Test",
        )

        assert isinstance(error, ServiceError)

    def test_can_be_caught_as_service_error(self):
        """Should be catchable as ServiceError."""
        with pytest.raises(ServiceError):
            raise RetryableError(
                code="CATCH_TEST",
                message_safe="Catchable",
            )


class TestTerminalError:
    """Tests for TerminalError class."""

    def test_is_not_retryable(self):
        """Should have retryable=False."""
        error = TerminalError(
            code="STOP_HERE",
            message_safe="Do not retry",
        )

        assert error.retryable is False

    def test_inherits_from_service_error(self):
        """Should be a ServiceError."""
        error = TerminalError(
            code="TERMINAL_TEST",
            message_safe="Test",
        )

        assert isinstance(error, ServiceError)


class TestErrorCode:
    """Tests for ErrorCode constants."""

    def test_timeout_code(self):
        """Should have TIMEOUT code."""
        assert ErrorCode.TIMEOUT == "TIMEOUT"

    def test_connection_error_code(self):
        """Should have CONNECTION_ERROR code."""
        assert ErrorCode.CONNECTION_ERROR == "CONNECTION_ERROR"

    def test_service_unavailable_code(self):
        """Should have SERVICE_UNAVAILABLE code."""
        assert ErrorCode.SERVICE_UNAVAILABLE == "SERVICE_UNAVAILABLE"

    def test_unauthorized_code(self):
        """Should have UNAUTHORIZED code."""
        assert ErrorCode.UNAUTHORIZED == "UNAUTHORIZED"

    def test_forbidden_code(self):
        """Should have FORBIDDEN code."""
        assert ErrorCode.FORBIDDEN == "FORBIDDEN"

    def test_not_found_code(self):
        """Should have NOT_FOUND code."""
        assert ErrorCode.NOT_FOUND == "NOT_FOUND"

    def test_rate_limited_code(self):
        """Should have RATE_LIMITED code."""
        assert ErrorCode.RATE_LIMITED == "RATE_LIMITED"

    def test_internal_error_code(self):
        """Should have INTERNAL_ERROR code."""
        assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"
