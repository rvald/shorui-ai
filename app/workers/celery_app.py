"""
Celery application configuration.

This module configures the Celery app with Redis as broker and backend.
"""

import os

from celery import Celery
from loguru import logger

# Get broker/backend URLs from environment
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "shorui_ai",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks",
        "app.workers.transcript_tasks",
    ],
)

# Configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task tracking
    task_track_started=True,
    task_acks_late=True,  # Acknowledge after task completes (for reliability)
    # Results
    result_expires=3600,  # Results expire after 1 hour
    # Worker settings
    worker_prefetch_multiplier=1,  # Fetch one task at a time (for large tasks)
    worker_concurrency=2,  # Number of concurrent workers
)

logger.info(f"Celery app configured with broker: {CELERY_BROKER_URL}")
