"""
VectorBaseDocument: Base class for documents stored in vector databases.

This module provides the abstract base class for all vector-indexed documents
in the shorui-ai system. It handles:
- UUID-based identity and equality
- Serialization to Qdrant PointStruct
- Deserialization from Qdrant ScoredPoint
"""

import uuid
from abc import ABC
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field
from qdrant_client.models import PointStruct, ScoredPoint

T = TypeVar("T", bound="VectorBaseDocument")


class VectorBaseDocument(BaseModel, Generic[T], ABC):
    """
    Abstract base class for vector-indexed documents.

    Subclasses must define:
    - A Config class with `name` (collection name) and optionally `use_vector_index`
    - An `embedding` field for the vector data

    Example:
        class MyDocument(VectorBaseDocument):
            content: str
            embedding: list[float] | None = None

            class Config:
                name = "my_collection"
                use_vector_index = True
    """

    id: UUID = Field(default_factory=uuid.uuid4)

    def __eq__(self, value: object) -> bool:
        """Two documents are equal if they have the same ID."""
        if not isinstance(value, self.__class__):
            return False
        return self.id == value.id

    def __hash__(self) -> int:
        """Hash based on ID for use in sets and dicts."""
        return hash(self.id)

    def to_point(self: T, **kwargs) -> PointStruct:
        """
        Serialize this document to a Qdrant PointStruct.

        The embedding is extracted as the vector, and remaining fields
        become the payload. UUIDs are converted to strings.
        """
        exclude_unset = kwargs.pop("exclude_unset", False)
        by_alias = kwargs.pop("by_alias", True)

        payload = self.model_dump(exclude_unset=exclude_unset, by_alias=by_alias, **kwargs)

        _id = str(payload.pop("id"))
        vector = payload.pop("embedding", [])

        # Convert any remaining UUIDs in payload to strings
        payload = self._uuid_to_str(payload)

        return PointStruct(id=_id, vector=vector, payload=payload)

    def _uuid_to_str(self, item: Any) -> Any:
        """Recursively convert UUIDs to strings in nested structures."""
        if isinstance(item, UUID):
            return str(item)
        elif isinstance(item, dict):
            return {k: self._uuid_to_str(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [self._uuid_to_str(v) for v in item]
        return item

    @classmethod
    def from_record(cls: type[T], point: ScoredPoint) -> T:
        """
        Deserialize a Qdrant ScoredPoint into a document instance.

        Handles multiple content field names for backward compatibility:
        - "content" (preferred)
        - "cleaned_text" (fallback)
        - "text" (fallback)
        """
        # Parse the ID
        try:
            _id = UUID(point.id)
        except (ValueError, AttributeError):
            _id = uuid.uuid4()

        payload = point.payload or {}

        # Handle content mapping with fallbacks
        content = payload.get("content") or payload.get("cleaned_text") or payload.get("text") or ""

        # Build attributes for the model
        attributes = {
            "id": _id,
            "content": content,
        }

        # Include embedding if present
        if point.vector is not None:
            attributes["embedding"] = point.vector

        # Filter to only allowed fields
        allowed_fields = cls.model_fields.keys()
        filtered_attributes = {k: v for k, v in attributes.items() if k in allowed_fields}

        return cls(**filtered_attributes)

    @classmethod
    def get_collection_name(cls: type[T]) -> str:
        """Get the collection name from the Config class."""
        if not hasattr(cls, "Config") or not hasattr(cls.Config, "name"):
            raise ValueError("VectorBaseDocument subclass must define Config.name")
        return cls.Config.name

    @classmethod
    def get_use_vector_index(cls: type[T]) -> bool:
        """Check if this document type uses vector indexing."""
        if not hasattr(cls, "Config") or not hasattr(cls.Config, "use_vector_index"):
            return True
        return cls.Config.use_vector_index
