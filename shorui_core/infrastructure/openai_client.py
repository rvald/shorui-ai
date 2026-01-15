"""
OpenAI Client Singleton

Provides a shared OpenAI client instance for efficient connection reuse
across all services that need LLM inference.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from shorui_core.config import settings

if TYPE_CHECKING:
    from openai import OpenAI


class OpenAIClientSingleton:
    """
    Singleton wrapper for OpenAI client.
    
    Ensures only one client instance is created and reused across
    all services, avoiding connection overhead on each request.
    
    Usage:
        client = OpenAIClientSingleton.get_instance()
        response = client.chat.completions.create(...)
    """
    
    _instance: "OpenAI | None" = None
    
    @classmethod
    def get_instance(cls) -> "OpenAI":
        """
        Get or create the OpenAI client instance.
        
        Returns:
            OpenAI: The shared client instance.
            
        Raises:
            ImportError: If openai package is not installed.
            ValueError: If OPENAI_API_KEY is not configured.
        """
        if cls._instance is None:
            from openai import OpenAI
            
            api_key = settings.OPENAI_API_KEY
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY not configured. "
                    "Set it in .env or environment variables."
                )
            
            cls._instance = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized (singleton)")
        
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton instance.
        
        Useful for testing or when API key changes.
        """
        cls._instance = None


def get_openai_client() -> "OpenAI":
    """Convenience function to get the OpenAI client."""
    return OpenAIClientSingleton.get_instance()
