# Standalone ReAct Agent Package
"""
A standalone ReAct (Reasoning + Acting) agent implementation.
Follows smolagents abstraction patterns for easy extension.
"""

from .agent import ReActAgent
from .core.models import Model, ChatMessage, MockModel
from .core.tools import Tool, tool
from .core.memory import AgentMemory, ActionStep, ToolCall
from .default_tools import FinalAnswerTool, CalculatorTool

# Backward compatibility alias
BasicReActAgent = ReActAgent

# Shorui AI Platform Tools
from .tools import (
    RAGSearchTool,
    UploadDocumentTool,
    CheckIngestionStatusTool,
    AnalyzeClinicalTranscriptTool,
    GetComplianceReportTool,
    QueryAuditLogTool,
    LookupHIPAARegulationTool,
    CheckSystemHealthTool,
)

__all__ = [
    # Core
    "ReActAgent",
    "BasicReActAgent",  # Alias for backward compatibility
    "Model",
    "ChatMessage", 
    "MockModel",
    "Tool",
    "tool",
    "AgentMemory",
    "ActionStep",
    "ToolCall",
    "FinalAnswerTool",
    "CalculatorTool",
    # Shorui AI Tools
    "RAGSearchTool",
    "UploadDocumentTool",
    "CheckIngestionStatusTool",
    "AnalyzeClinicalTranscriptTool",
    "GetComplianceReportTool",
    "QueryAuditLogTool",
    "LookupHIPAARegulationTool",
    "CheckSystemHealthTool",
]
