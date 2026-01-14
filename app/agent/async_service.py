"""
Simplified Async Agent Service

Uses ReActAgent directly as the orchestrator with 2 tools:
- AnalyzeClinicalTranscriptTool: PHI detection via backend
- QueryHIPAARegulationsRAGTool: HIPAA questions via RAG

No router needed - the agent decides which tool(s) to use.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger


# Lazy-loaded global agent instance
_agent = None
_conversations: Dict[str, List[dict]] = {}  # session_id -> message history


def _get_tools():
    """Get the 2 core tools for HIPAA compliance."""
    try:
        from agents.react_agent.tools.compliance_tools import (
            AnalyzeClinicalTranscriptTool,
            QueryHIPAARegulationsRAGTool,
        )
        
        return [
            AnalyzeClinicalTranscriptTool(),
            QueryHIPAARegulationsRAGTool(),
        ]
    except ImportError as e:
        logger.error(f"Could not import tools: {e}")
        return []


def _get_model():
    """Get LLM model for agent execution."""
    try:
        from agents.react_agent.core.models import OpenAIModel
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set, agent will use mock responses")
            return None
        return OpenAIModel(api_key=api_key)
    except ImportError as e:
        logger.error(f"Could not import OpenAIModel: {e}")
        return None


def get_agent():
    """
    Get or create the global ReActAgent instance.
    
    Uses lazy initialization to avoid import-time side effects.
    """
    global _agent
    
    if _agent is None:
        from agents.react_agent.agent import ReActAgent
        
        tools = _get_tools()
        model = _get_model()
        
        if model is None:
            logger.error("Cannot create agent without model")
            return None
        
        _agent = ReActAgent(
            tools=tools,
            model=model,
            max_steps=10,
            verbose=True,
        )
        
        tool_names = [t.name for t in tools]
        logger.info(f"Created ReActAgent with tools: {tool_names}")
    
    return _agent


class AsyncAgentService:
    """
    Simplified async agent service.
    
    Uses ReActAgent directly as orchestrator - no separate router or executors.
    The agent decides which tool(s) to use based on the query.
    
    Example:
    ```python
    service = AsyncAgentService()
    session_id = await service.create_session()
    result = await service.send_message(session_id, "What is HIPAA Safe Harbor?")
    ```
    """
    
    def __init__(self):
        """Initialize service."""
        self._agent = None
    
    @property
    def agent(self):
        """Get agent (lazy initialization)."""
        if self._agent is None:
            self._agent = get_agent()
        return self._agent
    
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
        Process user message with ReActAgent.
        
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
        
        # Build task with file context and conversation history
        task = self._build_task(message, project_id, session_id, file_paths)
        
        # Get agent
        agent = self.agent
        if agent is None:
            return {
                "content": "Agent not configured. Please set OPENAI_API_KEY.",
                "steps": [],
            }
        
        try:
            # Run agent (in thread pool since run() is sync)
            if hasattr(agent, 'run_async'):
                result = await agent.run_async(task)
            else:
                result = await asyncio.to_thread(agent.run, task)
            
            # Extract output
            output = result.output if isinstance(result.output, str) else str(result.output)
            
            # Format steps
            steps = []
            for i, step in enumerate(result.steps):
                steps.append({
                    "step_number": i + 1,
                    "thought": getattr(step, "thought", None),
                    "action": step.tool_call.name if hasattr(step, "tool_call") and step.tool_call else None,
                    "observation": getattr(step, "observation", None),
                })
            
            # Store in conversation history
            _conversations[session_id].append({"role": "user", "content": message})
            _conversations[session_id].append({"role": "assistant", "content": output})
            
            logger.info(f"Agent completed with {len(steps)} steps")
            
            return {
                "content": output,
                "steps": steps,
            }
            
        except Exception as e:
            logger.exception(f"Agent error: {e}")
            return {
                "content": f"Error: {str(e)}",
                "steps": [],
            }
    
    def _build_task(
        self,
        message: str,
        project_id: str,
        session_id: str,
        file_paths: Optional[List[str]] = None,
    ) -> str:
        """
        Build task string with context.
        
        Includes:
        - Previous conversation history (for multi-turn support)
        - File paths for transcript analysis
        - Project ID
        """
        parts = []
        
        # Add previous conversation context if available
        conversation = _conversations.get(session_id, [])
        if conversation:
            # Get last few exchanges (limit to avoid token overflow)
            recent = conversation[-6:]  # Last 3 exchanges
            if recent:
                context_lines = []
                for msg in recent:
                    role = msg["role"].upper()
                    content = msg["content"][:300]  # Truncate long messages
                    if len(msg["content"]) > 300:
                        content += "..."
                    context_lines.append(f"{role}: {content}")
                
                parts.append(f"Previous conversation:\n" + "\n".join(context_lines))
        
        # Add file context if files were uploaded
        if file_paths:
            file_list = "\n".join(f"- {path}" for path in file_paths)
            parts.append(f"""The user has uploaded the following file(s) for analysis:
{file_list}

Use the analyze_clinical_transcript tool with the file path to analyze these files for HIPAA compliance.""")
        
        # Add project context
        parts.append(f"Project ID: {project_id}")
        
        # Add current user request
        parts.append(f"Current request: {message}")
        
        return "\n\n".join(parts)
    
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
