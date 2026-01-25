"""
Request-scoped context for service operations.

RunContext carries correlation IDs, tenant information, and operational budgets
across service boundaries. It can be created from an AuthContext (for HTTP requests)
or directly for worker/background tasks.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from shorui_core.domain.auth import AuthContext


class RunContext(BaseModel):
    """Request-scoped context for service operations.

    This context flows through all service calls and is used for:
    - Correlation ID propagation (request_id)
    - Tenant isolation (tenant_id, project_id)
    - Operational budgets (deadline, max_retries)
    - Header injection in HTTP clients

    Attributes:
        request_id: Unique identifier for request tracing.
        tenant_id: Tenant namespace for data isolation.
        project_id: Project within the tenant.
        user_id: Optional user identifier.
        deadline: Optional absolute deadline for the operation.
        budgets: Optional operational constraints (e.g., {"max_retries": 3}).
    """

    request_id: str
    tenant_id: str
    project_id: str | None = None
    user_id: str | None = None
    deadline: datetime | None = None
    budgets: dict[str, int] | None = Field(default=None)

    model_config = {"frozen": True}

    @classmethod
    def from_auth(
        cls,
        auth: "AuthContext",
        project_id: str | None = None,
    ) -> "RunContext":
        """Create RunContext from an AuthContext.

        Args:
            auth: The authentication context from the request.
            project_id: Optional project ID to include.

        Returns:
            A new RunContext with values from the auth context.
        """
        return cls(
            request_id=auth.request_id,
            tenant_id=auth.tenant_id,
            project_id=project_id,
        )

    @classmethod
    def for_worker(
        cls,
        tenant_id: str,
        project_id: str,
        job_id: str,
    ) -> "RunContext":
        """Create RunContext for a background worker task.

        Uses the job_id as the request_id for correlation.

        Args:
            tenant_id: Tenant namespace.
            project_id: Project identifier.
            job_id: The job ID, used as request_id for tracing.

        Returns:
            A new RunContext configured for worker use.
        """
        return cls(
            request_id=job_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

    def with_deadline(self, deadline: datetime) -> "RunContext":
        """Return a new context with the specified deadline.

        Args:
            deadline: Absolute datetime by which operation should complete.

        Returns:
            New RunContext with the deadline set.
        """
        return self.model_copy(update={"deadline": deadline})

    def with_budgets(self, **budgets: int) -> "RunContext":
        """Return a new context with the specified budgets.

        Args:
            **budgets: Key-value pairs for operational budgets.

        Returns:
            New RunContext with the budgets set.
        """
        current = self.budgets or {}
        return self.model_copy(update={"budgets": {**current, **budgets}})

    def get_headers(self) -> dict[str, str]:
        """Get HTTP headers for propagating context.

        Returns:
            Dictionary of headers to inject into outbound requests.
        """
        headers = {
            "X-Request-Id": self.request_id,
            "X-Tenant-Id": self.tenant_id,
        }
        if self.project_id:
            headers["X-Project-Id"] = self.project_id
        return headers
