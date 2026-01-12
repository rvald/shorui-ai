"""Type defenitions for query routing"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class RouteType(str, Enum):
    """Execution route types."""
    DIRECT_TOOL = "direct_tool"      # Pattern match → direct tool call (0 LLM)
    PROMPT_CHAIN = "prompt_chain"    # Use specialized chain
    LIGHT_AGENT = "light_agent"      # ReAct with max 3 steps
    FULL_AGENT = "full_agent"        # Full ReAct with 10 steps
    

class ExecutionPlan(BaseModel):
    """Plan for executing a query with full validation."""
    
    route_type: RouteType = Field(
        ..., 
        description="Type of execution route to use"
    )
    
    executor_name: str = Field(
        ..., 
        description="Name of executor that will handle this query"
    )
    
    model_id: str = Field(
        default="gpt-4o-mini",
        description="LLM model to use, or 'none' for direct execution"
    )
    
    max_steps: int = Field(
        default=5,
        ge=0,
        le=20,
        description="Maximum steps for agent execution"
    )
    
    chain_name: Optional[str] = Field(
        default=None,
        description="Name of prompt chain (for PROMPT_CHAIN route)"
    )
    
    tool_name: Optional[str] = Field(
        default=None,
        description="Name of tool to call directly (for DIRECT_TOOL route)"
    )
    
    tool_args: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Parsed arguments for direct tool call"
    )
    
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Router confidence score for monitoring"
    )
    
    class Config:
        """Pydantic config."""
        frozen = False  # Allow modification
        use_enum_values = True  # Serialize enums as values