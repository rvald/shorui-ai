"""
System Tools

Tools for system observability and health checks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

# Support both package import and direct script execution
try:
    from ..core.tools import Tool
    from ..infrastructure.http_clients import HealthClient
except ImportError:
    from core.tools import Tool
    from infrastructure.http_clients import HealthClient


class CheckSystemHealthTool(Tool):
    """
    Check the health status of all Shorui AI backend services.
    
    Verifies connectivity to:
    - Ingestion Service (document processing)
    - RAG Service (semantic search)
    
    Example:
        tool = CheckSystemHealthTool()
        result = tool()
    """
    
    name = "check_system_health"
    description = (
        "Check if all backend services are healthy and reachable. "
        "Use this to diagnose connectivity issues before other operations."
    )
    inputs = {}  # No inputs required
    output_type = "string"
    
    def __init__(self, client: Optional[HealthClient] = None):
        self._client = client or HealthClient()
    
    def forward(self) -> str:
        """Check health of all services."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            statuses = loop.run_until_complete(self._client.check_all())
            
            all_healthy = all(s.healthy for s in statuses.values())
            
            output = "System Health Status:\n"
            for name, status in statuses.items():
                icon = "✅" if status.healthy else "❌"
                msg = status.message if not status.healthy else "OK"
                output += f"- {icon} {name.upper()}: {msg}\n"
            
            if all_healthy:
                output += "\nAll services are healthy and ready."
            else:
                output += "\n⚠️ Some services are unhealthy. Check logs for details."
            
            return output
            
        except Exception as e:
            return f"Error checking system health: {e}"
