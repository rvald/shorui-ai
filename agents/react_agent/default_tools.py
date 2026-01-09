"""
Default Tools

Built-in tools that come with the ReAct agent.
"""
from __future__ import annotations

from typing import Any

# Support both package import and direct script execution
try:
    from .core.tools import Tool
except ImportError:
    from core.tools import Tool


class FinalAnswerTool(Tool):
    """
    Special tool for providing the final answer.
    Every agent automatically includes this tool.
    
    When the agent calls this tool, the run loop terminates
    and returns the provided answer.
    """
    
    name = "final_answer"
    description = "Provides the final answer to the task. Use this when you have completed the task."
    inputs = {
        "answer": {
            "type": "any",
            "description": "The final answer to provide"
        }
    }
    output_type = "any"
    
    def forward(self, answer: Any) -> Any:
        return answer


class CalculatorTool(Tool):
    """
    A simple calculator tool for basic arithmetic.
    Useful for math operations.
    """
    
    name = "calculator"
    description = "Evaluates a mathematical expression and returns the result."
    inputs = {
        "expression": {
            "type": "string",
            "description": "The mathematical expression to evaluate (e.g., '2 + 2', '15 * 7')"
        }
    }
    output_type = "string"
    
    def forward(self, expression: str) -> str:
        try:
            # Safely evaluate math expressions
            # Only allow basic math operations
            allowed_chars = set('0123456789+-*/().% ')
            if not all(c in allowed_chars for c in expression):
                return f"Error: Expression contains invalid characters. Only numbers and basic operators allowed."
            
            result = eval(expression)
            return str(result)
        except Exception as e:
            return f"Error evaluating expression: {e}"
