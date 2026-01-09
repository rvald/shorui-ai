"""FastAPI routes for agent chat API."""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.agent.service import AgentService
from app.agent.schemas import (
    CreateSessionResponse,
    AgentResponse,
    AgentStep,
)
from shorui_core.config import settings

router = APIRouter(prefix="/agent", tags=["agent"])

# Singleton service instance
_service = AgentService()

# Ensure temp upload directory exists
UPLOAD_DIR = Path(settings.TEMP_DIR) / "agent_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session():
    """Create a new ephemeral agent session."""
    session_id = _service.create_session()
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
        result = _service.send_message(
            session_id=session_id,
            message=message,
            project_id=project_id,
            file_paths=file_paths,
        )
        
        return AgentResponse(
            content=result["content"],
            steps=[AgentStep(**step) for step in result["steps"]],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
