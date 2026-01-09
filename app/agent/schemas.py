"""Pydantic schemas for agent API."""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class CreateSessionResponse(BaseModel):
    """Response for session creation."""
    session_id: str
    created_at: datetime


class SendMessageRequest(BaseModel):
    """Request to send a message to the agent."""
    message: str
    project_id: str = "default"


class AgentStep(BaseModel):
    """Single step in agent reasoning."""
    step_number: int
    thought: Optional[str] = None
    action: Optional[str] = None
    observation: Optional[str] = None


class AgentResponse(BaseModel):
    """Response from agent after processing a message."""
    content: str
    steps: List[AgentStep]
