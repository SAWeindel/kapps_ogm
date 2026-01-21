"""Core Node class for managing RDF-backed entity instances."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, Optional, TypeVar, Union, List
import logging
import json

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from rdflib import BNode
from graph_db_interface import IRI
from graph_db_interface.utils.types import Triple, IRILike

from .node_serializer import NodeSerializer
from .node_validator import NodeValidator
from .node_data_formatter import NodeDataFormatter
from .node_property_chains import NodePropertyChainExtractor

if TYPE_CHECKING:
    from circular_factory_ogm.mapping.class_spec import ClassSpec
    from circular_factory_ogm.ogm import OGM

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger("cf_node")
logger.setLevel(logging.DEBUG)


class Node:
    """Lightweight runtime handle for an RDF-backed instance.

    A Node represents an entity identified by an IRI and may carry:
    - a ClassSpec describing its schema,
    - raw loaded data,
    - a materialized Pydantic instance.

    It coordinates the entity lifecycle, including lazy loading and
    materialization, without embedding persistence logic itself.
    """

    def __init__(
        self,
        *,
        id: Optional[Union[str, IRI, BNode]] = None,
        class_spec: Optional["ClassSpec"] = None,
        data: Optional[Dict[IRILike, List[Any]]] = None,
        instance: Optional[T] = None,
        ogm: Optional[OGM] = None,
    ):
        """
        Initialize a node with identity and optional state.

        Either an explicit IRI/BNode or an instance exposing an ``id`` attribute
        must be provided. If both are given, they must match.
        """
        if instance is not None and hasattr(instance, "id") and instance.id is not None:
            if id is None:
                id = instance.id
            elif id != instance.id:
                raise ValueError("Provided id does not match instance id")

        if data is not None and "id" in data and data["id"] is not None:
            if id is None:
                id = data["id"]
            elif id != data["id"]:
                raise ValueError("Provided id does not match instance id")

        if id is not None and not isinstance(id, (IRI, BNode)):
            id = IRI(id)

        # Core attributes - use provided id or instance id
        self.id = id
        self.class_spec = class_spec
        self.ogm = ogm

        self._data = None
        self.instance = instance

        # Set data through property to trigger sanitization
        if data is not None:
            self.data = data

    # -------------------------
    # Lifecycle helpers
    # -------------------------

    @property
    def is_materialized(self) -> bool:
        """Check if the node has a materialized Pydantic instance."""
        return self.instance is not None

    @property
    def has_data(self) -> bool:
        """Check if the node has loaded data."""
        return self._data is not None

    # -------------------------
    # Data access
    # -------------------------

    @property
    def data(self) -> Optional[Dict[IRI, List[Any]]]:
        """
        Get the raw instance data for this node.

        Returns:
            Optional[Dict[IRI, List[Any]]]: Raw instance data if loaded, else None.
        """
        return self._data

    @data.setter
    def data(self, value: Dict[IRILike, List[Any]]) -> None:
        """
        Set or update the raw data for this node.

        Args:
            value (Dict): Raw instance data to set on the node.
        """
        if value is None:
            self._data = None
            return

        # Sanitize data through the formatter
        sanitized, node_id = NodeDataFormatter.sanitize_data(value, self.ogm)
        self._data = sanitized

        # Update node ID if found in data
        if node_id is not None:
            self.id = node_id

    # -------------------------
    # Materialization
    # -------------------------

    def materialize(self, *, reload: bool = False) -> BaseModel:
        """
        Return a validated Pydantic model instance for this node.

        Lazily materializes the nodes loaded data into a Pydantic model on first
        access and caches the result. Subsequent calls return the cached instance
        without reprocessing.

        If data has not yet been loaded, it is loaded automatically before
        materialization.

        If ``reload`` is True, any cached instance is discarded. The nodes data
        is reloaded from the database and a new instance is materialized.

        Returns:
            BaseModel: A validated Pydantic model corresponding to the nodes
            ClassSpec. The instance is cached on the node.

        Raises:
            RuntimeError: If no OGM is attached to load data.
            ValidationError: If the loaded data violates the ClassSpec constraints.

        Notes:
            - This is the preferred way to access node data in application code.
            - Modifications to the returned instance must be persisted explicitly
            via the OGM.
        """
        if self.instance is not None and not reload:
            return self.instance
        if self.data is None:
            raise RuntimeError("Node has no data")
        if self.class_spec is None:
            raise RuntimeError("Node has no ClassSpec")

        # Validate data
        NodeValidator.validate(self)

        # Format data for Pydantic
        formatted_data = NodeDataFormatter.format_for_instance(self)

        model_cls = self.class_spec.to_pydantic_model()
        self.instance = model_cls.model_validate(formatted_data)
        return self.instance

    # -------------------------
    # Serialization (delegated)
    # -------------------------

    def to_triples(self) -> set[Triple]:
        """
        Serialize the nodes current instance into RDF triples for persistence.

        Delegates to NodeSerializer.to_triples().
        """
        return NodeSerializer.to_triples(self)

    def to_json_ld(self, context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Serialize the nodes instance into JSON-LD format.

        Delegates to NodeSerializer.to_json_ld().
        """
        return NodeSerializer.to_json_ld(self, context)

    # -------------------------
    # Property chain extraction (delegated)
    # -------------------------

    def extract_property_chains(self) -> list[list[IRI | str]]:
        """
        Extract property chains from nested node data.

        Delegates to NodePropertyChainExtractor.extract().
        """
        return NodePropertyChainExtractor(self).extract()

    # -------------------------
    # Debugging utilities
    # -------------------------

    def log_data_debug(self) -> None:
        """Pretty print data for debugging."""
        if logger.isEnabledFor(logging.DEBUG) and self.data:
            from circular_factory_ogm.utils.pretty_print import format_node_data

            logger.debug(json.dumps(format_node_data(self.data), indent=2))

    # -------------------------
    # Representation
    # -------------------------

    def __repr__(self) -> str:
        """
        Return a concise string representation of the node for debugging.

        The representation reflects the nodes lifecycle state:
        - Materialized nodes include the Pydantic instance representation.
        - Unmaterialized nodes include the node IRI and flags indicating whether
        data and a ClassSpec are present.

        Returns:
            str: A human-readable representation of the nodes current state.
        """
        if self.instance:
            return f"Node<instance {self.instance!r}>"
        return (
            f"Node<ref {self.id!r}, "
            f"data={self.data is not None}, "
            f"class_spec={self.class_spec is not None}>"
        )

    # -------------------------
    # Pydantic integration
    # -------------------------

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
