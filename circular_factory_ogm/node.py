from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, Optional, TypeVar, Union
from collections import defaultdict

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from rdflib import BNode, Literal
from graph_db_interface import IRI, to_literal
from graph_db_interface.utils.types import Triple


if TYPE_CHECKING:
    from circular_factory_ogm.mapping.class_spec import ClassSpec
    from circular_factory_ogm.ogm import OGM

T = TypeVar("T", bound=BaseModel)


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
        data: Optional[Dict[str, Any]] = None,
        instance: Optional[T] = None,
        ogm: Optional[OGM] = None,
    ):
        """
        Initialize a node with identity and optional state.

        Either an explicit IRI/BNode or an instance exposing an ``id`` attribute
        must be provided. If both are given, they must match.
        """
        if id is None and instance is None:
            raise ValueError("Either 'id' or 'instance' must be provided")

        # Keep BNode as is, convert string to IRI only if not already IRI/BNode
        if id is not None and not isinstance(id, (IRI, BNode)):
            id = IRI(id)

        # Get instance id if available
        instance_id = getattr(instance, "id", None) if instance is not None else None

        # Validate id match if both provided
        if id is not None and instance_id is not None and id != instance_id:
            raise ValueError("Provided id does not match instance id")

        # Core attributes - use provided id or instance id
        self.id: Optional[Union[IRI, BNode]] = id if id is not None else instance_id
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

    def load_data(self, *, reload: bool = False) -> Dict[str, Any]:
        """
        Load and return raw instance data from the graph database.

        Lazily fetches data for this node via the configured OGM loader and caches
        the result. Subsequent calls return the cached data without re-querying
        the database.

        If ``reload`` is True, any cached data is discarded and the data is fetched
        again from the database.

        The returned data is a JSON-compatible dictionary structured according to
        the nodes ClassSpec.

        Args:
        reload: If True, force a reload from the database even if data is cached.

        Returns:
            Dict[str, Any]: Raw instance data for this node. The result is cached
            on the node.

        Raises:
            RuntimeError: If no OGM is attached to the node.

        Notes:
            - This method returns unvalidated raw data.
            - For validated, type-safe access, use ``materialize()``.
        """
        if self.data is not None and not reload:
            return self.data
        if not self.ogm:
            raise RuntimeError("No OGM attached to load data")
        self.data = self.ogm._fetch_from_node(self)
        return self.data

    def _validate_instance(self) -> BaseModel:
        """
        Validate and build a Pydantic instance from the node's loaded data.

        Returns:
            BaseModel: A validated Pydantic model instance.

        Raises:
            ValueError: If ClassSpec or data is missing.
            ValidationError: If the loaded data violates the ClassSpec constraints.
        """
        if self.class_spec is None:
            raise ValueError("Cannot create instance without ClassSpec")
        if self.data is None:
            raise ValueError("Cannot create instance without loaded data")

        model_cls = self.class_spec.to_pydantic_model()

        data = Node._format_data_for_validation(self.data)
        model = model_cls.model_validate(data)
        return model

    @staticmethod
    def _format_data_for_validation(data: Any) -> Any:
        """
        Recursively resolve property data to a model.
        Converts Nodes to their data, property IRIs to their lined representation.
        """
        match data:
            case dict():
                return {
                    (
                        k.lined if isinstance(k, IRI) else k
                    ): Node._format_data_for_validation(v)
                    for k, v in data.items()
                }
            case list():
                return [Node._format_data_for_validation(item) for item in data]
            case Node():
                return Node._format_data_for_validation(data.data)
            case _:
                return data

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
        if self.data is None or reload:
            if not self.ogm:
                raise RuntimeError("No OGM attached to load data")
            self.load_data(reload=reload)
        self.instance = self._validate_instance()
        return self.instance

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

    def to_triples(self) -> set[Triple]:
        """Serialize the nodes current instance into RDF triples for persistence.

        Uses the in-memory materialized instance and cached data. Updates in
        memory will be reflected in the serialized triples.

        Returns:
            set[Triple]: RDF triples representing this node, including nested objects.

        Raises:
            RuntimeError: If the node has no ClassSpec or IRI.

        Notes:
            - Intended for persisting the current instance state.
            - Always uses the cached instance; does not refresh from the database.
        """
        if self.instance is None:
            raise RuntimeError("Node must be materialized before calling to_triples")

        model = self.instance
        iri_field_map: dict[str, IRI] = getattr(model.__class__, "_iri_fields", {})

        # We need either a ClassSpec or _iri_fields to know how to serialize
        if self.class_spec is None and not iri_field_map:
            raise RuntimeError(
                "Node must have a ClassSpec or _iri_fields to serialize to triples"
            )

        triples: set[Triple] = set()

        subject = self.id
        if subject is None:
            raise RuntimeError("Node has no IRI")

        # Add type triples only for named classes (those with a class IRI)
        if self.class_spec and self.class_spec.iri:
            triples.add((subject, "rdf:type", self.class_spec.iri))
            triples.add((subject, "rdf:type", "owl:NamedIndividual"))

        # Serialize all properties from the Pydantic model
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

    def to_json_ld(self, context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Serialize the nodes instance into JSON-LD format.

        Converts RDF triples to JSON-LD with proper handling of IRIs, blank nodes,
        and literals. Blank nodes are inlined recursively for cleaner output.

        Args:
            context: Optional @context dictionary mapping prefixes to namespace URIs.
                    If provided, URIs are compacted using these prefixes.

        Returns:
            Dict[str, Any]: JSON-LD document with @context and @graph keys.
                          Main subject appears first in @graph, followed by other
                          named nodes. Blank nodes are inlined as nested objects.

        Notes:
            - Calls to_triples() internally to obtain RDF representation
            - Literal datatypes are preserved as native Python types
            - Multiple property values are represented as JSON arrays
            - Context prefixes are registered globally in IRI.PREFIXES
        """
        triples = self.to_triples()

        # Register context prefixes for compaction
        if context:
            for prefix, namespace in context.items():
                IRI.add_prefix(prefix, namespace)

        def compact_iri(iri_str: str) -> str:
            """Compact a full IRI to prefix:name form if possible."""
            if iri_str.startswith("genid-"):
                return iri_str  # Don't compact blank nodes
            try:
                iri = IRI(iri_str)
                return iri.short
            except:
                return iri_str

        # Group triples by subject
        subjects: Dict[Union[str, BNode], Dict[str, Any]] = defaultdict(dict)
        blank_nodes: set[BNode] = set()

        for s, p, o in triples:
            # Track blank nodes
            if isinstance(s, BNode):
                blank_nodes.add(s)
            if isinstance(o, BNode):
                blank_nodes.add(o)

            # Convert subject to string
            subj_str = str(s) if isinstance(s, (IRI, BNode)) else s

            # Handle type declarations
            if p == "rdf:type" or (
                isinstance(p, IRI) and str(p).endswith("rdf-syntax-ns#type")
            ):
                if "@type" not in subjects[subj_str]:
                    subjects[subj_str]["@type"] = []
                # Convert object to string and compact
                type_val = compact_iri(str(o)) if isinstance(o, IRI) else o
                if type_val not in subjects[subj_str]["@type"]:
                    subjects[subj_str]["@type"].append(type_val)
                continue

            # Convert predicate to string and compact
            pred_str = compact_iri(str(p)) if isinstance(p, IRI) else p

            # Convert object to appropriate JSON-LD value
            if isinstance(o, Literal):
                # Handle rdflib Literal with datatype
                value = o.toPython()  # Convert to native Python type
            elif isinstance(o, BNode):
                # Blank node - will be inlined later
                value = {"@id": str(o)}
            elif isinstance(o, IRI):
                # IRI reference - compact the IRI
                value = {"@id": compact_iri(str(o))}
            else:
                # Plain value
                value = o

            # Handle multiple values per predicate
            if pred_str in subjects[subj_str]:
                existing = subjects[subj_str][pred_str]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    subjects[subj_str][pred_str] = [existing, value]
            else:
                subjects[subj_str][pred_str] = value

        # Inline blank nodes recursively
        def inline_blank_nodes(node_dict: Dict[str, Any]) -> Dict[str, Any]:
            """Recursively inline blank node references."""
            result = {}
            for key, value in node_dict.items():
                if key == "@id":
                    # Keep @id as is
                    result[key] = value
                elif isinstance(value, dict) and "@id" in value:
                    # Check if this is a blank node reference
                    ref_id = value["@id"]
                    if ref_id in subjects and ref_id.startswith("genid-"):
                        # Inline the blank node
                        blank_node_data = subjects[ref_id].copy()
                        # Don't include @id for inline blank nodes
                        blank_node_data.pop("@id", None)
                        # Recursively inline nested blank nodes
                        result[key] = inline_blank_nodes(blank_node_data)
                    else:
                        # Keep as reference
                        result[key] = value
                elif isinstance(value, list):
                    # Handle arrays
                    result[key] = [
                        (
                            inline_blank_nodes(item)
                            if isinstance(item, dict)
                            and "@id" in item
                            and item["@id"] in subjects
                            and item["@id"].startswith("genid-")
                            else (
                                inline_blank_nodes(subjects[item["@id"]].copy())
                                if isinstance(item, dict)
                                and "@id" in item
                                and item["@id"].startswith("genid-")
                                else item
                            )
                        )
                        for item in value
                    ]
                else:
                    result[key] = value
            return result

        # Build JSON-LD graph with blank nodes inlined
        json_ld_nodes = []
        main_subject = str(self.id)

        # Add main subject first
        if main_subject in subjects:
            node = {"@id": compact_iri(main_subject)}
            node.update(inline_blank_nodes(subjects[main_subject]))
            json_ld_nodes.append(node)

        # Add other named (non-blank) nodes
        for subj, props in subjects.items():
            if subj != main_subject and not str(subj).startswith("genid-"):
                node = {"@id": compact_iri(subj)}
                node.update(inline_blank_nodes(props))
                json_ld_nodes.append(node)

        return {"@context": context or {}, "@graph": json_ld_nodes}

    def _value_to_triples(
        self,
        subject: IRI,
        predicate: IRI,
        value: Any,
    ) -> set[Triple]:
        """
        Convert a property value into RDF triples.

        Handles nested Pydantic objects (serialized to blank nodes or their own IRI),
        IRI references (linked directly), and literals (converted with type annotations).
        Nested objects are serialized recursively.

        Args:
            subject: The subject IRI for the generated triples.
            predicate: The property IRI relating subject to value.
            value: The value to serialize (Pydantic model, IRI, or primitive).

        Returns:
            set[Triple]: RDF triples representing the value. Single triple for
                        literals/IRIs, multiple for nested objects.

        Notes:
            - Internal helper called by to_triples()
            - Blank nodes get fresh IDs on each serialization
        """
        triples: set[Triple] = set()

        # Case 1: Nested Pydantic object
        if isinstance(value, BaseModel):
            # Check if nested object has its own ID (named instance)
            nested_id = getattr(value, "id", None)
            if nested_id:
                # Use the object's own IRI
                obj = nested_id if isinstance(nested_id, IRI) else IRI(nested_id)
            else:
                # Create blank node for anonymous nested object
                obj = BNode(self.ogm.db.new_blank_id())

            triples.add((subject, predicate, obj))

            # Recurse - nested object serializes its own properties
            nested_node = Node(
                id=obj,
                instance=value,
                class_spec=None,  # Properties encoded in Pydantic model
                ogm=self.ogm,
            )
            triples |= nested_node.to_triples()

        # Case 2: IRI object
        elif isinstance(value, IRI):
            triples.add((subject, predicate, value))

        # Case 3: Literal
        else:
            triples.add((subject, predicate, to_literal(value)))

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
