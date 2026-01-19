from __future__ import annotations
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Optional,
    TypeVar,
    Union,
    List,
    Callable,
    Type,
    get_args,
)
from collections import defaultdict
from itertools import batched
import logging
import json
from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import CoreSchema, ValidationError, core_schema
from rdflib import BNode, Literal
from graph_db_interface import IRI, to_literal
from graph_db_interface.exceptions import InvalidIRIError
from graph_db_interface.utils.types import Triple, IRILike

from circular_factory_ogm.mapping.property_spec import PropertyValueKind


if TYPE_CHECKING:
    from circular_factory_ogm.mapping.class_spec import ClassSpec
    from circular_factory_ogm.ogm import OGM

T = TypeVar("T", bound=BaseModel)

logger = logging.Logger("cf_node")
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

        self.data = data
        self.instance = instance

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

    @property
    def data(self) -> Optional[Dict[IRI, List[Any]]]:
        """
        Get the raw instance data for this node.

        Returns:
            Optional[Dict[IRILike, List[Any]]]: Raw instance data if loaded, else None.
        """
        return self._data

    @data.setter
    def data(self, value: Dict[IRILike, List[Any]]) -> None:
        """
        Set or update the raw data for this node.

        Args:
            data (Dict): Raw instance data to set on the node.
        """
        if value is None:
            self._data = None
            return
        self._sanitize_data(value)

    def _sanitize_data(self, data: Dict) -> dict[IRI, List[Any]]:
        """
        Recursively converts provided data dict into a unified format.

        The output is a dict with items in any of the forms:
            - IRI: List[Any] # literal property -> list of literal values
            - IRI: List[Node] # class property -> list of Node instances with IRI ids
            - IRI: List[Node] # complex property -> list of Node instances with blank ids
        In the input, property keys can be either str or IRI. Class and complex property values may be represented as dicts

        Raises:
            ValueError: If data cannot be converted into the expected format.
        """
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        self._data = {}

        for property_iri, domain_list in data.items():
            # Catch special cases
            if property_iri == "id":
                self.id = IRI(domain_list)
                continue

            try:
                property_iri = IRI(property_iri)
            except Exception as e:
                try:
                    property_iri = IRI.from_lined(property_iri)
                except Exception:
                    raise ValueError(f"Invalid property in data: {property_iri}") from e

            if not isinstance(domain_list, list):
                raise ValueError(
                    f"Property {property_iri} data must be a list, got {type(domain_list)}"
                )

            self._data[property_iri] = []

            for domain_instance in domain_list:
                if isinstance(domain_instance, Node):
                    # Already a Node, use as is
                    self._data[property_iri].append(domain_instance)
                elif isinstance(domain_instance, dict):
                    # Convert dict to Node
                    node = Node(
                        data=domain_instance,
                        ogm=self.ogm,
                    )
                    self._data[property_iri].append(node)
                else:
                    self._data[property_iri].append(domain_instance)
            logger.debug(
                f"Converted property {property_iri} with {len(self._data[property_iri])} items to Node list"
            )

    def _validate_data(
        self,
        class_spec: Optional[ClassSpec] = None,
        strict: bool = True,
        # strict: bool = False,
    ) -> None:
        """
        Validate the nodes data against its ClassSpec.

        Args:
            strict (bool): If True, enforce strict validation rules. In this case, no unknown properties are permitted. Defaults to True.
        """
        if self.data is None:
            raise ValueError("Node does not contain data to validate")

        if self.class_spec is None:
            if class_spec is None:
                raise ValueError("Cannot validate data without ClassSpec")
            self.class_spec = class_spec

        # Check that node IRI is instance of ClassSpec IRI
        if self.id is not None and self.class_spec.iri is not None:
            if self.ogm.db.iri_exists(
                self.id, as_sub=True, as_pred=True, as_obj=True
            ) and not self.ogm.db.is_subclass(self.id, self.class_spec.iri):
                raise ValueError(
                    f"Node IRI {self.id} is known but is not an instance of ClassSpec {self.class_spec.iri}"
                )

        # Check that data properties conform to ClassSpec properties
        data_properties = set(self.data.keys())
        permitted_properties = set(self.class_spec.properties.keys())
        required_properties = set(
            p for p, s in self.class_spec.properties.items() if s.required
        )

        if data_properties < required_properties:
            missing_properties = required_properties - data_properties
            raise ValueError(
                f"Missing required properties in data for ClassSpec {self.class_spec.iri}: {missing_properties}"
            )

        if data_properties > permitted_properties:
            unknown_properties = data_properties - permitted_properties
            logger.warning(
                f"Unknown properties in data for ClassSpec {self.class_spec.iri}: {unknown_properties}"
            )
            if strict:
                raise ValueError(
                    f"Unknown properties in data for ClassSpec {self.class_spec.iri}: {unknown_properties}"
                )

        known_properties = data_properties & permitted_properties

        # Check each property against its specification
        for property_iri in known_properties:
            domain_list = self.data[property_iri]
            prop_spec = self.class_spec.properties[property_iri]

            # Check cardinality. sh:minCount only enforced in strict, according to the OWA.
            if prop_spec.min_count and len(domain_list) < prop_spec.min_count:
                logger.warning(
                    f"Node {self.id} property {property_iri} has fewer items ({len(domain_list)}) than min_count ({prop_spec.min_count})"
                )
                if strict:
                    raise ValueError(
                        f"Node {self.id} property {property_iri} has fewer items ({len(domain_list)}) than min_count ({prop_spec.min_count})"
                    )

            if prop_spec.max_count and len(domain_list) > prop_spec.max_count:
                logger.warning(
                    f"Node {self.id} property {property_iri} has more items ({len(domain_list)}) than max_count ({prop_spec.max_count})"
                )
                if strict:
                    raise ValueError(
                        f"Node {self.id} property {property_iri} has more items ({len(domain_list)}) than max_count ({prop_spec.max_count})"
                    )

            # Check type
            match prop_spec.value_kind:
                case PropertyValueKind.OBJECT | PropertyValueKind.COMPLEX:
                    # TODO Add checks for owl:allValuesFrom and owl:someValuesFrom for object properties.
                    # Maybe collect set of failed and passed checks?
                    logger.info(
                        f"Cardinality checks for object properties ({property_iri}) not implemented yet."
                    )

                    for domain_instance in domain_list:
                        if not isinstance(domain_instance, Node):
                            raise ValueError(
                                f"Node {self.id} property {property_iri} expected Node instances, got literal"
                            )
                        # Recursively call nodes
                        domain_instance._validate_data(
                            class_spec=prop_spec.nested,
                            strict=strict,
                        )
                case PropertyValueKind.LITERAL:
                    permitted_types = prop_spec.python_range_type

                    if not permitted_types:
                        logger.debug(
                            f"PropSpec {prop_spec.iri} has no permitted types defined, skipping type check."
                        )
                        continue

                    # owl:allValuesFrom
                    if prop_spec.all_from and not all(
                        isinstance(domain_instance, permitted_types)
                        for domain_instance in domain_list
                    ):
                        raise ValueError(
                            f"Node {self.id} property {property_iri} expected owl:allValuesFrom {permitted_types}, got {type(domain_instance)}"
                        )

                    # owl:someValuesFrom. Only enforced in strict, according to the OWA.
                    if prop_spec.some_from and not any(
                        isinstance(domain_instance, permitted_types)
                        for domain_instance in domain_list
                    ):
                        logger.warning(
                            f"Node {self.id} property {property_iri} expected owl:someValuesFrom {permitted_types}, got {type(domain_instance)}"
                        )
                        if strict:
                            raise ValueError(
                                f"Node {self.id} property {property_iri} expected owl:someValuesFrom {permitted_types}, got {type(domain_instance)}"
                            )

    def _format_data_for_instance(self) -> Dict[str, List[Any]]:
        """
        Recursively resolve property data to a model.
        Converts Nodes to their data, property IRIs to their lined representation.
        """
        if not self.id:
            self.ogm._assign_id(self)

        formatted_data = {"id": self.id}
        for property_iri, domain_list in self.data.items():
            property_str = property_iri.lined
            if domain_list and isinstance(domain_list[0], Node):
                formatted_data[property_str] = [
                    Node._format_data_for_instance(domain_item)
                    for domain_item in domain_list
                ]
            else:
                formatted_data[property_str] = domain_list.copy()
        return formatted_data

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

        self._validate_data()
        formatted_data = self._format_data_for_instance()

        model_cls = self.class_spec.to_pydantic_model()
        self.instance = model_cls.model_validate(formatted_data)
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

        iri_field_map: dict[str, IRI] = getattr(
            self.instance.__class__, "_iri_fields", {}
        )

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
            value = getattr(self.instance, field_name, None)
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

    def extract_property_chains(self) -> list[list[IRI | str]]:
        """
        Extract property chains from nested node data.

        Reconstructs full IRIs from lined keys using hybrid lookup:
        1. Direct IRI construction (already full IRI)
        2. _iri_fields mapping (top-level properties from ClassSpec)
        3. Decode from lined format (nested properties)
        4. Fallback to string if all fail

        Returns:
            list[list[IRI | str]]: Property chains from root to each terminal value,
                                   with all keys normalized to full IRIs where possible.
        """
        property_chains: list[list[IRI | str]] = []

        if not self.data:
            logger.debug("No data to extract property chains from.")
            return property_chains

        def normalize_key(key: str) -> IRI | str:
            """
            Normalize property key to IRI with hybrid lookup strategy.

            Resolves lined keys back to full IRIs in this order:
            1. Try direct IRI construction (already full IRI)
            2. Try _iri_fields mapping lookup (fast path for known top-level props)
            3. Try decode from lined format (nested/dynamic props)
            4. Return as string if all fail
            """
            # 1. Already a full IRI
            if "://" in key:
                try:
                    return IRI(key)
                except (InvalidIRIError, TypeError):
                    pass

            # 2. Try mapping lookup (fast path)
            if self.class_spec:
                model = self.class_spec.to_pydantic_model()
                iri_fields = getattr(model, "_iri_fields", {})
                if key in iri_fields:
                    return iri_fields[key]

            # 3. Fallback: decode from lined format
            # Markers _c_, _s_, _d_, _h_ indicate a lined key
            if any(marker in key for marker in ("_c_", "_s_", "_d_", "_h_")):
                try:
                    return IRI.from_lined(key)
                except (InvalidIRIError, TypeError, ValueError):
                    pass

            # 4. Return as string
            return key

        def walk(value: Any, path: list[IRI | str]) -> None:
            """Recursively walk nested structure, extracting terminal property paths."""
            if not isinstance(value, list):
                return
            for item in value:
                if not isinstance(item, dict):
                    # Primitive value in list - don't go deeper
                    continue
                # Item is a dict - walk through its properties
                for key, child_value in item.items():
                    if key == "id":
                        continue
                    new_path = path + [normalize_key(key)]
                    # Check if child_value contains more nested dicts
                    has_nested_dicts = False
                    if isinstance(child_value, list):
                        for sub_item in child_value:
                            if isinstance(sub_item, dict):
                                has_nested_dicts = True
                                break
                    if has_nested_dicts:
                        # Continue walking
                        walk(child_value, new_path)
                    else:
                        # Terminal - child_value is primitives or empty
                        property_chains.append(new_path)

        for key, value in self.data.items():
            if key == "id":
                continue
            walk(value, [normalize_key(key)])

        return property_chains

    def log_data_debug(self) -> None:
        """
        # Pretty print data for debugging
        """
        if logger.isEnabledFor(logging.DEBUG) and self.data:

            def convert_to_serializable(obj):
                """Convert IRI and other non-serializable objects to strings."""
                if isinstance(obj, (IRI, BNode)):
                    return str(obj)
                elif isinstance(obj, dict):
                    return {
                        convert_to_serializable(k): convert_to_serializable(v)
                        for k, v in obj.items()
                    }
                elif isinstance(obj, list):
                    return [convert_to_serializable(item) for item in obj]
                return obj

            logger.debug(json.dumps(convert_to_serializable(self.data), indent=2))

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
