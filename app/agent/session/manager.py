"""
Session Manager

Manages agent session lifecycle with async storage.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.agent.session.types import Session, Message
from app.agent.session.storage import SessionStorage


class SessionNotFoundError(Exception):
    """Raised when session is not found."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class SessionManager:
    """
    Manage agent sessions with async storage.
    
    Handles session creation, retrieval, updates, and cleanup.
    
    Example:
    ```python
    storage = RedisSessionStorage("redis://localhost:6379")
    manager = SessionManager(storage)
    
    # Create session
    session_id = await manager.create_session(metadata={"project_id": "test"})
    
    # Get and update session
    session = await manager.get_session(session_id)
    session.add_message("user", "Hello")
    await manager.save_session(session)
    ```
    """
    
    def __init__(
        self,
        storage: SessionStorage,
        ttl: int = 3600,
        max_messages: int = 50,
    ):
        """
        Initialize session manager.
        
        Args:
            storage: Storage backend (Redis, in-memory, etc.)
            ttl: Session TTL in seconds (default 1 hour)
            max_messages: Max messages to keep per session
        """
        self.storage = storage
        self.ttl = ttl
        self.max_messages = max_messages
    
    async def create_session(
        self,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Create a new session.
        
        Args:
            session_id: Optional custom session ID
            metadata: Optional session metadata
            
        Returns:
            Session ID
        """
        session = Session(
            id=session_id or str(uuid.uuid4()),
            metadata=metadata or {},
        )
        
        await self.storage.set(
            self._key(session.id),
            session.to_json(),
            self.ttl,
        )
        
        return session.id
    
    async def get_session(self, session_id: str) -> Session:
        """
        Retrieve session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session instance
            
        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        data = await self.storage.get(self._key(session_id))
        
        if not data:
            raise SessionNotFoundError(session_id)
        
        session = Session.from_json(data)
        session.last_accessed = datetime.now()
        
        return session
    
    async def save_session(self, session: Session) -> None:
        """
        Save session to storage.
        
        Also handles message truncation if over max_messages.
        
        Args:
            session: Session to save
        """
        # Truncate old messages if needed
        if len(session.messages) > self.max_messages:
            session.messages = session.messages[-self.max_messages:]
        
        session.last_accessed = datetime.now()
        
        await self.storage.set(
            self._key(session.id),
            session.to_json(),
            self.ttl,
        )
    
    async def delete_session(self, session_id: str) -> None:
        """
        Delete session.
        
        Args:
            session_id: Session ID to delete
        """
        await self.storage.delete(self._key(session_id))
    
    async def session_exists(self, session_id: str) -> bool:
        """
        Check if session exists.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if session exists
        """
        data = await self.storage.get(self._key(session_id))
        return data is not None
    
    def _key(self, session_id: str) -> str:
        """Generate storage key for session ID."""
        return f"session:{session_id}"
