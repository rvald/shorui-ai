# Dockerfile for Shorui-AI Unified Application
FROM python:3.13-slim-bookworm

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:0.8.10 /uv /uvx /bin/

# Install system dependencies (curl for healthcheck, tesseract for OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*


# Set working directory
WORKDIR /app

# Copy dependency files first (for Docker layer caching)
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv
# This uses pyproject.toml and uv.lock if present
RUN uv sync --frozen --no-dev || uv sync

# Download spaCy model for Presidio (PHI detection)
RUN uv run python -m spacy download en_core_web_sm

# Copy application code
COPY shorui_core/ ./shorui_core/
COPY app/ ./app/
COPY agents/ ./agents/

# Set Python path and unbuffer output
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:8082/health || exit 1

# Run with multiple workers (Redis session storage enables cross-worker sessions)
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082", "--workers", "1"]
