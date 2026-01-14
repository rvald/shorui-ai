"""
BasicReActAgent

A standalone ReAct (Reasoning + Acting) agent implementation.
Follows the loop: Thought → Action → Observation → Repeat until final_answer.

This implementation follows smolagents' abstraction patterns for easy extension.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import re
import uuid

# Support both package import and direct script execution
try:
    from .core.models import Model, ChatMessage
    from .core.tools import Tool
    from .core.memory import AgentMemory, ActionStep, ToolCall
    from .core.prompts import DEFAULT_SYSTEM_PROMPT
    from .default_tools import FinalAnswerTool
except ImportError:
    from core.models import Model, ChatMessage
    from core.tools import Tool
    from core.memory import AgentMemory, ActionStep, ToolCall
    from core.prompts import DEFAULT_SYSTEM_PROMPT
    from default_tools import FinalAnswerTool


@dataclass
class AgentResult:
    """
    Result of an agent run.
    
    Attributes:
        output: The final answer returned by the agent
        steps: List of steps taken during the run
        success: Whether the run completed successfully (vs hitting max steps)
    """
    output: Any
    steps: List[ActionStep]
    success: bool


class ReActAgent:
    """
    A basic ReAct agent that can use tools to solve tasks.
    
    The agent follows the ReAct paradigm:
    1. **Thought**: Reason about the current state and what to do next
    2. **Action**: Choose a tool and arguments to call
    3. **Observation**: Receive the result of the tool execution
    4. Repeat until final_answer is called or max_steps is reached
    
    Example:
    ```python
    from react_agent import ReActAgent, CalculatorTool
    from react_agent.core import OpenAIModel
    
    model = OpenAIModel(api_key="sk-...")
    agent = ReActAgent(
        tools=[CalculatorTool()],
        model=model,
    )
    result = agent.run("What is 15 * 7?")
    print(result.output)  # "15 * 7 = 105"
    ```
    
    Args:
        tools: List of Tool instances the agent can use
        model: Model instance for LLM calls
        system_prompt: Custom system prompt (uses default if None)
        max_steps: Maximum number of action steps before forcing final answer
        verbose: Whether to print step-by-step output
    """
    
    def __init__(
        self,
        tools: List[Tool],
        model: Model,
        system_prompt: Optional[str] = None,
        max_steps: int = 10,
        verbose: bool = False,
    ):
        # Store tools by name, always include final_answer
        self.tools: Dict[str, Tool] = {t.name: t for t in tools}
        if "final_answer" not in self.tools:
            self.tools["final_answer"] = FinalAnswerTool()
        
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        
        # Build system prompt with tool descriptions
        self.system_prompt = system_prompt or self._build_system_prompt()
        
        # Initialize memory
        self.memory = AgentMemory()
        
    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool descriptions."""
        tool_descriptions = "\n\n".join([
            tool.to_prompt_description() 
            for tool in self.tools.values()
        ])
        return DEFAULT_SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions)
    
    def run(self, task: str) -> AgentResult:
        """
        Run the agent on a task.
        
        Args:
            task: The task/question for the agent to solve
            
        Returns:
            AgentResult with the output, steps taken, and success status
        """
        # Reset memory for new run
        self.memory.reset()
        self.memory.add_task(task)
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Task: {task}")
            print(f"{'='*60}")
        
        final_answer = None
        step_number = 0
        
        while step_number < self.max_steps:
            step_number += 1
            
            if self.verbose:
                print(f"\n--- Step {step_number} ---")
            
            # Execute one step of the ReAct loop
            step, is_final = self._step(step_number)
            self.memory.add_step(step)
            
            if is_final:
                final_answer = step.observation
                break
        
        # If we hit max steps without final answer, force one
        success = final_answer is not None
        if not success:
            if self.verbose:
                print(f"\n⚠️  Max steps ({self.max_steps}) reached. Forcing final answer.")
            final_answer = self._force_final_answer()
        
        return AgentResult(
            output=final_answer,
            steps=self.memory.steps,
            success=success,
        )
    
    def _step(self, step_number: int) -> Tuple[ActionStep, bool]:
        """
        Execute one step of the ReAct loop.
        
        Returns:
            Tuple of (ActionStep, is_final_answer)
        """
        # Build messages for the model
        messages = self._build_messages()
        
        # Get model response
        try:
            response = self.model.generate(messages)
            
            # Parse tool calls if not already present
            response = self.model.parse_tool_calls(response)
            
        except Exception as e:
            # Handle generation errors
            step = ActionStep(
                step_number=step_number,
                thought=None,
                tool_calls=None,
                observation=None,
                error=f"Model generation error: {e}"
            )
            if self.verbose:
                print(f"Error: {e}")
            return step, False
        
        # Extract thought from content
        thought = response.content
        if self.verbose and thought:
            print(f"Thought: {thought[:200]}..." if len(thought or "") > 200 else f"Thought: {thought}")
        
        # Check if we got tool calls
        if not response.tool_calls:
            step = ActionStep(
                step_number=step_number,
                thought=thought,
                tool_calls=None,
                observation=None,
                error="No tool call found in response"
            )
            if self.verbose:
                print("Error: No tool call found")
            return step, False
        
        # Process the first tool call
        tool_call_msg = response.tool_calls[0]
        tool_name = tool_call_msg.function.name
        tool_args = tool_call_msg.function.arguments
        
        # Ensure arguments is a dict
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except json.JSONDecodeError:
                tool_args = {"input": tool_args}
        
        tool_call = ToolCall(
            name=tool_name,
            arguments=tool_args,
            id=tool_call_msg.id or f"call_{uuid.uuid4().hex[:8]}"
        )
        
        if self.verbose:
            print(f"Action: {tool_name}({tool_args})")
        
        # Execute the tool
        observation, is_final = self._execute_tool(tool_call)
        
        if self.verbose:
            obs_preview = str(observation)[:200] + "..." if len(str(observation)) > 200 else str(observation)
            print(f"Observation: {obs_preview}")
        
        step = ActionStep(
            step_number=step_number,
            thought=thought,
            tool_calls=[tool_call],
            observation=str(observation),
            error=None
        )
        
        return step, is_final
    
    def _build_messages(self) -> List[ChatMessage]:
        """Build the message list for the model."""
        messages = [
            ChatMessage(role="system", content=self.system_prompt)
        ]
        
        # Add memory (task + previous steps)
        messages.extend(self.memory.to_messages())
        
        return messages
    
    def _execute_tool(self, tool_call: ToolCall) -> Tuple[Any, bool]:
        """
        Execute a tool call.
        
        Returns:
            Tuple of (observation, is_final_answer)
        """
        tool_name = tool_call.name
        
        # Check if tool exists
        if tool_name not in self.tools:
            available = ", ".join(self.tools.keys())
            return f"Error: Unknown tool '{tool_name}'. Available tools: {available}", False
        
        tool = self.tools[tool_name]
        is_final = tool_name == "final_answer"
        
        try:
            result = tool(**tool_call.arguments)
            return result, is_final
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}", False
    
    def _force_final_answer(self) -> str:
        """Force a final answer when max steps is reached."""
        # Ask the model to summarize what it knows
        messages = self._build_messages()
        messages.append(ChatMessage(
            role="user",
            content="You've reached the maximum number of steps. Please provide your best final answer now using the final_answer tool."
        ))
        
        try:
            response = self.model.generate(messages)
            response = self.model.parse_tool_calls(response)
            
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                if tool_call.function.name == "final_answer":
                    args = tool_call.function.arguments
                    if isinstance(args, dict):
                        return args.get("answer", str(args))
                    return str(args)
            
            return response.content or "Could not determine answer"
        except Exception as e:
            return f"Could not generate final answer: {e}"
    
    # =========================================================================
    # Async Execution Methods
    # =========================================================================
    
    async def run_async(self, task: str) -> AgentResult:
        """
        Run the agent asynchronously with parallel tool execution.
        
        Args:
            task: The task/question for the agent to solve
            
        Returns:
            AgentResult with the output, steps taken, and success status
        """
        import asyncio
        
        # Reset memory for new run
        self.memory.reset()
        self.memory.add_task(task)
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Task: {task}")
            print(f"{'='*60}")
        
        final_answer = None
        step_number = 0
        
        while step_number < self.max_steps:
            step_number += 1
            
            if self.verbose:
                print(f"\n--- Step {step_number} (async) ---")
            
            # Execute one step of the ReAct loop (async)
            step, is_final = await self._step_async(step_number)
            self.memory.add_step(step)
            
            if is_final:
                final_answer = step.observation
                break
        
        # If we hit max steps without final answer, force one
        success = final_answer is not None
        if not success:
            if self.verbose:
                print(f"\n⚠️  Max steps ({self.max_steps}) reached. Forcing final answer.")
            final_answer = await self._force_final_answer_async()
        
        return AgentResult(
            output=final_answer,
            steps=self.memory.steps,
            success=success,
        )
    
    async def _step_async(self, step_number: int) -> Tuple[ActionStep, bool]:
        """
        Execute one async step of the ReAct loop.
        
        Uses async model generation and parallel tool execution.
        """
        import asyncio
        
        # Build messages for the model
        messages = self._build_messages()
        
        # Get model response (async if available)
        try:
            if hasattr(self.model, 'generate_async'):
                response = await self.model.generate_async(messages)
            else:
                response = await asyncio.to_thread(self.model.generate, messages)
            
            # Parse tool calls
            response = self.model.parse_tool_calls(response)
            
        except Exception as e:
            step = ActionStep(
                step_number=step_number,
                thought=None,
                tool_calls=None,
                observation=None,
                error=f"Model generation error: {e}"
            )
            if self.verbose:
                print(f"Error: {e}")
            return step, False
        
        # Extract thought from content
        thought = response.content
        if self.verbose and thought:
            print(f"Thought: {thought[:200]}..." if len(thought or "") > 200 else f"Thought: {thought}")
        
        # Check if we got tool calls
        if not response.tool_calls:
            step = ActionStep(
                step_number=step_number,
                thought=thought,
                tool_calls=None,
                observation=None,
                error="No tool call found in response"
            )
            if self.verbose:
                print("Error: No tool call found")
            return step, False
        
        # Execute tools in parallel if multiple
        tool_calls = []
        observations = []
        is_final = False
        
        for tool_call_msg in response.tool_calls:
            tool_name = tool_call_msg.function.name
            tool_args = tool_call_msg.function.arguments
            
            # Ensure arguments is a dict
            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except json.JSONDecodeError:
                    tool_args = {"input": tool_args}
            
            tool_call = ToolCall(
                name=tool_name,
                arguments=tool_args,
                id=tool_call_msg.id or f"call_{uuid.uuid4().hex[:8]}"
            )
            tool_calls.append(tool_call)
        
        if self.verbose:
            for tc in tool_calls:
                print(f"Action: {tc.name}({tc.arguments})")
        
        # Execute tools (parallel for multiple, single for one)
        results = await self._execute_tools_parallel(tool_calls)
        
        for result, tc in zip(results, tool_calls):
            observations.append(str(result))
            if tc.name == "final_answer":
                is_final = True
        
        observation = "\n---\n".join(observations)
        
        if self.verbose:
            obs_preview = observation[:200] + "..." if len(observation) > 200 else observation
            print(f"Observation: {obs_preview}")
        
        step = ActionStep(
            step_number=step_number,
            thought=thought,
            tool_calls=tool_calls,
            observation=observation,
            error=None
        )
        
        return step, is_final
    
    async def _execute_tools_parallel(self, tool_calls: List[ToolCall]) -> List[Any]:
        """
        Execute multiple tools in parallel using asyncio.gather.
        """
        import asyncio
        
        async def execute_one(tc: ToolCall) -> Any:
            tool_name = tc.name
            
            if tool_name not in self.tools:
                available = ", ".join(self.tools.keys())
                return f"Error: Unknown tool '{tool_name}'. Available tools: {available}"
            
            tool = self.tools[tool_name]
            
            try:
                # Use async execution if available
                if hasattr(tool, 'forward_async'):
                    return await tool.forward_async(**tc.arguments)
                else:
                    return await asyncio.to_thread(tool, **tc.arguments)
            except Exception as e:
                return f"Error executing tool '{tool_name}': {e}"
        
        # Execute all tools in parallel
        return await asyncio.gather(*[execute_one(tc) for tc in tool_calls])
    
    async def _force_final_answer_async(self) -> str:
        """Force a final answer asynchronously."""
        import asyncio
        
        messages = self._build_messages()
        messages.append(ChatMessage(
            role="user",
            content="You've reached the maximum number of steps. Please provide your best final answer now using the final_answer tool."
        ))
        
        try:
            if hasattr(self.model, 'generate_async'):
                response = await self.model.generate_async(messages)
            else:
                response = await asyncio.to_thread(self.model.generate, messages)
            
            response = self.model.parse_tool_calls(response)
            
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                if tool_call.function.name == "final_answer":
                    args = tool_call.function.arguments
                    if isinstance(args, dict):
                        return args.get("answer", str(args))
                    return str(args)
            
            return response.content or "Could not determine answer"
        except Exception as e:
            return f"Could not generate final answer: {e}"

