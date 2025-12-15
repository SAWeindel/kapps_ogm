from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import logging
import pydantic as pd

from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.node import Node
from circular_factory_ogm.builders.mapping.class_spec import ClassSpec, specify
from circular_factory_ogm.builders.mapping.property_spec import PropertySpec
from circular_factory_ogm.utils.blank_instance import (
    _create_blank_instance,
    _blank_instance_from_class_spec,
    _blank_value_for_property,
)


class OGM:
    """
    Object–Graph Mapper coordinating:

    - Schema resolution (ClassSpec)
    - Instance loading from RDF
    - Pydantic model materialization
    - Persistence hooks (future)

    OGM is orchestration-only:
    - no node registry
    - no implicit global state
    - no hard-coded expansion rules
    """

    def __init__(
        self,
        *,
        db: GraphDB,
        loader: Callable[[Node], Dict[str, Any]],
        logger: Optional[logging.Logger] = None,
    ):
        """
        Args:
            db: GraphDB interface
            loader: Callable that loads instance data respecting Node.class_spec
        """
        self.db = db
        self._loader = loader
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

        spec = specify(
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
        Fetch an existing RDF instance and return a Node.

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
    ) -> IRI:
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
