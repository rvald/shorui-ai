"""
Base definitions for HTTP clients.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from shorui_core.runtime import RunContext


class ServiceStatus(BaseModel):
    """Status of a backend service."""

    name: str
    healthy: bool
    message: str = ""


def default_context(tenant_id: str = "default") -> RunContext:
    """Create a default RunContext for backward compatibility.

    Used when callers don't provide an explicit context.

    Args:
        tenant_id: Tenant ID to use. Defaults to "default".

    Returns:
        A new RunContext with a generated request_id.
    """
    return RunContext(
        request_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
    )
