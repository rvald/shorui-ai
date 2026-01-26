"""
Rate limiter infrastructure using slowapi.
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

from shorui_core.config import settings

# Initialize the global limiter
# Use Redis if configured, otherwise fallback to memory (which won't work well with multiple workers)
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=getattr(settings, "CELERY_BROKER_URL", "memory://"),
)
