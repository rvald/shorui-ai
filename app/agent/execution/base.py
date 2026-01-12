"""Base types and interfaces for execution strategies using Pydantic."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel, Field

class ExecutionResult(BaseModel):
    """Result from any executor with full validation."""
    
    content: str = Field(
        ...,
        description="Final answer/response to user"
    )
    
    steps: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Execution steps taken (for transparency)"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution metadata (tokens, latency, route type, etc.)"
    )
    
    success: bool = Field(
        default=True,
        description="Whether execution completed successfully"
    )
    
    error: Optional[str] = Field(
        default=None,
        description="Error message if execution failed"
    )
    
    class Config:
        """Pydantic config."""
        frozen = False
        arbitrary_types_allowed = True
    
    def add_metadata(self, key: str, value: Any) -> None:
        """Convenience method to add metadata."""
        self.metadata[key] = value
    
    def add_step(self, step: Dict[str, Any]) -> None:
        """Convenience method to add execution step."""
        self.steps.append(step)

class BaseExecutor(Protocol):
    """Protocol defining the executor interface.
    
    All executors must implement this interface to be compatible
    with the orchestrator. Uses Protocol for structural subtyping
    (duck typing with type safety).
    """
    
    @property
    def name(self) -> str:
        """Unique executor identifier."""
        ...
    
    async def execute(
        self,
        query: str,
        plan: Any,  # ExecutionPlan from routing.types
        context: Dict[str, Any],
    ) -> ExecutionResult:
        """Execute query according to the execution plan.
        
        Args:
            query: User's query string
            plan: ExecutionPlan specifying how to execute
            context: Additional context (session, project_id, etc.)
        
        Returns:
            ExecutionResult with answer and metadata
        """
        ...