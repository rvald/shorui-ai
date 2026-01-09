"""
Unit Tests for BasicReActAgent

Run with:
    cd /home/rvald/smolagents/examples/react_agent
    python -m pytest test_agent.py -v
"""

import pytest
from react_agent import BasicReActAgent, FinalAnswerTool
from react_agent.core import MockModel, ChatMessage, Tool
from react_agent.core.models import ChatMessageToolCall, ToolCallFunction
from react_agent.core.tools import tool
from react_agent.default_tools import CalculatorTool


class TestBasicReActAgent:
    """Tests for the BasicReActAgent class."""
    
    def test_agent_initialization(self):
        """Test that agent initializes correctly with tools."""
        model = MockModel([])
        agent = BasicReActAgent(
            tools=[CalculatorTool()],
            model=model,
        )
        
        assert "calculator" in agent.tools
        assert "final_answer" in agent.tools  # Always added
        assert agent.max_steps == 10  # Default
        
    def test_agent_runs_to_completion(self):
        """Test that agent completes a task with final_answer."""
        responses = [
            ChatMessage(
                role="assistant",
                content="Let me calculate this.",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_1",
                        function=ToolCallFunction(
                            name="calculator",
                            arguments={"expression": "2 + 2"}
                        )
                    )
                ]
            ),
            ChatMessage(
                role="assistant",
                content="I have the answer.",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_2",
                        function=ToolCallFunction(
                            name="final_answer",
                            arguments={"answer": "The answer is 4"}
                        )
                    )
                ]
            ),
        ]
        
        model = MockModel(responses)
        agent = BasicReActAgent(
            tools=[CalculatorTool()],
            model=model,
        )
        
        result = agent.run("What is 2 + 2?")
        
        assert result.success is True
        assert result.output == "The answer is 4"
        assert len(result.steps) == 2
        
    def test_agent_respects_max_steps(self):
        """Test that agent stops at max_steps."""
        # Model that never calls final_answer
        responses = [
            ChatMessage(
                role="assistant",
                content="Let me calculate.",
                tool_calls=[
                    ChatMessageToolCall(
                        id=f"call_{i}",
                        function=ToolCallFunction(
                            name="calculator",
                            arguments={"expression": "1 + 1"}
                        )
                    )
                ]
            )
            for i in range(10)
        ]
        
        model = MockModel(responses)
        agent = BasicReActAgent(
            tools=[CalculatorTool()],
            model=model,
            max_steps=3,
        )
        
        result = agent.run("Keep calculating forever")
        
        assert result.success is False
        assert len(result.steps) == 3
        
    def test_tool_execution(self):
        """Test that tools are executed correctly."""
        responses = [
            ChatMessage(
                role="assistant",
                content="Calculating...",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_1",
                        function=ToolCallFunction(
                            name="calculator",
                            arguments={"expression": "10 * 5"}
                        )
                    )
                ]
            ),
            ChatMessage(
                role="assistant",
                content="Done.",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_2",
                        function=ToolCallFunction(
                            name="final_answer",
                            arguments={"answer": "50"}
                        )
                    )
                ]
            ),
        ]
        
        model = MockModel(responses)
        agent = BasicReActAgent(
            tools=[CalculatorTool()],
            model=model,
        )
        
        result = agent.run("What is 10 * 5?")
        
        # Check that calculator was executed and observation recorded
        assert result.steps[0].tool_calls[0].name == "calculator"
        assert "50" in result.steps[0].observation
        
    def test_unknown_tool_handling(self):
        """Test that unknown tools are handled gracefully."""
        responses = [
            ChatMessage(
                role="assistant",
                content="Let me use a nonexistent tool.",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_1",
                        function=ToolCallFunction(
                            name="nonexistent_tool",
                            arguments={}
                        )
                    )
                ]
            ),
            ChatMessage(
                role="assistant",
                content="I'll try final_answer instead.",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_2",
                        function=ToolCallFunction(
                            name="final_answer",
                            arguments={"answer": "Recovered"}
                        )
                    )
                ]
            ),
        ]
        
        model = MockModel(responses)
        agent = BasicReActAgent(
            tools=[],
            model=model,
        )
        
        result = agent.run("Test unknown tool")
        
        assert "Error" in result.steps[0].observation
        assert "Unknown tool" in result.steps[0].observation
        
    def test_tool_decorator(self):
        """Test that @tool decorator creates valid tools."""
        @tool
        def greet(name: str) -> str:
            """Greet a person by name."""
            return f"Hello, {name}!"
        
        responses = [
            ChatMessage(
                role="assistant",
                content="Greeting...",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_1",
                        function=ToolCallFunction(
                            name="greet",
                            arguments={"name": "World"}
                        )
                    )
                ]
            ),
            ChatMessage(
                role="assistant",
                content="Done.",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_2",
                        function=ToolCallFunction(
                            name="final_answer",
                            arguments={"answer": "Hello, World!"}
                        )
                    )
                ]
            ),
        ]
        
        model = MockModel(responses)
        agent = BasicReActAgent(
            tools=[greet],
            model=model,
        )
        
        result = agent.run("Greet the world")
        
        assert result.steps[0].observation == "Hello, World!"
        

class TestAgentMemory:
    """Tests for the memory system."""
    
    def test_memory_reset(self):
        """Test that memory resets between runs."""
        model = MockModel([
            ChatMessage(
                role="assistant",
                content="Final.",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_1",
                        function=ToolCallFunction(
                            name="final_answer",
                            arguments={"answer": "Done"}
                        )
                    )
                ]
            ),
        ])
        
        agent = BasicReActAgent(tools=[], model=model)
        
        # First run
        agent.run("Task 1")
        assert agent.memory.task == "Task 1"
        assert len(agent.memory.steps) == 1
        
        # Reset model for second run
        model.call_count = 0
        
        # Second run should reset memory
        agent.run("Task 2")
        assert agent.memory.task == "Task 2"
        assert len(agent.memory.steps) == 1


class TestToolSchema:
    """Tests for tool schema generation."""
    
    def test_tool_to_schema(self):
        """Test JSON schema generation from tools."""
        calc = CalculatorTool()
        schema = calc.to_schema()
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "calculator"
        assert "expression" in schema["function"]["parameters"]["properties"]
        
    def test_tool_prompt_description(self):
        """Test prompt description generation."""
        calc = CalculatorTool()
        desc = calc.to_prompt_description()
        
        assert "calculator" in desc
        assert "expression" in desc
        assert "mathematical" in desc.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
