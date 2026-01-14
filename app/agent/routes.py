"""FastAPI routes for agent chat API."""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.agent.schemas import (
    CreateSessionResponse,
    AgentResponse,
    AgentStep,
)

router = APIRouter(prefix="/agent", tags=["agent"])

# Feature flag for async service
USE_ASYNC_SERVICE = os.getenv("USE_ASYNC_AGENT", "true").lower() == "true"

# Lazy-loaded service instances
_sync_service = None
_async_service = None


def get_sync_service():
    """Get legacy sync service (backward compatibility)."""
    global _sync_service
    if _sync_service is None:
        from app.agent.service import AgentService
        _sync_service = AgentService()
    return _sync_service


def get_async_service():
    """Get new async service with orchestrator."""
    global _async_service
    if _async_service is None:
        from app.agent.async_service import AsyncAgentService
        _async_service = AsyncAgentService()
    return _async_service


# Ensure temp upload directory exists
TEMP_DIR = os.getenv("TEMP_DIR", "/tmp")
UPLOAD_DIR = Path(TEMP_DIR) / "agent_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session():
    """Create a new ephemeral agent session."""
    if USE_ASYNC_SERVICE:
        service = get_async_service()
        session_id = await service.create_session()
    else:
        service = get_sync_service()
        session_id = service.create_session()
    
    return CreateSessionResponse(
        session_id=session_id,
        created_at=datetime.now(),
    )


@router.post("/sessions/{session_id}/messages", response_model=AgentResponse)
async def send_message(
    session_id: str,
    message: str = Form(...),
    project_id: str = Form("default"),
    files: Optional[List[UploadFile]] = File(None),
):
    """
    Send a message to an existing agent session.
    
    Optionally upload files (transcripts) for the agent to analyze.
    Files are saved to a temp directory and paths are included in the task context.
    
    Uses async orchestrator with routing for optimal execution:
    - Direct tool calls: 0 LLM tokens
    - Prompt chains: Minimal tokens
    - Agent: Full ReAct loop
    """
    try:
        # Save uploaded files and collect paths
        file_paths: List[str] = []
        if files:
            for uploaded_file in files:
                if uploaded_file.filename:
                    # Generate unique filename to avoid collisions
                    ext = Path(uploaded_file.filename).suffix
                    unique_name = f"{uuid.uuid4()}{ext}"
                    file_path = UPLOAD_DIR / unique_name
                    
                    # Save file
                    content = await uploaded_file.read()
                    file_path.write_bytes(content)
                    file_paths.append(str(file_path.absolute()))
        
        # Call service with message and file paths
        if USE_ASYNC_SERVICE:
            service = get_async_service()
            result = await service.send_message(
                session_id=session_id,
                message=message,
                project_id=project_id,
                file_paths=file_paths,
            )
        else:
            service = get_sync_service()
            result = service.send_message(
                session_id=session_id,
                message=message,
                project_id=project_id,
                file_paths=file_paths,
            )
        
        return AgentResponse(
            content=result["content"],
            steps=[AgentStep(**step) for step in result.get("steps", [])],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

