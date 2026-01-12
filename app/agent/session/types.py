"""Session types using Pydantic for validation and serialization."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator
import uuid

class Message(BaseModel):
    """A single message in the conversation."""
    
    role: Literal["system", "user", "assistant", "tool"] = Field(
        ...,
        description="Message role"
    )
    
    content: str = Field(
        ...,
        description="Message content"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When this message was created"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata (e.g., tokens, model used)"
    )
    
    class Config:
        """Pydantic config."""
        frozen = False
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    @field_validator('content')
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        """Ensure content is not empty."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v
        
class Session(BaseModel):
    """Agent session with conversation history."""
    
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique session identifier"
    )
    
    messages: List[Message] = Field(
        default_factory=list,
        description="Conversation message history"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session metadata (project_id, user context, etc.)"
    )
    
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Session creation timestamp"
    )
    
    last_accessed: datetime = Field(
        default_factory=datetime.now,
        description="Last access timestamp (for TTL)"
    )
    
    class Config:
        """Pydantic config."""
        frozen = False
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def add_message(self, role: str, content: str, **metadata) -> None:
        """Add a message to the session.
        
        Args:
            role: Message role (user, assistant, etc.)
            content: Message content
            **metadata: Optional metadata to attach
        """
        message = Message(role=role, content=content, metadata=metadata)
        self.messages.append(message)
        self.last_accessed = datetime.now()
    
    def get_recent_messages(self, n: int = 10) -> List[Message]:
        """Get the last N messages (for context window management).
        
        Args:
            n: Number of recent messages to return
            
        Returns:
            List of recent messages
        """
        return self.messages[-n:] if len(self.messages) > n else self.messages
    
    def clear_history(self) -> None:
        """Clear all messages (keep session metadata)."""
        self.messages = []
        self.last_accessed = datetime.now()
    
    def to_json(self) -> str:
        """Serialize to JSON string for Redis storage."""
        return self.model_dump_json()
    
    @classmethod
    def from_json(cls, json_str: str) -> "Session":
        """Deserialize from JSON string.
        
        Args:
            json_str: JSON string from Redis
            
        Returns:
            Session instance
        """
        return cls.model_validate_json(json_str)