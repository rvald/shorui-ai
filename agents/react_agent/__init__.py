"""
Standalone ReAct Agent Package

A ReAct (Reasoning + Acting) agent using LangGraph for workflow orchestration.
"""

from .agent import ReActAgent
from .state import AgentState
from .workflow import AgentWorkflow
from .core.prompts import SYSTEM_PROMPT
from .core.model_factory import ModelFactory, ModelType

# LangChain-compatible tools
from .tools import search_regulations, analyze_clinical_transcript

__all__ = [
    # Core
    "ReActAgent",
    "AgentState",
    "AgentWorkflow",
    "SYSTEM_PROMPT",
    "ModelFactory",
    "ModelType",
    # Tools
    "search_regulations",
    "analyze_clinical_transcript",
]
