"""
Session Storage Adapters

Async storage implementations for session management.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Optional, Protocol


class SessionStorage(Protocol):
    """Abstract storage interface for sessions."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        ...
    
    @abstractmethod
    async def set(self, key: str, value: str, ttl: int) -> None:
        """Set value with TTL in seconds."""
        ...
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key."""
        ...


class RedisSessionStorage:
    """
    Async Redis storage implementation.
    
    Uses redis.asyncio for non-blocking operations.
    
    Example:
    ```python
    storage = RedisSessionStorage("redis://localhost:6379")
    await storage.set("session:abc", '{"id": "abc"}', ttl=3600)
    data = await storage.get("session:abc")
    ```
    """
    
    def __init__(self, redis_url: str):
        import redis.asyncio as redis
        self.client = redis.from_url(redis_url, decode_responses=True)
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        return await self.client.get(key)
    
    async def set(self, key: str, value: str, ttl: int) -> None:
        """Set value in Redis with TTL."""
        await self.client.setex(key, ttl, value)
    
    async def delete(self, key: str) -> None:
        """Delete key from Redis."""
        await self.client.delete(key)
    
    async def close(self) -> None:
        """Close Redis connection."""
        await self.client.close()


class InMemorySessionStorage:
    """
    In-memory storage for testing and development.
    
    Note: Does not persist across restarts. TTL is ignored.
    """
    
    def __init__(self):
        self._data: dict[str, str] = {}
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from memory."""
        return self._data.get(key)
    
    async def set(self, key: str, value: str, ttl: int) -> None:
        """Set value in memory (TTL ignored)."""
        self._data[key] = value
    
    async def delete(self, key: str) -> None:
        """Delete key from memory."""
        self._data.pop(key, None)
    
    def clear(self) -> None:
        """Clear all data."""
        self._data.clear()
