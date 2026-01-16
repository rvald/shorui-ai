"""
Async Agent Service with LangGraph Integration

Uses LangGraph ReAct workflow for HIPAA compliance queries.
The workflow handles tool selection and execution automatically.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from loguru import logger


# Lazy-loaded global workflow instance
_workflow = None
_conversations: Dict[str, List[dict]] = {}  # session_id -> message history


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
            logger.info("Created LangGraph AgentWorkflow")
        except Exception as e:
            logger.error(f"Failed to create AgentWorkflow: {e}")
            return None
    
    return _workflow


class AsyncAgentService:
   
    def __init__(self):
        """Initialize service."""
        self._workflow = None
    
    @property
    def workflow(self):
        """Get workflow (lazy initialization)."""
        if self._workflow is None:
            self._workflow = get_workflow()
        return self._workflow
    
    async def create_session(self, metadata: Optional[dict] = None) -> str:
        """
        Create new session.
        
        Args:
            metadata: Optional session metadata
            
        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        _conversations[session_id] = []
        logger.info(f"Created agent session: {session_id}")
        return session_id
    
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
            session_id: Session ID
            message: User's message
            project_id: Project/tenant ID
            file_paths: Optional file paths for context
            
        Returns:
            Dict with 'content' and 'steps'
        """
        logger.info(f"Processing message in session {session_id}: {message[:50]}...")
        
        # Ensure session exists
        if session_id not in _conversations:
            _conversations[session_id] = []
        
        # Build user input with file context
        user_input = self._build_user_input(message, project_id, file_paths)
        
        # Get workflow
        workflow = self.workflow
        if workflow is None:
            return {
                "content": "Agent workflow not configured. Please check OPENAI_API_KEY.",
                "steps": [],
            }
        
        try:
            # Run LangGraph workflow
            result = await asyncio.to_thread(
                workflow._invoke_impl,
                user_input=user_input,
                config=None,
            )
            
            # Extract output from LangGraph state
            output, steps = self._parse_langgraph_result(result)
            
            # Store in conversation history
            _conversations[session_id].append({"role": "user", "content": message})
            _conversations[session_id].append({"role": "assistant", "content": output})
            
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
        project_id: str,
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

Use the analyze_clinical_transcript tool with the file path to analyze these files for HIPAA compliance.""")
        
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
        iterations = result.get("iterations", 0)
        
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
    
    async def get_session(self, session_id: str) -> dict:
        """Get session details."""
        if session_id not in _conversations:
            raise ValueError(f"Session not found: {session_id}")
        
        return {
            "session_id": session_id,
            "messages": _conversations[session_id],
        }
    
    async def delete_session(self, session_id: str) -> None:
        """Delete session."""
        if session_id in _conversations:
            del _conversations[session_id]
        logger.info(f"Deleted session: {session_id}")
