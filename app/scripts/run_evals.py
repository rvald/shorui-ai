"""
Run offline evaluations against a dataset.

Usage:
    python -m app.scripts.run_evals --dataset evals/data/sample.jsonl
"""

import argparse
import json
import asyncio
from typing import Type

from shorui_core.evals.base import Evaluator
from shorui_core.evals.evaluators import RefusalEvaluator, CitationEvaluator, PHISafetyEvaluator

# Map string names to classes
EVALUATORS: dict[str, Type[Evaluator]] = {
    "refusal": RefusalEvaluator,
    "citation": CitationEvaluator,
    "phi_safety": PHISafetyEvaluator,
}

async def run_evals(dataset_path: str):
    print(f"Loading dataset from {dataset_path}...")
    
    results = []
    
    # Mock runner loop - in real implementation, this would call the API
    # Here we simulate the component output based on "mock_output" in dataset 
    # to demonstrate the harness logic without needing live services up for this script.
    
    try:
        with open(dataset_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                case = json.loads(line)
                
                eval_type = case.get("eval_type")
                input_data = case.get("input")
                # In a real integration test, we would call:
                # response = await client.post("/rag/query", json={"query": input_data})
                # output = response.text
                output = case.get("mock_output", "") # Simulating system output for now
                
                eval_cls = EVALUATORS.get(eval_type)
                if not eval_cls:
                    print(f"Unknown evaluator: {eval_type}")
                    continue
                
                evaluator = eval_cls()
                result = evaluator.evaluate(output, case.get("expected"), context={"input": input_data})
                
                results.append({
                    "case": input_data,
                    "evaluator": eval_type,
                    "passed": result.passed,
                    "score": result.score,
                    "reason": result.reason
                })
                
                status = "✅ PASS" if result.passed else "❌ FAIL"
                print(f"{status} | Type: {eval_type:<10} | Score: {result.score} | Reason: {result.reason}")

    except FileNotFoundError:
        print(f"Dataset file not found: {dataset_path}")
        return

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print("-" * 50)
    print(f"Run Complete. Passed: {passed}/{total} ({passed/total*100:.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to JSONL dataset")
    args = parser.parse_args()
    
    asyncio.run(run_evals(args.dataset))
