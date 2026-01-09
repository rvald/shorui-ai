#!/usr/bin/env python3
"""
Shorui AI Agent Example

Demonstrates how to use the BasicReActAgent with Shorui AI platform tools
for HIPAA compliance workflows.

Run with:
    cd agents/react_agent
    python shorui_example.py             # Uses mock model
    python shorui_example.py --openai    # Uses OpenAI API (requires OPENAI_API_KEY)

Prerequisites:
    - Docker Compose services running (for real API calls)
    - OPENAI_API_KEY environment variable set (for --openai mode)
"""

import argparse
import sys
from pathlib import Path

# Add parent directory for package imports
sys.path.insert(0, str(Path(__file__).parent))

from agent import ReActAgent
from core.models import MockModel, ChatMessage, OpenAIModel, ChatMessageToolCall, ToolCallFunction
from tools import (
    RAGSearchTool,
    UploadDocumentTool,
    CheckIngestionStatusTool,
    AnalyzeClinicalTranscriptTool,
    GetComplianceReportTool,
    QueryAuditLogTool,
    CheckSystemHealthTool,
)


def run_mock_rag_example():
    """Run a mock RAG search example."""
    print("\n" + "="*60)
    print("Shorui AI Agent - RAG Search Example (Mock)")
    print("="*60)
    
    model = MockModel(create_mock_rag_responses())
    agent = ReActAgent(
        tools=[RAGSearchTool()],  # Just the RAG tool for this example
        model=model,
        max_steps=5,
        verbose=True,
    )
    
    result = agent.run("What are the 18 HIPAA identifiers?")
    
    print(f"\n{'='*60}")
    print(f"Final Answer: {result.output}")
    print(f"Success: {result.success}")
    print(f"Steps taken: {len(result.steps)}")
    print("="*60)
    
    return result


def run_rag():
    """Run with OpenAI API and real Shorui tools."""
    print("\n" + "="*60)
    print("Shorui AI Agent - Live Mode (OpenAI)")
    print("="*60)
    
    try:
        model = OpenAIModel(model_id="gpt-4o-mini")
    except ValueError as e:
        print(f"Error: {e}")
        print("Set OPENAI_API_KEY environment variable.")
        return None
    except ImportError:
        print("Install openai package: pip install openai")
        return None
    
    agent = ReActAgent(
        tools=[RAGSearchTool()],
        model=model,
        max_steps=5,
        verbose=True,
    )
    
    result = agent.run("What are the 18 HIPAA identifiers?")
    
    print(f"\n{'='*60}")
    print(f"Final Answer: {result.output}")
    print(f"Success: {result.success}")
    print(f"Steps taken: {len(result.steps)}")
    print("="*60)
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Shorui AI Agent Example")
    parser.add_argument("--rag", action="store_true", help="Run RAG search example")
    args = parser.parse_args()
    
    if args.rag:
        run_rag()
    else:
        run_mock_rag_example()


if __name__ == "__main__":
    main()
