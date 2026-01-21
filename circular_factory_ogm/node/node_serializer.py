"""Serialization utilities for Node instances to RDF and JSON-LD formats."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, Optional, Union
from collections import defaultdict

from rdflib import BNode, Literal
from graph_db_interface import IRI, to_literal
from graph_db_interface.utils.types import Triple

if TYPE_CHECKING:
    from .core import Node


def to_triples(self: "Node") -> set[Triple]:
    """Serialize the nodes current instance into RDF triples for persistence.

    Uses the in-memory materialized instance and cached data. Updates in
    memory will be reflected in the serialized triples.

    Args:
        node: The Node instance to serialize.

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

    iri_field_map: dict[str, IRI] = getattr(self.instance.__class__, "_iri_fields", {})

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
            triples |= _value_to_triples(
                self=self,
                subject=subject,
                predicate=prop_iri,
                value=v,
            )

    return triples


def to_json_ld(
    self: "Node", context: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Serialize the nodes instance into JSON-LD format.

    Converts RDF triples to JSON-LD with proper handling of IRIs, blank nodes,
    and literals. Blank nodes are inlined recursively for cleaner output.

    Args:
        node: The Node instance to serialize.
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
    triples = to_triples(self)

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
        json_node = {"@id": compact_iri(main_subject)}
        json_node.update(inline_blank_nodes(subjects[main_subject]))
        json_ld_nodes.append(json_node)

    # Add other named (non-blank) nodes
    for subj, props in subjects.items():
        if subj != main_subject and not str(subj).startswith("genid-"):
            json_node = {"@id": compact_iri(subj)}
            json_node.update(inline_blank_nodes(props))
            json_ld_nodes.append(json_node)

    return {"@context": context or {}, "@graph": json_ld_nodes}


def _value_to_triples(
    self: "Node",
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
        node: The parent Node instance (for accessing ogm).
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
    from pydantic import BaseModel
    from .core import Node

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
        triples |= to_triples(nested_node)

    # Case 2: IRI object
    elif isinstance(value, IRI):
        triples.add((subject, predicate, value))

    # Case 3: Literal
    else:
        triples.add((subject, predicate, to_literal(value)))

    return triples
