from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, Optional, TypeVar, Union

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from graph_db_interface import IRI

if TYPE_CHECKING:
    from .builders.mapping.class_spec import ClassSpec

if TYPE_CHECKING:
    from .ogm import OGM

T = TypeVar("T", bound=BaseModel)


class Node:
    """
    Lightweight runtime handle for an RDF-backed instance.

    Responsibilities:
    - Hold identity (IRI)
    - Hold optional ClassSpec
    - Hold optional instance data
    - Coordinate lifecycle (lazy load, materialize)
    """

    def __init__(
        self,
        *,
        id: Optional[Union[str, IRI]] = None,
        class_spec: Optional["ClassSpec"] = None,
        data: Optional[Dict[str, Any]] = None,
        instance: Optional[T] = None,
        ogm: Optional[OGM] = None,
    ):
        """Initialize a Node with identity, optional spec, data, instance, and OGM."""
        if id is None and instance is None:
            raise ValueError("Either 'id' or 'instance' must be provided")

        if id is not None and not isinstance(id, IRI):
            id = IRI(id)

        if instance is not None and not hasattr(instance, "id"):
            raise ValueError("Instance must expose an 'id' attribute")

        if (
            id is not None
            and instance is not None
            and getattr(instance, "id", None) != id
        ):
            raise ValueError("Instance id does not match provided IRI")

        # Core attributes
        self.id: Optional[IRI] = id or getattr(instance, "id", None)
        self.class_spec = class_spec
        self.data = data
        self.instance = instance
        self.ogm = ogm

    # -------------------------
    # Lifecycle helpers
    # -------------------------

    @property
    def is_materialized(self) -> bool:
        return self.instance is not None

    @property
    def has_data(self) -> bool:
        return self.data is not None

    # -------------------------
    # Explicit loading
    # -------------------------

    def load_data(self) -> Dict[str, Any]:
        if self.data is not None:
            return self.data
        if not self.ogm:
            raise RuntimeError("No OGM attached to load data")
        self.data = self.ogm.loader(self)
        return self.data

    def materialize(self) -> BaseModel:
        if self.instance is not None:
            return self.instance
        if not self.ogm:
            raise RuntimeError("No OGM attached to build instance")
        if self.data is None:
            self.load_data()
        self.instance = self.ogm.create_node_instance(self)
        return self.instance

    # -------------------------
    # Representation
    # -------------------------

    def __repr__(self) -> str:
        if self.instance:
            return f"Node<instance {self.instance!r}>"
        return (
            f"Node<ref {self.id!r}, "
            f"data={self.data is not None}, "
            f"class_spec={self.class_spec is not None}>"
        )

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        """
        Provide a permissive Pydantic core schema for IRI fields.

        Args:
            source_type (Any): The source type passed by Pydantic.
            handler (GetCoreSchemaHandler): Pydantic schema handler.

        Returns:
            CoreSchema: A schema accepting any value (validated by IRI itself).
        """
        return core_schema.any_schema()
