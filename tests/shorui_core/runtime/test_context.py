"""Unit tests for RunContext."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from shorui_core.runtime.context import RunContext


class TestRunContextCreation:
    """Tests for RunContext instantiation."""

    def test_create_with_required_fields(self):
        """Should create context with required fields."""
        ctx = RunContext(
            request_id="req-123",
            tenant_id="tenant-abc",
        )
        assert ctx.request_id == "req-123"
        assert ctx.tenant_id == "tenant-abc"
        assert ctx.project_id is None
        assert ctx.user_id is None
        assert ctx.deadline is None
        assert ctx.budgets is None

    def test_create_with_all_fields(self):
        """Should create context with all fields."""
        deadline = datetime.now(timezone.utc)
        ctx = RunContext(
            request_id="req-456",
            tenant_id="tenant-xyz",
            project_id="proj-001",
            user_id="user-789",
            deadline=deadline,
            budgets={"max_retries": 5},
        )
        assert ctx.request_id == "req-456"
        assert ctx.tenant_id == "tenant-xyz"
        assert ctx.project_id == "proj-001"
        assert ctx.user_id == "user-789"
        assert ctx.deadline == deadline
        assert ctx.budgets == {"max_retries": 5}

    def test_context_is_immutable(self):
        """Context should be frozen/immutable."""
        ctx = RunContext(request_id="req-1", tenant_id="tenant-1")
        with pytest.raises(Exception):  # ValidationError for frozen model
            ctx.request_id = "changed"


class TestRunContextFromAuth:
    """Tests for creating RunContext from AuthContext."""

    def test_from_auth_basic(self):
        """Should create context from AuthContext."""
        # Mock AuthContext
        mock_auth = MagicMock()
        mock_auth.request_id = "auth-req-123"
        mock_auth.tenant_id = "auth-tenant"

        ctx = RunContext.from_auth(mock_auth)

        assert ctx.request_id == "auth-req-123"
        assert ctx.tenant_id == "auth-tenant"
        assert ctx.project_id is None

    def test_from_auth_with_project(self):
        """Should include project_id when provided."""
        mock_auth = MagicMock()
        mock_auth.request_id = "auth-req-456"
        mock_auth.tenant_id = "auth-tenant-2"

        ctx = RunContext.from_auth(mock_auth, project_id="my-project")

        assert ctx.request_id == "auth-req-456"
        assert ctx.tenant_id == "auth-tenant-2"
        assert ctx.project_id == "my-project"


class TestRunContextForWorker:
    """Tests for creating RunContext for worker tasks."""

    def test_for_worker_uses_job_id_as_request_id(self):
        """Should use job_id as request_id for correlation."""
        ctx = RunContext.for_worker(
            tenant_id="worker-tenant",
            project_id="worker-project",
            job_id="job-12345",
        )

        assert ctx.request_id == "job-12345"
        assert ctx.tenant_id == "worker-tenant"
        assert ctx.project_id == "worker-project"


class TestRunContextModifiers:
    """Tests for context modifier methods."""

    def test_with_deadline_returns_new_context(self):
        """Should return new context with deadline."""
        ctx = RunContext(request_id="req-1", tenant_id="tenant-1")
        deadline = datetime.now(timezone.utc)

        new_ctx = ctx.with_deadline(deadline)

        assert new_ctx is not ctx
        assert new_ctx.deadline == deadline
        assert ctx.deadline is None  # Original unchanged

    def test_with_budgets_returns_new_context(self):
        """Should return new context with budgets."""
        ctx = RunContext(request_id="req-1", tenant_id="tenant-1")

        new_ctx = ctx.with_budgets(max_retries=3, timeout_ms=5000)

        assert new_ctx is not ctx
        assert new_ctx.budgets == {"max_retries": 3, "timeout_ms": 5000}
        assert ctx.budgets is None  # Original unchanged

    def test_with_budgets_merges_existing(self):
        """Should merge with existing budgets."""
        ctx = RunContext(
            request_id="req-1",
            tenant_id="tenant-1",
            budgets={"existing": 1},
        )

        new_ctx = ctx.with_budgets(new_key=2)

        assert new_ctx.budgets == {"existing": 1, "new_key": 2}


class TestRunContextGetHeaders:
    """Tests for header generation."""

    def test_get_headers_required_only(self):
        """Should include required headers."""
        ctx = RunContext(request_id="req-abc", tenant_id="tenant-xyz")

        headers = ctx.get_headers()

        assert headers == {
            "X-Request-Id": "req-abc",
            "X-Tenant-Id": "tenant-xyz",
        }

    def test_get_headers_with_project(self):
        """Should include project header when set."""
        ctx = RunContext(
            request_id="req-abc",
            tenant_id="tenant-xyz",
            project_id="proj-123",
        )

        headers = ctx.get_headers()

        assert headers == {
            "X-Request-Id": "req-abc",
            "X-Tenant-Id": "tenant-xyz",
            "X-Project-Id": "proj-123",
        }
