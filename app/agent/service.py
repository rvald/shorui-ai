"""
Agent service with Redis-backed session management.

Sessions are stored in Redis for cross-worker access.
Sessions expire after 1 hour of inactivity.
"""

from datetime import datetime
from typing import List, Optional
import uuid
import json
import sys
from pathlib import Path

import redis

# Add project root to path for agent imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "agents" / "react_agent"))

from loguru import logger
from shorui_core.config import settings


# Redis client (shared across workers)
_redis: Optional[redis.Redis] = None

SESSION_TTL_SECONDS = 3600  # 1 hour


def get_redis() -> redis.Redis:
    """Get or create Redis connection."""
    global _redis
    if _redis is None:
        redis_url = getattr(settings, "REDIS_URL", "redis://redis:6379/0")
        _redis = redis.from_url(redis_url, decode_responses=True)
    return _redis


def _session_key(session_id: str) -> str:
    """Generate Redis key for a session."""
    return f"agent:session:{session_id}"


class AgentService:
    """Service for managing agent conversations with Redis-backed sessions."""

    def create_session(self) -> str:
        """Create new session stored in Redis."""
        session_id = str(uuid.uuid4())
        r = get_redis()
        
        session_data = {
            "session_id": session_id,
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat(),
        }
        
        r.setex(
            _session_key(session_id),
            SESSION_TTL_SECONDS,
            json.dumps(session_data),
        )
        
        logger.info(f"Created agent session: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> dict:
        """Retrieve session from Redis and refresh TTL."""
        r = get_redis()
        key = _session_key(session_id)
        
        data = r.get(key)
        if data is None:
            raise ValueError(f"Session {session_id} not found or expired")
        
        session = json.loads(data)
        session["last_accessed"] = datetime.now().isoformat()
        
        # Refresh TTL
        r.setex(key, SESSION_TTL_SECONDS, json.dumps(session))
        
        return session

    def _save_session(self, session: dict) -> None:
        """Save session back to Redis."""
        r = get_redis()
        r.setex(
            _session_key(session["session_id"]),
            SESSION_TTL_SECONDS,
            json.dumps(session),
        )

    def send_message(
        self,
        session_id: str,
        message: str,
        project_id: str = "default",
        file_paths: List[str] | None = None,
    ) -> dict:
        """Process new user message in existing session."""
        session = self.get_session(session_id)

        # Add user message to history (include file info if present)
        msg_content = message
        if file_paths:
            msg_content += f"\n\n[Uploaded files: {', '.join(file_paths)}]"
        session["messages"].append({"role": "user", "content": msg_content})

        # Build task with full conversation context
        task = self._build_task_with_context(session["messages"], file_paths)

        logger.info(f"Processing message in session {session_id}: {message[:50]}...")

        # Initialize and run agent
        from agent import ReActAgent
        from core.models import OpenAIModel
        from tools.compliance_tools import (
            AnalyzeClinicalTranscriptTool,
            GetComplianceReportTool,
            LookupHIPAARegulationTool,
            QueryAuditLogTool,
        )

        model = OpenAIModel(api_key=settings.OPENAI_API_KEY)
        
        agent = ReActAgent(
            tools=[
                AnalyzeClinicalTranscriptTool(),
                GetComplianceReportTool(),
                LookupHIPAARegulationTool(),
                QueryAuditLogTool(),
            ],
            model=model,
            max_steps=10,
            verbose=True,
        )

        result = agent.run(task)

        # Store assistant's response
        output = result.output if isinstance(result.output, str) else str(result.output)
        session["messages"].append({"role": "assistant", "content": output})
        
        # Save session back to Redis
        self._save_session(session)

        logger.info(f"Agent completed with {len(result.steps)} steps")

        return {
            "content": output,
            "steps": [
                {
                    "step_number": i + 1,
                    "thought": getattr(step, "thought", None),
                    "action": step.tool_call.name if hasattr(step, "tool_call") and step.tool_call else None,
                    "observation": getattr(step, "observation", None),
                }
                for i, step in enumerate(result.steps)
            ],
        }

    def _build_task_with_context(
        self, messages: List[dict], file_paths: List[str] | None = None
    ) -> str:
        """Convert message history into task prompt with context."""
        # Build file context if files were uploaded
        file_context = ""
        if file_paths:
            file_context = f"""
The user has uploaded the following file(s) for analysis:
{chr(10).join(f'- {path}' for path in file_paths)}

Use the analyze_clinical_transcript tool with the file path to analyze these files for HIPAA compliance.
"""

        if len(messages) == 1:
            return file_context + messages[0]["content"]

        # Format previous conversation as context
        context = "\n\n".join(
            [f"{msg['role'].upper()}: {msg['content']}" for msg in messages[:-1]]
        )

        current_message = messages[-1]["content"]

        return f"""Previous conversation context:
{context}

{file_context}Current user request:
{current_message}

Please continue the conversation by addressing the current request while keeping the previous context in mind."""
