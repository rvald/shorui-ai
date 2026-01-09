#!/usr/bin/env python3
"""
Example Usage of BasicReActAgent

This script demonstrates how to use the standalone ReAct agent
with both a mock model (for testing) and optionally a real API.

Run with:
    cd examples/react_agent
    python example.py             # Uses mock model
    python example.py --openai    # Uses OpenAI API (requires OPENAI_API_KEY)
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for local imports when running as script
sys.path.insert(0, str(Path(__file__).parent))

from agent import BasicReActAgent
from core.models import MockModel, ChatMessage, OpenAIModel, ChatMessageToolCall, ToolCallFunction
from core.tools import tool
from default_tools import CalculatorTool


# Example: Create a custom tool using the @tool decorator
@tool
def get_weather(city: str) -> str:
    """
    Get the current weather for a city.
    
    Args:
        city: The city name to get weather for
    """
    # Mock implementation
    weather_data = {
        "new york": "Sunny, 72°F",
        "london": "Cloudy, 55°F",
        "tokyo": "Rainy, 65°F",
        "paris": "Partly cloudy, 68°F",
    }
    return weather_data.get(city.lower(), f"Weather data not available for {city}")


def create_mock_model():
    """Create a mock model that simulates a ReAct agent solving a math problem."""
    responses = [
        # Step 1: Use calculator
        ChatMessage(
            role="assistant",
            content="I need to calculate 15 * 7. Let me use the calculator tool.",
            tool_calls=[
                ChatMessageToolCall(
                    id="call_1",
                    function=ToolCallFunction(
                        name="calculator",
                        arguments={"expression": "15 * 7"}
                    )
                )
            ]
        ),
        # Step 2: Provide final answer
        ChatMessage(
            role="assistant", 
            content="I got the result. Let me provide the final answer.",
            tool_calls=[
                ChatMessageToolCall(
                    id="call_2",
                    function=ToolCallFunction(
                        name="final_answer",
                        arguments={"answer": "15 × 7 = 105"}
                    )
                )
            ]
        ),
    ]
    return MockModel(responses)


def run_mock_example():
    """Run the agent with a mock model."""
    print("\n" + "="*60)
    print("Running with Mock Model")
    print("="*60)
    
    model = create_mock_model()
    agent = BasicReActAgent(
        tools=[CalculatorTool()],
        model=model,
        max_steps=5,
        verbose=True,
    )
    
    result = agent.run("What is 15 multiplied by 7?")
    
    print(f"\n{'='*60}")
    print(f"Final Answer: {result.output}")
    print(f"Success: {result.success}")
    print(f"Steps taken: {len(result.steps)}")
    print("="*60)
    
    return result


def run_openai_example():
    """Run the agent with OpenAI API."""
    print("\n" + "="*60)
    print("Running with OpenAI Model")
    print("="*60)
    
    try:
        model = OpenAIModel(model_id="gpt-4o-mini")
    except ValueError as e:
        print(f"Error: {e}")
        print("Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        return None
    except ImportError:
        print("Install openai package: pip install openai")
        return None
    
    agent = BasicReActAgent(
        tools=[CalculatorTool(), get_weather],
        model=model,
        max_steps=5,
        verbose=True,
    )
    
    # Try a more complex task
    result = agent.run("What is 25 * 4, and what's the weather in Paris?")
    
    print(f"\n{'='*60}")
    print(f"Final Answer: {result.output}")
    print(f"Success: {result.success}")
    print(f"Steps taken: {len(result.steps)}")
    print("="*60)
    
    return result


def main():
    parser = argparse.ArgumentParser(description="BasicReActAgent Example")
    parser.add_argument("--openai", action="store_true", help="Use OpenAI API instead of mock")
    args = parser.parse_args()
    
    if args.openai:
        run_openai_example()
    else:
        run_mock_example()


if __name__ == "__main__":
    main()
