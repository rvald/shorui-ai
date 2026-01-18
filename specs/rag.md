# RAG Module Specification

This document describes the RAG (Retrieval-Augmented Generation) module architecture and implementation.

## Overview

The RAG module handles the retrieval of relevant context and generation of answers for the shorui-ai platform. It supports a multi-stage pipeline including query expansion, vector search, graph-based reasoning, and reranking.

---

## Module Structure

```
app/rag/
├── protocols.py            # Interface definitions
├── factory.py             # Component wiring & creation
├── routes.py              # API endpoints
└── services/              # Business logic implementations
    ├── retrieval.py        # PipelineRetriever (Orchestrator)
    ├── inference.py        # GenerativeModel implementations
    ├── query_processor.py  # QueryAnalyzer implementation
    ├── reranker.py         # Reranker implementation
    └── graph_retriever.py  # GraphRetriever implementation
```

---

## API Endpoints

### Query & Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/rag/health` | Health check |
| `POST` | `/rag/query` | Full RAG pipeline (Retrieve + Generate) |
| `GET` | `/rag/search` | Search-only (Retrieve without generation) |

> Source: [routes.py](../app/rag/routes.py)

---

## Schemas

All request/response models use Pydantic for validation:

- `QueryRequest` - RAG query parameters (query, project_id, k, backend)
- `QueryResponse` - Generated answer with source citations
- `SourceDocument` - Metadata for a cited source
- `SearchResponse` - Raw search results list
- `SearchResult` - Individual search hit details

> Source: [routes.py](../app/rag/routes.py)

---

## Retrieval Pipeline

Queries are processed through a composable pipeline:

```
Query → Analyzer → Expander → VectorSearch (Parallel) → GraphReasoning → Reranker → Generator
```

### Pipeline Stages

| Stage | Protocol | Implementation | Purpose |
|-------|----------|----------------|---------|
| Analysis | `QueryAnalyzer` | `LLMQueryAnalyzer` | Extract keywords & intent |
| Expansion | `QueryAnalyzer` | `LLMQueryAnalyzer` | Generate query variations |
| Retrieval | `Retriever` | `PipelineRetriever` | Orchestrate search & context building |
| Reasoning | `GraphRetriever` | `GraphRetrieverService` | Expand context via Neo4j |
| Reranking | `Reranker` | `CrossEncoderReranker` | Re-score results using CrossEncoder |
| Generation| `GenerativeModel`| `OpenAIGenerator` | Generate final answer |

### Usage

```python
from app.rag.factory import get_retriever, get_generator

# 1. Retrieve Context
retriever = get_retriever()
result = await retriever.retrieve(
    query="What are the compliance requirements?",
    project_id="proj-123"
)

# 2. Generate Answer
generator = get_generator(backend="openai")
answer = await generator.generate(
    query="What are the compliance requirements?",
    context=format_context(result["documents"])
)
```

> Source: [factory.py](../app/rag/factory.py), [retrieval.py](../app/rag/services/retrieval.py)

---

## Protocols & Backends

Components are abstracted via Protocols defined in `protocols.py`:

| Protocol | Implementations | Description |
|----------|-----------------|-------------|
| `Retriever` | `PipelineRetriever` | Main entry point for context retrieval |
| `GenerativeModel` | `OpenAIGenerator`, `RunPodGenerator` | LLM backend wrapper |
| `QueryAnalyzer` | `LLMQueryAnalyzer` | text-to-intent logic |
| `Reranker` | `CrossEncoderReranker` | Similarity scorer |
| `GraphRetriever` | `GraphRetrieverService` | specialized Neo4j logic |

> Source: [protocols.py](../app/rag/protocols.py)

---

## Services

### PipelineRetriever

Orchestrates the parallel execution of search queries, deduplication, graph reasoning, and reranking. Lazily initializes connections to Qdrant.

> Source: [retrieval.py](../app/rag/services/retrieval.py)

### LLMQueryAnalyzer

Uses OpenAI to:
1.  **Extract Keywords**: JSON-mode extraction of keywords and intent (e.g., "gap_analysis").
2.  **Expand Queries**: Generates `N` variations of the user query for higher recall.

> Source: [query_processor.py](../app/rag/services/query_processor.py)

### GraphRetrieverService

Connects to Neo4j to:
- **Expand Context**: Follows `SEE_DETAIL` relationships to pull in referenced details.
- **Detect Gaps**: Finds `Gap` nodes linked to retrieved content to support "Gap Analysis" queries.

> Source: [graph_retriever.py](../app/rag/services/graph_retriever.py)

### CrossEncoderReranker

Uses `sentence-transformers` CrossEncoder to re-score the top `K` vector results against the original query.

> Source: [reranker.py](../app/rag/services/reranker.py)

---

## Configuration

Key settings from `shorui_core.config`:

| Setting | Description |
|---------|-------------|
| `OPENAI_MODEL_ID` | Model for query analysis & generation (default) |
| `RERANKING_CROSS_ENCODER_MODEL_ID` | Model for reranking |
| `RUNPOD_API_URL` | Endpoint for custom LLM backend |
| `QDRANT_DATABASE_HOST` | Qdrant server host |
| `NEO4J_URI` | Neo4j connection URI |

> Source: [config.py](../shorui_core/config.py)
