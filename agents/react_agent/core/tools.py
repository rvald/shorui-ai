"""
Tool Abstraction Layer

This module defines the abstract Tool class that all tools must inherit.
Following the smolagents pattern, tools are defined by:
1. name: Unique identifier
2. description: What the tool does (used in prompts)
3. inputs: Dictionary defining input parameters
4. output_type: Type of output
5. forward(): The actual implementation

Extend this for custom tools or use the @tool decorator for simple functions.

Now includes AsyncTool mixin for non-blocking async execution.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, get_type_hints, Protocol
import inspect
import functools
import asyncio


class Tool(ABC):
    """
    Abstract base class for tools.
    
    All tools must define:
    - name: str
    - description: str
    - inputs: dict[str, dict] with type and description for each param
    - output_type: str
    - forward(**kwargs): The implementation
    
    Example:
    ```python
    class CalculatorTool(Tool):
        name = "calculator"
        description = "Performs basic arithmetic"
        inputs = {
            "expression": {
                "type": "string",
                "description": "Math expression to evaluate"
            }
        }
        output_type = "string"
        
        def forward(self, expression: str) -> str:
            return str(eval(expression))
    ```
    """
    
    name: str
    description: str
    inputs: Dict[str, dict]
    output_type: str
    
    @abstractmethod
    def forward(self, **kwargs) -> Any:
        """Execute the tool with given arguments."""
        ...
    
    def __call__(self, **kwargs) -> Any:
        """Allow calling tool instance directly."""
        return self.forward(**kwargs)
    
    def to_schema(self) -> dict:
        """
        Convert tool to JSON schema for LLM tool calling.
        Compatible with OpenAI function calling format.
        """
        properties = {}
        required = []
        
        for param_name, param_info in self.inputs.items():
            prop = {
                "type": param_info.get("type", "string"),
                "description": param_info.get("description", ""),
            }
            if "enum" in param_info:
                prop["enum"] = param_info["enum"]
            properties[param_name] = prop
            
            if not param_info.get("nullable", False):
                required.append(param_name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
    
    def to_prompt_description(self) -> str:
        """
        Generate a text description for including in prompts.
        Used when LLM doesn't support native tool calling.
        """
        params = []
        for name, info in self.inputs.items():
            param_type = info.get("type", "any")
            desc = info.get("description", "")
            nullable = " (optional)" if info.get("nullable") else ""
            params.append(f"    - {name} ({param_type}{nullable}): {desc}")
        
        params_str = "\n".join(params) if params else "    (no parameters)"
        
        return f"""Tool: {self.name}
Description: {self.description}
Parameters:
{params_str}
Returns: {self.output_type}"""


class AsyncTool(ABC):
    """
    Abstract base class for async tools.
    
    Async tools provide a `forward_async` method for non-blocking execution.
    Tools can inherit from both Tool and AsyncTool to support both sync
    and async usage patterns.
    
    Example:
    ```python
    class AsyncSearchTool(Tool, AsyncTool):
        name = "search"
        description = "Search the web asynchronously"
        inputs = {"query": {"type": "string", "description": "Search query"}}
        output_type = "string"
        
        def forward(self, query: str) -> str:
            # Sync fallback
            return asyncio.run(self.forward_async(query=query))
        
        async def forward_async(self, query: str) -> str:
            # Async implementation
            async with httpx.AsyncClient() as client:
                response = await client.get(f"https://api.search.com?q={query}")
                return response.text
    ```
    """
    
    @abstractmethod
    async def forward_async(self, **kwargs) -> Any:
        """Execute the tool asynchronously with given arguments."""
        ...
    
    async def __call_async__(self, **kwargs) -> Any:
        """Allow calling tool instance directly with async."""
        return await self.forward_async(**kwargs)


class AsyncToolMixin:
    """
    Mixin that adds async support to any Tool.
    
    Provides a default `forward_async` implementation that runs
    the sync `forward` method in a thread pool, allowing sync tools
    to be used in async contexts without blocking.
    
    Example:
    ```python
    class MyTool(Tool, AsyncToolMixin):
        name = "my_tool"
        # ... define as normal sync tool
        
        def forward(self, **kwargs):
            # Sync implementation
            return "result"
    
    # Now can be used async:
    result = await my_tool.forward_async(arg="value")
    ```
    """
    
    async def forward_async(self, **kwargs) -> Any:
        """
        Run the sync forward method in a thread pool.
        
        This allows sync tools to be used in async contexts without
        blocking the event loop. Override this for true async implementations.
        """
        # Run sync method in thread pool to avoid blocking
        return await asyncio.to_thread(self.forward, **kwargs)


class FunctionTool(Tool):
    """
    A Tool wrapper around a regular function.
    Created automatically by the @tool decorator.
    """
    
    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self._func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or f"Tool: {self.name}"
        
        # Extract input schema from function signature and type hints
        self.inputs = self._extract_inputs(func)
        
        # Try to get output type from type hints
        hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
        return_type = hints.get('return', Any)
        self.output_type = self._type_to_string(return_type)
    
    def _extract_inputs(self, func: Callable) -> Dict[str, dict]:
        """Extract input schema from function signature."""
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
        
        inputs = {}
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
                
            param_type = hints.get(param_name, Any)
            has_default = param.default != inspect.Parameter.empty
            
            inputs[param_name] = {
                "type": self._type_to_string(param_type),
                "description": f"Parameter: {param_name}",
                "nullable": has_default,
            }
        
        return inputs
    
    def _type_to_string(self, type_hint) -> str:
        """Convert Python type hint to JSON schema type string."""
        type_map = {
            str: "string",
            int: "integer", 
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        
        # Handle basic types
        if type_hint in type_map:
            return type_map[type_hint]
        
        # Handle string type names
        if isinstance(type_hint, str):
            return type_hint
            
        # Default to string
        return "string"
    
    def forward(self, **kwargs) -> Any:
        return self._func(**kwargs)


def tool(func: Callable = None, *, name: str = None, description: str = None):
    """
    Decorator to create a Tool from a function.
    
    Usage:
    ```python
    @tool
    def search(query: str) -> str:
        '''Search the web for information.'''
        return f"Results for: {query}"
    
    # Or with custom name/description:
    @tool(name="web_search", description="Search the internet")
    def search(query: str) -> str:
        return f"Results for: {query}"
    ```
    """
    def decorator(f):
        return FunctionTool(f, name=name, description=description)
    
    if func is not None:
        # Called without arguments: @tool
        return decorator(func)
    else:
        # Called with arguments: @tool(name=...)
        return decorator


class AsyncFunctionTool(Tool, AsyncTool):
    """
    A Tool wrapper around an async function.
    
    Supports both sync and async usage:
    - forward(): Runs async function using asyncio.run()
    - forward_async(): Native async execution
    
    Created automatically by the @async_tool decorator.
    """
    
    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"Function {func.__name__} must be async (defined with 'async def')")
        
        self._func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or f"Tool: {self.name}"
        
        # Extract input schema from function signature and type hints
        self.inputs = self._extract_inputs(func)
        
        # Try to get output type from type hints
        hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
        return_type = hints.get('return', Any)
        self.output_type = self._type_to_string(return_type)
    
    def _extract_inputs(self, func: Callable) -> Dict[str, dict]:
        """Extract input schema from function signature."""
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
        
        inputs = {}
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
                
            param_type = hints.get(param_name, Any)
            has_default = param.default != inspect.Parameter.empty
            
            inputs[param_name] = {
                "type": self._type_to_string(param_type),
                "description": f"Parameter: {param_name}",
                "nullable": has_default,
            }
        
        return inputs
    
    def _type_to_string(self, type_hint) -> str:
        """Convert Python type hint to JSON schema type string."""
        type_map = {
            str: "string",
            int: "integer", 
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        
        # Handle basic types
        if type_hint in type_map:
            return type_map[type_hint]
        
        # Handle string type names
        if isinstance(type_hint, str):
            return type_hint
            
        # Default to string
        return "string"
    
    def forward(self, **kwargs) -> Any:
        """Sync execution - runs async function with asyncio.run()."""
        return asyncio.run(self._func(**kwargs))
    
    async def forward_async(self, **kwargs) -> Any:
        """Async execution - native coroutine call."""
        return await self._func(**kwargs)


def async_tool(func: Callable = None, *, name: str = None, description: str = None):
    """
    Decorator to create an AsyncTool from an async function.
    
    The resulting tool supports both sync and async usage:
    - tool.forward(**kwargs): Runs with asyncio.run()
    - await tool.forward_async(**kwargs): Native async
    
    Usage:
    ```python
    @async_tool
    async def fetch_data(url: str) -> str:
        '''Fetch data from a URL asynchronously.'''
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            return response.text
    
    # Sync usage
    result = fetch_data(url="https://example.com")
    
    # Async usage
    result = await fetch_data.forward_async(url="https://example.com")
    ```
    """
    def decorator(f):
        if not asyncio.iscoroutinefunction(f):
            raise TypeError(
                f"@async_tool can only be used on async functions. "
                f"'{f.__name__}' is not async. Use @tool instead."
            )
        return AsyncFunctionTool(f, name=name, description=description)
    
    if func is not None:
        # Called without arguments: @async_tool
        return decorator(func)
    else:
        # Called with arguments: @async_tool(name=...)
        return decorator

