"""
Memory System

This module provides the memory/state tracking for the agent.
Following smolagents patterns, memory stores:
1. Steps taken (thoughts, actions, observations)
2. Conversation history as messages

The memory can be converted to chat messages for context in LLM calls.

Updated to use Pydantic BaseModel for better validation and serialization.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import json

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """
    Represents a tool call made by the agent.
    
    Attributes:
        name: The tool's name
        arguments: Dictionary of arguments passed to the tool
        id: Unique identifier for this call
    """
    name: str
    arguments: Dict[str, Any]
    id: str
    
    class Config:
        extra = "forbid"
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


class ActionStep(BaseModel):
    """
    Represents one step in the ReAct loop.
    
    Attributes:
        step_number: Which step this is (1-indexed)
        thought: The agent's reasoning (from LLM output)
        tool_calls: List of tool calls made
        observation: Result from executing the tool
        error: Any error that occurred
    """
    step_number: int
    thought: Optional[str] = Field(default=None)
    tool_calls: Optional[List[ToolCall]] = Field(default=None)
    observation: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    
    class Config:
        extra = "forbid"
    
    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "thought": self.thought,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else [],
            "observation": self.observation,
            "error": self.error,
        }


class TaskStep(BaseModel):
    """The initial task given to the agent."""
    task: str
    
    class Config:
        extra = "forbid"


class AgentMemory:
    """
    Memory for the agent containing all steps taken.
    
    Provides methods to:
    - Add steps
    - Convert to chat messages for LLM context
    - Reset for new tasks
    
    Example:
    ```python
    memory = AgentMemory()
    memory.add_task("What is 2 + 2?")
    memory.add_step(ActionStep(
        step_number=1,
        thought="I should calculate this",
        tool_calls=[ToolCall(name="calculator", arguments={"expr": "2+2"}, id="c1")],
        observation="4"
    ))
    messages = memory.to_messages()
    ```
    """
    
    def __init__(self):
        self.task: Optional[str] = None
        self.steps: List[ActionStep] = []
        
    def reset(self):
        """Clear all memory."""
        self.task = None
        self.steps = []
        
    def add_task(self, task: str):
        """Set the current task."""
        self.task = task
        
    def add_step(self, step: ActionStep):
        """Add a completed step."""
        self.steps.append(step)
        
    def to_messages(self) -> list:
        """
        Convert memory to chat message format.
        
        Returns list of ChatMessage objects.
        """
        from .models import ChatMessage
        
        messages = []
        
        # Add task as user message
        if self.task:
            messages.append(ChatMessage(role="user", content=f"Task: {self.task}"))
        
        # Add each step
        for step in self.steps:
            # Add thought/action as assistant message
            if step.thought or step.tool_calls:
                content_parts = []
                if step.thought:
                    content_parts.append(f"Thought: {step.thought}")
                if step.tool_calls:
                    for tc in step.tool_calls:
                        action_json = json.dumps({
                            "name": tc.name,
                            "arguments": tc.arguments
                        })
                        content_parts.append(f"Action: {action_json}")
                
                messages.append(ChatMessage(
                    role="assistant",
                    content="\n".join(content_parts)
                ))
            
            # Add observation as user message (simulating environment feedback)
            if step.observation:
                messages.append(ChatMessage(
                    role="user", 
                    content=f"Observation: {step.observation}"
                ))
            elif step.error:
                messages.append(ChatMessage(
                    role="user",
                    content=f"Error: {step.error}\nPlease try again with a different approach."
                ))
        
        return messages
    
    def get_last_observation(self) -> Optional[str]:
        """Get the most recent observation."""
        if self.steps:
            return self.steps[-1].observation
        return None
    
    def get_steps_summary(self) -> List[dict]:
        """Get a summary of all steps for logging/debugging."""
        return [step.to_dict() for step in self.steps]
