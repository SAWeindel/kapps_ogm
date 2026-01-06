from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import logging
import pydantic as pd
from pydantic import ValidationError

from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.node import Node
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.mapping.property_spec import PropertySpec
from circular_factory_ogm.utils.blank_instance import (
    _create_blank_instance,
    _blank_instance_from_class_spec,
    _blank_value_for_property,
)
from circular_factory_ogm.utils.loader_strategy import LoaderStrategy


class OGM:
    """
    TODO: Docstring for OGM
    """

    def __init__(
        self,
        *,
        db: GraphDB,
        loader: Optional[LoaderStrategy] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Args:
            db: GraphDB interface

            loader: LoaderStrategy that takes an IRI and returns property chains for selective instance loading. if not specified, property chains need to be provided at fetch/creation time.
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
        property_chains = (
            property_chains
            if property_chains is not None
            else self._loader.expand(class_iri) if self._loader else None
        )
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
    # Creating new instances
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        class_iri: IRI,
        data: dict,
        property_chains: Optional[list[list[IRI]]] = None,
        instance_iri: Optional[IRI] = None,
        node_naming_schema: Optional[Callable[[], str]] = None,
        persist: bool = True,
    ) -> Node:
        """
        Create a new Node instance with given data.
        Args:
            class_iri: IRI of the class to instantiate
            data: Data dictionary for the instance (must conform to class_spec)
            property_chains: Optional property chains for selective hydration
            instance_iri: Optional IRI for the new instance (if not provided, a new one will be generated)
            node_naming_schema: Optional callable to generate node names/IRIs
            persist: Whether to persist the new instance to the graph database
        Returns:
            Node representing the newly created instance

        This is the primary entry point for:
        - REST POST
        - API writes
        - JSON import
        """
        property_chains = (
            property_chains
            if property_chains is not None
            else self._loader.expand(class_iri) if self._loader else None
        )

        class_spec = self.get_class_spec(
            class_iri=class_iri,
            property_chains=property_chains,
        )

        model_cls = class_spec.to_pydantic_model()

        try:
            instance = model_cls.model_validate(data)
        except ValidationError as e:
            self.logger.error("Data validation error for class %s: %s", class_iri, e)
            raise

        node_id = (
            instance_iri or IRI(f"http://example.org/instances/{node_naming_schema()}")
            if node_naming_schema
            else IRI(f"http://example.org/instances/{class_iri.lined}-generated")
        )

        node = Node(
            id=node_id,
            class_spec=class_spec,
            data=data,
            instance=instance,
            ogm=self,
        )

        if persist:
            pass  # TODO: implement persistence logic here

        return node

    def create_blank_instance(
        self,
        *,
        class_iri: IRI,
        property_chains: Optional[list[list[IRI]]] = None,
        instance_iri: Optional[IRI] = None,
    ) -> pd.BaseModel:
        """
        Create a blank pydantic instance for a given class IRI, able to serve as a template for data population.

        Args:
            class_iri: IRI of the class to instantiate
            property_chains: Optional property chains for selective hydration
            instance_iri: Optional IRI for the new instance
        Returns:
            pydantic BaseModel representing the blank instance
        """
        property_chains = (
            property_chains
            if property_chains is not None
            else self._loader.expand(class_iri) if self._loader else None
        )
        return _create_blank_instance(
            ogm=self,
            instance_iri=instance_iri or IRI("urn:uuid:generated-blank-instance"),
            class_iri=class_iri,
            property_chains=property_chains,
        )

    # ------------------------------------------------------------------
    # Fetching existing instances (Read)
    # ------------------------------------------------------------------

    def _get_property_data(
        self,
        property_spec: PropertySpec,
        instance_iri: IRI,
        property_chain: Optional[list[IRI]] = None,
        
    ) -> Optional[list[Any]]:
        """
        Helper method to fetch property data for a given property spec and instance IRI.
        """
        data = []

        query_result = self.db.triples_get(sub=instance_iri, pred=property_spec.iri)
        if query_result is None:
            return None
        else:
            if (
                property_spec.value_kind == "data"
            ):  # this is a datatype property without further chaining => cannot be expanded
                data.append([str(obj) for subj, pred, obj in query_result])

            elif property_spec.value_kind == "object":

                if (
                    property_spec.nested is not None
                ):  # recursively fetch nested objects according to nested class spec
                    nested_class_spec = property_spec.nested
                    for subj, pred, obj in query_result:
                        data.append(
                            self.fetch(
                                instance_iri=obj,
                                class_spec=nested_class_spec,
                                
                            )
                        )
                else:  # fetch as references only
                    for subj, pred, obj in query_result:
                        data.append(
                            self.fetch(
                                instance_iri=obj,
                                as_reference=True,
                            ).data
                        )
            elif (
                property_spec.value_kind == "complex"
            ):  # this is a property that has a range of complex type/bnode (ie due to union or intersection)

                nested_dict = {}
                query = f"""
                    SELECT ?property ?value
                    WHERE {{
                        <{instance_iri}> <{property_spec.iri}> ?intermediate .
                        ?intermediate ?property ?value .
                    }}
                """
                nested_query_result = (
                    self.db.query(query).get("results", {}).get("bindings", [])
                )
                for binding in nested_query_result:
                    prop_iri = IRI(binding["property"]["value"])
                    value = binding["value"]["value"]
                    if prop_iri not in nested_dict:
                        nested_dict[prop_iri] = []
                    nested_dict[prop_iri].append(value)
                data.append(nested_dict)

            else:
                raise ValueError(
                    f"Unknown value_kind {property_spec.value_kind} for property {property_spec.iri}"
                )

            return data
    
    

    def fetch(
        self,
        *,
        instance_iri: IRI,
        property_chains: Optional[list[list[IRI]]] = None,
        class_spec: Optional[ClassSpec] = None,
        as_reference: bool = False,
        materialize: bool = False,
        
    ) -> Node:
        """
        Fetch an existing RDF instance from the database and return a Node for that instance.

        Args:
            instance_iri: IRI of the instance to fetch
            property_chains: Optional property chains for selective hydration
            as_reference: If True, fetch only the IRI without loading properties

        Returns:
            Node representing the fetched instance
        """
        property_chains = (
            property_chains
            if property_chains is not None
            else self._loader.expand(instance_iri) if self._loader else None
        )
        class_iri = self.db.owl_get_classes_of_individual(instance_iri)[0]
        if class_spec is None:
            class_spec = self.get_class_spec(
                class_iri=class_iri,
                property_chains=property_chains,
            )
        else:
            class_spec = class_spec
        data = {}
        data["id"] = str(instance_iri)  # every node must have an id at minimum

        if not as_reference:
            # Full fetch according to class spec (already filtered by property chains)
            for prop, prop_spec in class_spec.properties.items():
                prop_data = self._get_property_data(
                    prop_spec, instance_iri=instance_iri, 
                )
                # Only include properties that have actual data (not None or empty list)
                if prop_data:  # This excludes both None and []
                    data[prop] = prop_data
        else:
            # As reference: keep only the id
            pass
        
        
            

        node = Node(
            id=instance_iri,
            class_spec=class_spec,
            data=data,
            instance=None,  # instance can be materialized later if needed
            ogm=self,
        )

        if materialize:
            node.materialize()
        return node

    def _fetch_from_node(self, node: Node) -> dict:
        """
        Populate a reference node with data from the graph database.

        Internal orchestration method powering node.load_data() for selective
        lazy loading. Respects node.class_spec property chains to hydrate only
        requested fields.

        Args:
            node: Node with id and class_spec, but no data yet

        Returns:
            Dict[str, Any]: JSON-compatible data matching node.class_spec structure
        """
        if node.id is None:
            raise ValueError("Cannot fetch data for a node without an id")

        property_chains = getattr(node.class_spec, "property_chains", None)
        fetched_node = self.fetch(
            instance_iri=node.id,
            property_chains=property_chains,
            as_reference=False,
            materialize=False,
        )

        return fetched_node.data or {}

    # ------------------------------------------------------------------
    # updating existing instances
    # ------------------------------------------------------------------

    def commit(
        self,
        *,
        updated_node: Node,
        previous_node: Optional[Node] = None,
    ) -> None:
        """
        Commit changes of an existing Node instance to the graph database.

        Args:
            node: Node instance to commit
        """
        raise NotImplementedError("Commit method is not yet implemented.")

    # ------------------------------------------------------------------
    # deletion of instances
    # ------------------------------------------------------------------

    def delete(
        self,
        *,
        node: Node,
    ) -> bool:
        """
        Delete an existing Node instance from the graph database.

        Args:
            node: Node instance to delete
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        raise NotImplementedError("Delete method is not yet implemented.")
        return False
