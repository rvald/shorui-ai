"""
PostgreSQL connection helper for shorui-ai.

This module provides a simple connection function for PostgreSQL access.
Uses psycopg for the connection.
"""

import psycopg
from loguru import logger

from shorui_core.config import settings


def get_db_connection():
    """
    Get a PostgreSQL database connection.

    Returns a context manager that can be used with 'with' statement.
    The connection is automatically closed when the context exits.

    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs")

    Returns:
        psycopg.Connection: A PostgreSQL connection.
    """
    try:
        conn = psycopg.connect(settings.POSTGRES_DSN)
        logger.debug("Connected to PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise
