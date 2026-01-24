"""
Tenant resolution helpers.

Temporary placeholder until auth/tenant mapping is implemented.
"""

from fastapi import HTTPException


def resolve_tenant_from_project(project_id: str) -> str:
    """
    Derive tenant_id from project context (placeholder).

    Args:
        project_id: Project identifier supplied by the client.

    Returns:
        tenant_id: Derived tenant identifier.
    """
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    return project_id.split(":")[0] if ":" in project_id else project_id
