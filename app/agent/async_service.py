"""
Async Agent Service with LangGraph Integration

Uses LangGraph ReAct workflow for HIPAA compliance queries.
Sessions are persisted via Redis checkpointer - no manual conversation tracking needed.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from langchain_core.messages import AIMessage, ToolMessage
from loguru import logger
from shorui_core.config import settings


# Lazy-loaded global workflow instance
_workflow = None


def get_workflow():
    """
    Get or create the global AgentWorkflow instance.
    
    Uses lazy initialization to avoid import-time side effects.
    """
    global _workflow
    
    if _workflow is None:
        try:
            from agents.react_agent.workflow import AgentWorkflow
            _workflow = AgentWorkflow()
            logger.info("Created LangGraph AgentWorkflow with Redis checkpointer")
        except Exception as e:
            logger.error(f"Failed to create AgentWorkflow: {e}")
            return None
    
    return _workflow


class AsyncAgentService:
    """Async agent service using LangGraph with Redis checkpointing."""
   
    def __init__(self):
        """Initialize service."""
        self._workflow = None
        self._redis = None
        self.redis_url = getattr(settings, "CELERY_BROKER_URL", "redis://redis:6379/0")

    @property
    def workflow(self):
        """Get workflow (lazy initialization)."""
        if self._workflow is None:
            self._workflow = get_workflow()
        return self._workflow

    @property
    def redis(self):
        """Get async redis client (lazy initialization)."""
        if self._redis is None:
            from redis.asyncio import from_url
            self._redis = from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def create_session(self, tenant_id: str | None = None, user_id: str | None = None) -> str:
        """Create new session ID (state persisted via Redis checkpointer).
        
        Args:
            tenant_id: Optional tenant ID.
            user_id: Optional user ID to bind session to (for invalidation).
        """
        session_id = str(uuid.uuid4())
        
        # Track session for user logic
        if user_id:
            try:
                # Add session to user's set of sessions
                # expire set after 30 days (cleanup)
                key = f"user:{user_id}:sessions"
                await self.redis.sadd(key, session_id)
                await self.redis.expire(key, 2592000)  # 30 days
            except Exception as e:
                logger.error(f"Failed to track session for user {user_id}: {e}")

        logger.info(f"Created agent session: {session_id} (tenant={tenant_id or 'default'}, user={user_id})")
        return session_id

    async def invalidate_user_sessions(self, user_id: str):
        """Invalidate all sessions for a user."""
        try:
            key = f"user:{user_id}:sessions"
            sessions = await self.redis.smembers(key)
            
            if sessions:
                # We can't easily delete checkpoints without internal access to checkpointer
                # But we can remove the mapping, effectively "orphaning" them from the user
                # Or we could mark them as revoked in a separate key if we wanted to block access
                
                # For now, just clearing the mapping is a start, but true security 
                # requires checking a revocation list or deleting checkpoints.
                # Since LangGraph checkpointer doesn't have an easy public delete API by thread_id 
                # without iterating, we will just delete the mapping for now.
                
                # Ideally: await self.workflow.checkpointer.adelete(thread_id=...)
                
                await self.redis.delete(key)
                logger.info(f"Invalidated sessions for user {user_id}: {sessions}")
        except Exception as e:
            logger.error(f"Failed to invalidate sessions for user {user_id}: {e}")
    
    async def send_message(
        self,
        session_id: str,
        message: str,
        project_id: str = "default",
        file_paths: Optional[List[str]] = None,
    ) -> dict:
        """
        Process user message with LangGraph ReAct workflow.
        
        Args:
            session_id: Session ID (used as thread_id for checkpointing)
            message: User's message
            project_id: Project/tenant ID
            file_paths: Optional file paths for context
            
        Returns:
            Dict with 'content' and 'steps'
        """
        logger.info(f"Processing message in session {session_id}: {message[:50]}...")
        
        # Build user input with file context
        user_input = self._build_user_input(message, file_paths)
        
        # Get workflow
        workflow = self.workflow
        if workflow is None:
            return {
                "content": "Agent workflow not configured. Please check OPENAI_API_KEY.",
                "steps": [],
            }
        
        try:
            # Run LangGraph workflow with session_id as thread_id for checkpointing
            result = await workflow.invoke_async(
                user_input=user_input,
                thread_id=session_id,
            )
            
            # Extract output from LangGraph state
            output, steps = self._parse_langgraph_result(result)
            
            logger.info(f"Workflow completed with {len(steps)} steps")
            
            return {
                "content": output,
                "steps": steps,
            }
            
        except Exception as e:
            logger.exception(f"Workflow error: {e}")
            return {
                "content": f"Error: {str(e)}",
                "steps": [],
            }
    
    def _build_user_input(
        self,
        message: str,
        file_paths: Optional[List[str]] = None,
    ) -> str:
        """
        Build user input with context.
        
        Includes file paths for transcript analysis.
        """
        parts = [message]
        
        # Add file context if files were uploaded
        if file_paths:
            file_list = "\n".join(f"- {path}" for path in file_paths)
            parts.append(f"""
                        The user has uploaded the following file(s) for analysis:
                        {file_list}
                        
                        Use the analyze_clinical_transcript tool with the file path to analyze these files for HIPAA compliance.
                        """)
        
        return "".join(parts)
    
    def _parse_langgraph_result(self, result: dict) -> tuple[str, list]:
        """
        Parse LangGraph state into output and steps.
        
        Args:
            result: LangGraph state dict with 'messages' and 'iterations'
            
        Returns:
            Tuple of (output_string, steps_list)
        """
        messages = result.get("messages", [])
        
        # Find the last AI message (the final answer)
        output = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                output = msg.content
                break
        
        # Build steps from message sequence
        steps = []
        step_number = 0
        
        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage):
                step_number += 1
                
                # Check for tool calls
                tool_name = None
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_name = msg.tool_calls[0].get("name") if msg.tool_calls else None
                
                # Look ahead for observation (ToolMessage)
                observation = None
                if i + 1 < len(messages) and isinstance(messages[i + 1], ToolMessage):
                    observation = messages[i + 1].content
                
                steps.append({
                    "step_number": step_number,
                    "thought": msg.content if not msg.tool_calls else None,
                    "action": tool_name,
                    "observation": observation,
                })
        
        return output, steps
