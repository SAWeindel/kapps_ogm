from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import logging
import pydantic as pd
from pydantic import ValidationError

from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.node.core import Node
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.mapping.property_spec import PropertySpec
from circular_factory_ogm.utils.blank_instance import (
    _create_blank_instance,
    _blank_instance_from_class_spec,
    _blank_value_for_property,
)


class OGM:
    """
    Maps RDF graphs to Pydantic objects with explicit orchestration.

    **Operations:**
    - fetch(instance_iri): Read RDF instances
    - create(class_iri, data): Write new objects
    - get_class_spec(class_iri): Inspect schemas

    Instantiate OGM with a GraphDB and loader, then call these methods
    for REST API endpoints, JSON serialization, or direct programmatic access.

    No registries, global state, or implicit expansion.
    """

    def __init__(
        self,
        *,
        db: GraphDB,
        loader: Callable[[Node], Dict[str, Any]],
        node_naming_schema: Optional[Callable[[IRI], IRI]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Args:
            db: GraphDB interface
            loader: Callable that loads instance data respecting Node.class_spec
        """
        self.db = db
        self._loader = loader
        self.node_naming_schema = node_naming_schema or (
            lambda class_iri: self.db.new_iri(
                base=f"{class_iri.onto}Instances#{class_iri.fragment}_"
            )
        )
        self.logger = logger or logging.getLogger("cf_ogm")

    # ------------------------------------------------------------------
    # Schema orchestration
    # ------------------------------------------------------------------

    def get_class_spec(
        self,
        *,
        class_iri: IRI,
        property_chains: Optional[list[list[IRI]]] = None,
    ) -> ClassSpec:
        """
        Resolve a ClassSpec for a given class IRI.

        property_chain defines selective hydration of nested properties.
        """
        self.logger.debug(
            "Resolving ClassSpec for %s (chain=%s)",
            class_iri,
            property_chains,
        )

        spec = ClassSpec.specify(
            class_iri=class_iri,
            ogm=self,
            property_chains=property_chains,
        )
        return spec

    # ------------------------------------------------------------------
    # Fetching existing instances
    # ------------------------------------------------------------------

    def fetch(
        self,
        *,
        instance_iri: IRI,
        property_chains: Optional[list[list[IRI]]] = None,
    ) -> Node:
        """
        Fetch an existing RDF instance from the database and return a Node.

        This is the primary entry point for:
        - REST GET
        - API reads
        - JSON export
        """
        self.logger.info("Fetching instance %s", instance_iri)

        class_iri = self._resolve_instance_type(instance_iri)
        class_spec = self.get_class_spec(
            class_iri=class_iri,
            property_chains=property_chains if property_chains else None,
        )

        node = Node(
            id=instance_iri,
            class_spec=class_spec,
            ogm=self,
        )

        return node

    def _resolve_instance_type(
        self,
        instance_iri: IRI,
    ) -> IRI:  # TODO: Do we need this? and if yes maybe move to graphdb interface
        """
        Resolve rdf:type of an instance.

        Currently expects exactly one concrete class.
        """
        triples = self.db.triples_get(
            sub=instance_iri,
            pred=IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            include_implicit=True,
        )

        types = [t[2] for t in triples]
        if not types:
            raise ValueError(f"No rdf:type found for instance {instance_iri}")
        if len(types) > 1:
            self.logger.warning(
                "Multiple rdf:types for %s, using first: %s",  # TODO: improve handling of multiple types
                instance_iri,
                types,
            )

        return types[0]

    # ------------------------------------------------------------------
    # Creation / schema-first workflow
    # ------------------------------------------------------------------
    def blank_value_for_property(
        self,
        prop: PropertySpec,
    ) -> Any:
        """Delegate to blank_instance helper to keep OGM lean."""
        return _blank_value_for_property(self, prop)

    def blank_instance_from_class_spec(
        self,
        *,
        class_spec: ClassSpec,
        instance_iri: Optional[IRI] = None,
    ) -> pd.BaseModel:
        """Delegate to blank_instance helper to keep OGM lean."""
        return _blank_instance_from_class_spec(
            self, class_spec=class_spec, instance_iri=instance_iri
        )

    def create_blank_instance(
        self,
        *,
        instance_iri: IRI,
        class_iri: IRI,
        property_chains: Optional[list[list[IRI]]] = None,
    ) -> pd.BaseModel:
        """Delegate to blank_instance helper to keep OGM lean."""
        return _create_blank_instance(
            self,
            instance_iri=instance_iri,
            class_iri=class_iri,
            property_chains=property_chains,
        )

    def create(
        self,
        *,
        class_iri: IRI,
        data: dict,
        property_chains: Optional[list[list[IRI]]] = None,
        instance_iri: Optional[IRI] = None,
    ) -> Node:
        """
        Create a new Node instance with given data.

        This is the primary entry point for:
        - REST POST
        - API writes
        - JSON import
        """
        self.logger.info("Creating new instance of class %s", class_iri)

        class_spec = self.get_class_spec(
            class_iri=class_iri,
            property_chains=property_chains if property_chains else None,
        )

        # Build Pydantic model from class_spec
        model_cls = class_spec.to_pydantic_model()

        # Extract ID from data or use provided instance_iri
        raw_id = data.get("id")
        if instance_iri:
            if self.db.iri_exists(instance_iri):
                raise ValueError(
                    f"Instance IRI {instance_iri} already exists in the database. use fetch instead of create."
                )
            id = instance_iri
        elif raw_id is not None:
            id = IRI(raw_id) if not isinstance(raw_id, IRI) else raw_id
        else:
            id = self.node_naming_schema(class_iri)

        # Prepare payload with id and auto-generate nested IDs
        payload = {**data, "id": id}
        self._inject_missing_ids(payload, class_spec)

        # Validate and instantiate Pydantic model
        try:
            instance = model_cls(**payload)
        except ValidationError as e:
            raise ValueError(f"Instance validation failed: {e}") from e

        node = Node(
            id=id,
            class_spec=class_spec,
            instance=instance,
            ogm=self,
        )

        return node

    def _inject_missing_ids(self, data: dict, class_spec: ClassSpec) -> None:
        """
        Recursively inject missing IDs into nested objects that require them.

        Args:
            data: The data dictionary to inject IDs into (modified in place)
            class_spec: The ClassSpec defining the structure
        """
        for prop_iri, prop_spec in class_spec.properties.items():
            field_name = prop_iri.lined

            if field_name not in data:
                continue

            value = data[field_name]
            if value is None:
                continue

            # Handle lists
            values = value if isinstance(value, list) else [value]

            for item in values:
                if not isinstance(item, dict):
                    continue

                # Check if this property has a nested ClassSpec with an IRI (named class)
                if prop_spec.nested and prop_spec.nested.iri:
                    # Named class needs an ID
                    if "id" not in item:
                        # Use the namespace from the nested class IRI without adding separator
                        # new_iri() will add the uuid automatically
                        nested_iri = prop_spec.nested.iri
                        item["id"] = self.node_naming_schema(nested_iri)

                    # Recurse into nested object
                    self._inject_missing_ids(item, prop_spec.nested)
                elif prop_spec.nested and not prop_spec.nested.iri:
                    # Anonymous/blank node - no ID needed, but recurse for deeper nesting
                    self._inject_missing_ids(item, prop_spec.nested)

    # ------------------------------------------------------------------
    # Loader / materialization
    # ------------------------------------------------------------------

    def loader(
        self,
        node: Node,
    ) -> Dict[str, Any]:
        """
        Delegate loading to the configured loader.

        Loader must:
        - respect node.class_spec
        - return JSON-compatible dict
        """
        self.logger.debug("Loading data for %s", node.id)
        return self._loader(node)

    def create_node_instance(
        self,
        node: Node,
    ) -> pd.BaseModel:
        """
        Materialize a Pydantic instance from node.data and node.class_spec.
        """
        if node.class_spec is None:
            raise ValueError("Cannot create instance without ClassSpec")

        if node.data is None:
            raise ValueError("Cannot create instance without loaded data")

        model_cls = node.class_spec.to_pydantic_model()  # type: ignore[attr-defined]
        return model_cls.model_validate(node.data)
