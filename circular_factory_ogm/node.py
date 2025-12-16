from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, Optional, TypeVar, Union

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from graph_db_interface import IRI
from uuid import uuid4


if TYPE_CHECKING:
    from circular_factory_ogm.builders.mapping.class_spec import ClassSpec
    from circular_factory_ogm.ogm import OGM

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

    def to_triples(
        self,
    ) -> set[tuple[IRI, IRI, Union[IRI, Any]]]:
        """
        Serialize this Node's instance into RDF triples.

        Returns:
            Set of (subject, predicate, object) triples
        """
        if self.instance is None:
            raise RuntimeError("Node must be materialized before calling to_triples")

        if self.class_spec is None:
            raise RuntimeError("Node must have a ClassSpec to serialize to triples")

        triples: set[tuple[IRI, IRI, Union[IRI, Any]]] = set()

        subject = self.id
        if subject is None:
            raise RuntimeError("Node has no IRI")

        if self.class_spec.iri:
            triples.add((subject, "rdf:type", self.class_spec.iri))
            triples.add((subject, "rdf:type", "owl:NamedIndividual"))

        model = self.instance
        iri_field_map: dict[str, IRI] = getattr(model.__class__, "_iri_fields", {})

        for field_name, prop_iri in iri_field_map.items():
            value = getattr(model, field_name, None)
            if value is None:
                continue

            # Always treat as list
            values = value if isinstance(value, list) else [value]

            for v in values:
                triples |= self._value_to_triples(
                    subject=subject,
                    predicate=prop_iri,
                    value=v,
                )

        return triples

    def _value_to_triples(
        self,
        *,
        subject: IRI,
        predicate: IRI,
        value: Any,
    ) -> set[tuple[IRI, IRI, Union[IRI, Any]]]:
        """
        Convert a single property value into triples.
        """
        triples: set[tuple[IRI, IRI, Union[IRI, Any]]] = set()

        # Case 1: Nested Pydantic object
        if isinstance(value, BaseModel):
            bnode = IRI(f"_:{uuid4().hex}")
            triples.add((subject, predicate, bnode))

            # Recurse
            nested_node = Node(
                id=bnode,
                instance=value,
                class_spec=None,  # Nested already encoded in model
                ogm=self.ogm,
            )
            triples |= nested_node.to_triples()

        # Case 2: IRI object
        elif isinstance(value, IRI):
            triples.add((subject, predicate, value))

        # Case 3: Literal
        else:
            triples.add((subject, predicate, value))

        return triples

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
