"""FastAPI routes for agent chat API."""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.agent.schemas import (
    CreateSessionResponse,
    AgentResponse,
    AgentStep,
)
from shorui_core.auth.dependencies import get_auth_context
from shorui_core.domain.auth import AuthContext

router = APIRouter(prefix="/agent", tags=["agent"])

# Lazy-loaded service instance
_service = None


def get_service():
    """Get async agent service (lazy initialization)."""
    global _service
    if _service is None:
        from app.agent.async_service import AsyncAgentService
        _service = AsyncAgentService()
    return _service


# Ensure temp upload directory exists
TEMP_DIR = os.getenv("TEMP_DIR", "/tmp")
UPLOAD_DIR = Path(TEMP_DIR) / "agent_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    auth: AuthContext = Depends(get_auth_context),
):
    """Create a new ephemeral agent session."""
    service = get_service()
    # Pass tenant_id to bind session to tenant
    session_id = await service.create_session(tenant_id=auth.tenant_id)
    
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
    auth: AuthContext = Depends(get_auth_context),
):
    """
    Send a message to an existing agent session.
    
    Optionally upload files (transcripts) for the agent to analyze.
    Files are saved to a temp directory and paths are included in the task context.
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
        
        # Call service
        service = get_service()
        result = await service.send_message(
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


