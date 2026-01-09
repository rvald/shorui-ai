"""
Neo4j client connector for shorui-ai.

This module provides a singleton Neo4j driver that can be shared
across all services. It uses the unified settings for connection parameters.
"""

from loguru import logger
from neo4j import Driver, GraphDatabase

from shorui_core.config import settings


class Neo4jClientConnector:
    """
    Singleton connector for Neo4j database.

    Usage:
        driver = Neo4jClientConnector.get_instance()
        with driver.session() as session:
            session.run("MATCH (n) RETURN n LIMIT 1")
    """

    _instance: Driver | None = None

    @classmethod
    def get_instance(cls) -> Driver:
        """
        Get or create the Neo4j driver instance.

        Returns:
            Driver: The Neo4j driver instance.

        Raises:
            Exception: If connection to Neo4j fails.
        """
        if cls._instance is None:
            try:
                cls._instance = GraphDatabase.driver(
                    uri=settings.NEO4J_URI,
                    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                )
                logger.info(f"Connected to Neo4j database at {settings.NEO4J_URI}")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j at '{settings.NEO4J_URI}': {e}")
                raise
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton instance.

        Useful for testing or reconnection scenarios.
        """
        if cls._instance is not None:
            try:
                cls._instance.close()
            except Exception:
                pass
            cls._instance = None


def get_neo4j_client() -> Driver:
    """
    Convenience function to get the Neo4j driver.

    Returns:
        Driver: The Neo4j driver instance.
    """
    return Neo4jClientConnector.get_instance()
