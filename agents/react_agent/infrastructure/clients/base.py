"""
Base definitions for HTTP clients.
"""
from typing import Optional
from pydantic import BaseModel

class ServiceStatus(BaseModel):
    """Status of a backend service."""
    name: str
    healthy: bool
    message: str = ""
