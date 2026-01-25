"""
Evaluation Harness Base Definitions.

Defines the Evaluator protocol and base classes for the offline evaluation system.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class EvalResult:
    """Result of a single evaluation."""

    score: float  # 0.0 to 1.0
    passed: bool
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Evaluator(Protocol):
    """Protocol for an evaluator (judge)."""

    def evaluate(self, output: str, expected: str | None, context: dict[str, Any]) -> EvalResult:
        """
        Evaluate the system output against expectations.

        Args:
            output: The actual output string from the system (e.g., answer JSON or text).
            expected: The expected output string (optional, usually for ground truth).
            context: Additional context like the query, retrieved documents, etc.

        Returns:
            EvalResult with score and reasoning.
        """
        ...
