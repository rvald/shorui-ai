"""
GraphBaseModel: Base class for documents stored in Neo4j graph database.

This module provides the abstract base class for all graph-indexed nodes
in the shorui-ai system. It handles:
- UUID-based identity with project isolation
- Serialization for Neo4j MERGE operations
- Database resolution for multi-tenancy
"""

import uuid
from abc import ABC
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound="GraphBaseModel")


class GraphBaseModel(BaseModel, Generic[T], ABC):
    """
    Abstract base class for Neo4j graph nodes.

    Subclasses must define:
    - A Meta class with `database_name` (Neo4j database name)

    Example:
        class TextBlock(GraphBaseModel):
            text: str
            cleaned_text: str

            class Meta:
                database_name = "neo4j"
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str | None = Field(
        None, description="Logical project identifier for multi-tenancy."
    )
    database_override: str | None = Field(None, exclude=True)

    _neo4j_client: ClassVar[Any] = None

    class Meta:
        database_name: str = "neo4j"

    @classmethod
    def _database_name(cls) -> str:
        """Get the database name from the Meta class."""
        database = getattr(cls.Meta, "database_name", None)
        if not database:
            raise ValueError("GraphBaseModel subclass must define Meta.database_name")
        return database

    @classmethod
    def _get_neo4j_client(cls):
        """
        Get the Neo4j driver instance.

        This method should be overridden or the client should be set
        before calling save(). For testing, it returns the class-level
        _neo4j_client attribute.
        """
        if cls._neo4j_client is None:
            # Lazy import to avoid circular dependencies
            try:
                from shorui_core.infrastructure.neo4j import get_neo4j_client

                cls._neo4j_client = get_neo4j_client()
            except ImportError:
                raise RuntimeError(
                    "Neo4j client not configured. Either set _neo4j_client "
                    "or ensure shorui_core.infrastructure.neo4j is available."
                )
        return cls._neo4j_client

    def _resolve_database(self) -> str:
        """Resolve which database to use, preferring override if set."""
        if self.database_override:
            return self.database_override
        return self._database_name()

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """
        Serialize the model to a dictionary.

        Automatically excludes database_override field.
        """
        # Ensure exclude is set up
        exclude = kwargs.pop("exclude", None) or set()
        if isinstance(exclude, set):
            exclude.add("database_override")
        elif isinstance(exclude, dict):
            exclude["database_override"] = True

        return super().model_dump(exclude=exclude, **kwargs)

    async def save(self) -> None:
        """
        Save the model as a node in Neo4j using MERGE.

        Uses the node's ID and project_id as the merge key to ensure
        idempotent upserts.
        """
        client = self._get_neo4j_client()
        database = self._resolve_database()
        label = self.__class__.__name__
        properties = self.model_dump()

        # Convert UUID to string for Neo4j if needed
        if "id" in properties:
            properties["id"] = str(properties["id"])

        query = f"MERGE (n:{label} {{id: $id, project_id: $project_id}}) SET n = $props"

        def _execute(tx):
            tx.run(
                query,
                id=properties["id"],
                project_id=properties.get("project_id"),
                props=properties,
            )

        with client.session(database=database) as session:
            session.execute_write(_execute)

    @classmethod
    async def merge_node(
        cls,
        label: str,
        match_props: dict[str, Any],
        properties: dict[str, Any],
        database: str = None,
    ) -> None:
        """
        Merge a node with given identifying properties and set all props.
        """
        client = cls._get_neo4j_client()
        database = database or cls._database_name()

        # Build match properties string
        match_parts = [f"{key}: ${key}_val" for key in match_props.keys()]
        match_str = ", ".join(match_parts)
        query = f"MERGE (n:{label} {{{match_str}}}) SET n += $props"

        def _execute(tx):
            params = {f"{k}_val": v for k, v in match_props.items()}
            params["props"] = properties
            tx.run(query, **params)

        with client.session(database=database) as session:
            session.execute_write(_execute)

    @classmethod
    async def create_relationship(
        cls,
        from_label: str,
        from_id_field: str,
        from_id_value: Any,
        to_label: str,
        to_id_field: str,
        to_id_value: Any,
        rel_type: str,
        properties: dict[str, Any] = None,
        database: str = None,
    ) -> None:
        """
        Create a relationship between two nodes.
        """
        client = cls._get_neo4j_client()
        database = database or cls._database_name()
        props_str = " SET r += $props" if properties else ""
        project_id = (properties or {}).get("project_id")

        query = f"""
        MATCH (a:{from_label} {{{from_id_field}: $from_id, project_id: $project_id}})
        MATCH (b:{to_label} {{{to_id_field}: $to_id, project_id: $project_id}})
        MERGE (a)-[r:{rel_type}]->(b)
        {props_str}
        """

        def _execute(tx):
            tx.run(
                query,
                from_id=from_id_value,
                to_id=to_id_value,
                project_id=project_id,
                props=properties or {},
            )

        with client.session(database=database) as session:
            session.execute_write(_execute)
