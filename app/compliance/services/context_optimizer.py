"""
Context Optimizer for HIPAA Compliance LLM Analysis.

Manages token budget by:
1. Line-based context extraction (not full transcript)
2. PHI deduplication (group similar values)
3. Token-aware batching (respect input limits)
"""

from dataclasses import dataclass

import tiktoken
from loguru import logger

from shorui_core.domain.hipaa_schemas import PHISpan

# Initialize tokenizer (cl100k_base is used by GPT-4, close approximation for most LLMs)
_encoder: tiktoken.Encoding | None = None


def get_encoder() -> tiktoken.Encoding:
    """Get or create the tiktoken encoder."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("o200k_harmony")
    return _encoder


def count_tokens(text: str) -> int:
    """Count exact tokens in text."""
    return len(get_encoder().encode(text))


def get_phi_value(text: str, span: PHISpan) -> str:
    """Extract the actual PHI value from text using span offsets."""
    return text[span.start_char : span.end_char]


@dataclass
class PHIContext:
    """PHI span with extracted line context."""

    span: PHISpan
    original_index: int
    line_context: str
    token_count: int


def extract_line_context(text: str, span: PHISpan) -> str:
    """
    Extract the full line containing the PHI.
    Falls back to sentence if line is too short.
    """
    phi_value = get_phi_value(text, span)
    lines = text.split("\n")

    current_pos = 0
    for line in lines:
        line_end = current_pos + len(line)
        if current_pos <= span.start_char < line_end:
            if len(line) > 200:
                phi_pos_in_line = span.start_char - current_pos
                start = max(0, phi_pos_in_line - 80)
                end = min(len(line), phi_pos_in_line + len(phi_value) + 80)
                line = "..." + line[start:end] + "..."
            return line.strip()
        current_pos = line_end + 1

    return phi_value


def deduplicate_phi(phi_spans: list[PHISpan], text: str) -> dict[str, list[int]]:
    """
    Group PHI spans by (category, normalized_value).
    Returns dict: key -> list of original indices.

    Example:
        "Maria Gonzalez" appears at indices 2, 15, 28
        -> {"NAME:maria gonzalez": [2, 15, 28]}
    """
    groups: dict[str, list[int]] = {}

    for i, span in enumerate(phi_spans):
        phi_value = get_phi_value(text, span)
        normalized = phi_value.lower().strip()
        key = f"{span.category.value}:{normalized}"

        if key not in groups:
            groups[key] = []
        groups[key].append(i)

    return groups


def build_optimized_batches(
    phi_spans: list[PHISpan],
    text: str,
    max_input_tokens: int = 1200,
    base_prompt_tokens: int = 200,
) -> list[list[PHIContext]]:
    """
    Build token-aware batches of PHI contexts.

    Args:
        phi_spans: All PHI spans needing LLM analysis
        text: Full transcript text
        max_input_tokens: Max tokens for input (excluding output budget)
        base_prompt_tokens: Tokens used by system prompt + template

    Returns:
        List of batches, each batch is a list of PHIContext
    """
    # Deduplicate first
    groups = deduplicate_phi(phi_spans, text)

    # Build PHIContext for each unique PHI (representative)
    contexts: list[PHIContext] = []

    for _key, indices in groups.items():
        rep_index = indices[0]
        span = phi_spans[rep_index]
        phi_value = get_phi_value(text, span)

        line_context = extract_line_context(text, span)

        if len(indices) > 1:
            description = f"{span.category.value}: '{phi_value}' (appears {len(indices)}x, indices: {indices})"
        else:
            description = f"{span.category.value}: '{phi_value}' in: \"{line_context}\""

        context = PHIContext(
            span=span,
            original_index=rep_index,
            line_context=description,
            token_count=count_tokens(description),
        )
        contexts.append(context)

    logger.info(f"Context optimization: {len(phi_spans)} spans -> {len(contexts)} unique groups")

    # Build batches respecting token limit
    available_tokens = max_input_tokens - base_prompt_tokens
    batches: list[list[PHIContext]] = []
    current_batch: list[PHIContext] = []
    current_tokens = 0

    for ctx in contexts:
        if current_tokens + ctx.token_count > available_tokens and current_batch:
            batches.append(current_batch)
            current_batch = [ctx]
            current_tokens = ctx.token_count
        else:
            current_batch.append(ctx)
            current_tokens += ctx.token_count

    if current_batch:
        batches.append(current_batch)

    # Log batch stats
    total_tokens = sum(ctx.token_count for batch in batches for ctx in batch)
    logger.info(f"Built {len(batches)} batches, total PHI tokens: {total_tokens}")
    for i, batch in enumerate(batches):
        batch_tokens = sum(ctx.token_count for ctx in batch)
        logger.debug(f"  Batch {i + 1}: {len(batch)} PHI groups, {batch_tokens} tokens")

    return batches


def build_compact_prompt(
    contexts: list[PHIContext],
    system_prompt: str,
) -> tuple[str, int]:
    """
    Build a token-efficient prompt for a batch of PHI contexts.

    Returns:
        (prompt_text, total_tokens)
    """
    phi_lines = [ctx.line_context for ctx in contexts]

    prompt = f"""Analyze each PHI for HIPAA violation.

PHI List:
{chr(10).join(f"{i}. {line}" for i, line in enumerate(phi_lines))}

For each: is_violation (bool), severity (LOW/MEDIUM/HIGH/CRITICAL), reason, citation.
Output JSON only: {{"phi_analyses": [{{"index": 0, "violation": true, "severity": "HIGH", "reason": "...", "citation": "45 CFR..."}}]}}"""

    total_tokens = count_tokens(system_prompt) + count_tokens(prompt)

    return prompt, total_tokens
