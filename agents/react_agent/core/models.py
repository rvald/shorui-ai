"""
Model Abstraction Layer

This module defines the abstract Model class that all LLM implementations must inherit.
Following the smolagents pattern, models are responsible for:
1. Taking a list of chat messages
2. Generating a response (potentially with tool calls)

Extend this for custom LLM integrations (OpenAI, Anthropic, local models, etc.)

Updated to use Pydantic BaseModel for better validation and serialization.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import json
import re
import uuid
import asyncio

from pydantic import BaseModel, Field


class ToolCallFunction(BaseModel):
    """Function details within a tool call."""
    name: str
    arguments: Union[Dict[str, Any], str]
    
    class Config:
        extra = "forbid"


class ChatMessageToolCall(BaseModel):
    """Represents a tool call in a chat message."""
    id: str
    function: ToolCallFunction
    type: str = Field(default="function")
    
    class Config:
        extra = "forbid"


class ChatMessage(BaseModel):
    """
    A message in the conversation.
    
    Attributes:
        role: One of "system", "user", "assistant", "tool"
        content: The text content of the message
        tool_calls: List of tool calls if this is an assistant message with actions
    """
    role: str  # "system", "user", "assistant", "tool"
    content: Optional[str] = Field(default=None)
    tool_calls: Optional[List[ChatMessageToolCall]] = Field(default=None)
    
    class Config:
        extra = "forbid"
    
    def to_dict(self) -> dict:
        """Convert to dictionary format for API calls."""
        result = {"role": self.role}
        if self.content is not None:
            result["content"] = self.content
        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments if isinstance(tc.function.arguments, str) 
                                     else json.dumps(tc.function.arguments)
                    }
                }
                for tc in self.tool_calls
            ]
        return result


class Model(ABC):
    """
    Abstract base class for language model implementations.
    
    All models must implement the `generate` method. Models can optionally
    support native tool calling, or fall back to parsing tool calls from text.
    
    To create a custom model:
    
    ```python
    class MyCustomModel(Model):
        def __init__(self, api_key: str):
            self.api_key = api_key
            
        def generate(self, messages: List[ChatMessage], **kwargs) -> ChatMessage:
            # Call your LLM API here
            response = my_api_call(messages)
            return ChatMessage(role="assistant", content=response)
    ```
    """
    
    @abstractmethod
    def generate(
        self,
        messages: List[ChatMessage],
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[List[dict]] = None,
        **kwargs,
    ) -> ChatMessage:
        """
        Generate a response from the model.
        
        Args:
            messages: List of chat messages forming the conversation
            stop_sequences: Optional list of strings that stop generation
            tools: Optional list of tool schemas for native tool calling
            **kwargs: Additional model-specific parameters
            
        Returns:
            ChatMessage with the model's response
        """
        ...
    
    def parse_tool_calls(self, message: ChatMessage) -> ChatMessage:
        """
        Parse tool calls from message content if not natively supported.
        
        Override this if your model outputs tool calls in a specific format.
        Default implementation looks for JSON action blocks.
        """
        if message.tool_calls:
            return message
            
        if not message.content:
            return message
        
        # Try to extract JSON from the content
        content = message.content
        
        # Remove markdown code block markers if present
        if "```json" in content:
            # Extract content between ```json and ```
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                content = content[start:end].strip()
        elif "```" in content:
            # Generic code block
            start = content.find("```") + 3
            end = content.find("```", start)
            if end > start:
                content = content[start:end].strip()
        
        # Try to find and parse JSON object with "name" key
        try:
            # Find the first { and try to parse from there
            brace_start = content.find("{")
            if brace_start == -1:
                return message
            
            # Count braces to find matching closing brace
            depth = 0
            brace_end = -1
            for i, char in enumerate(content[brace_start:], brace_start):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        brace_end = i + 1
                        break
            
            if brace_end == -1:
                return message
            
            json_str = content[brace_start:brace_end]
            action_dict = json.loads(json_str)
            
            if "name" in action_dict:
                tool_call = ChatMessageToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    function=ToolCallFunction(
                        name=action_dict["name"],
                        arguments=action_dict.get("arguments", {})
                    )
                )
                # Create new message with tool_calls
                return ChatMessage(
                    role=message.role,
                    content=message.content,
                    tool_calls=[tool_call]
                )
        except (json.JSONDecodeError, KeyError):
            pass
            
        return message
    
    def __call__(self, messages: List[ChatMessage], **kwargs) -> ChatMessage:
        """Allow calling model instance directly."""
        return self.generate(messages, **kwargs)

class AsyncModel(ABC):
    """
    Abstract base class for async language model implementations.
    
    Extends Model with async capabilities for non-blocking I/O.
    Models should inherit from both Model and AsyncModel to support
    both sync and async usage patterns.
    """
    
    @abstractmethod
    async def generate_async(
        self,
        messages: List[ChatMessage],
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[List[dict]] = None,
        **kwargs,
    ) -> ChatMessage:
        """
        Generate a response asynchronously.
        
        Args:
            messages: List of chat messages forming the conversation
            stop_sequences: Optional list of strings that stop generation
            tools: Optional list of tool schemas for native tool calling
            **kwargs: Additional model-specific parameters
            
        Returns:
            ChatMessage with the model's response
        """
        ...  


class MockModel(Model):
    """
    A mock model for testing that returns predefined responses.
    
    Usage:
    ```python
    responses = [
        ChatMessage(role="assistant", content="...", tool_calls=[...]),
        ChatMessage(role="assistant", content="final answer"),
    ]
    model = MockModel(responses)
    ```
    """
    
    def __init__(self, responses: List[ChatMessage]):
        """
        Args:
            responses: List of ChatMessages to return in sequence
        """
        self.responses = responses
        self.call_count = 0
        
    def generate(
        self,
        messages: List[ChatMessage],
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[List[dict]] = None,
        **kwargs,
    ) -> ChatMessage:
        if self.call_count >= len(self.responses):
            # Return a final answer if we run out of responses
            return ChatMessage(
                role="assistant",
                content='{"name": "final_answer", "arguments": {"answer": "Mock complete"}}'
            )
        
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


class OpenAIModel(Model, AsyncModel):
    """
    OpenAI API model implementation.
    
    Requires: pip install openai
    
    Usage:
    ```python
    model = OpenAIModel(api_key="sk-...", model_id="gpt-4")
    ```
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        import os
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY or pass api_key.")
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Add these lines for async support
        from openai import AsyncOpenAI
        self._async_client = AsyncOpenAI(api_key=self.api_key)
        
    def generate(
        self,
        messages: List[ChatMessage],
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[List[dict]] = None,
        **kwargs,
    ) -> ChatMessage:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Install openai: pip install openai")
            
        client = OpenAI(api_key=self.api_key)
        
        # Convert messages to OpenAI format
        openai_messages = [msg.to_dict() for msg in messages]
        
        # Build request params
        params = {
            "model": self.model_id,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        
        if stop_sequences:
            params["stop"] = stop_sequences
            
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        
        response = client.chat.completions.create(**params)
        choice = response.choices[0]
        
        # Parse tool calls if present
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                ChatMessageToolCall(
                    id=tc.id,
                    function=ToolCallFunction(
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                    )
                )
                for tc in choice.message.tool_calls
            ]
        
        return ChatMessage(
            role="assistant",
            content=choice.message.content,
            tool_calls=tool_calls,
        )

    async def generate_async(
        self,
        messages: List[ChatMessage],
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[List[dict]] = None,
        **kwargs,
    ) -> ChatMessage:
        """Async generation using OpenAI async client."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("Install openai: pip install openai")
        
        # Convert messages to OpenAI format
        openai_messages = [msg.to_dict() for msg in messages]
        
        # Build request params
        params = {
            "model": self.model_id,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        
        if stop_sequences:
            params["stop"] = stop_sequences
            
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        
        # Async API call
        response = await self._async_client.chat.completions.create(**params)
        choice = response.choices[0]
        
        # Parse tool calls if present
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                ChatMessageToolCall(
                    id=tc.id,
                    function=ToolCallFunction(
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                    )
                )
                for tc in choice.message.tool_calls
            ]
        
        return ChatMessage(
            role="assistant",
            content=choice.message.content,
            tool_calls=tool_calls,
        )
