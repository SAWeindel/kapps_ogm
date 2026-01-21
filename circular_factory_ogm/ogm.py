from __future__ import annotations

from typing import Any, Callable, Optional
import logging
import pydantic as pd

from graph_db_interface import GraphDB, IRI
from graph_db_interface.utils.types import GraphNameLike

from circular_factory_ogm.node.core import Node
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.mapping.property_spec import PropertySpec, PropertyValueKind
from circular_factory_ogm.utils.blank_instance import _create_blank_instance
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
        naming_schema: Optional[Callable[[], str]] = None,
    ):
        """
        Args:
            db: GraphDB interface

            loader: LoaderStrategy that takes an IRI and returns property chains for selective instance loading. if not specified, property chains need to be provided at fetch/creation time.
        """
        self.db = db
        self._loader = loader
        self._naming_schema = naming_schema
        self.logger = logger or logging.getLogger("cf_ogm")
        self.logger.setLevel(logging.DEBUG)

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
        persist: bool = True,
        named_graph: Optional[GraphNameLike] = None,
    ) -> Node:
        """
        Create a new Node instance with given data.
        Args:
            class_iri: IRI of the class to instantiate
            data: Data dictionary for the instance (must conform to class_spec)
            property_chains: Optional property chains for selective hydration
            instance_iri: Optional IRI for the new instance (if not provided, a new one will be generated)
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

        node = Node(
            id=instance_iri,
            class_spec=class_spec,
            data=data,
            ogm=self,
        )

        if node.has_data:
            node.materialize()

            if persist:
                triples = node.to_triples()
                self.db.triples_add(triples, named_graph=named_graph)

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

    def _assign_id(self, node: Node) -> None:
        if node.class_spec is None:
            raise ValueError(f"Node {node} has no ClassSpec, cannot assign id.")
        model_iri = getattr(node.class_spec, "iri", None)
        if model_iri:
            instance_id = self.db.new_iri(base=model_iri, schema=self._naming_schema)
        else:
            instance_id = self.db.new_blank_id()
        node.id = instance_id

    # ------------------------------------------------------------------
    # Fetching existing instances (Read)
    # ------------------------------------------------------------------

    def _get_property_data(
        self,
        property_spec: PropertySpec,
        instance_iri: IRI,
        property_chain: Optional[list[IRI]] = None,
        materialize: bool = False,
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
                property_spec.value_kind is PropertyValueKind.LITERAL
            ):  # this is a datatype property without further chaining => cannot be expanded
                data.extend([obj for subj, pred, obj in query_result])

            elif property_spec.value_kind is PropertyValueKind.OBJECT:
                # if there is a property chain given, and we are at the first element of it, we need to expand further
                if property_chain is not None:
                    if property_chain[0] == property_spec.iri:
                        # we remove the first element and pass the rest down, call fetch recursively
                        remaining_chain = property_chain[1:]
                        for subj, pred, obj in query_result:
                            nested_instance = self.fetch(
                                instance_iri=obj,
                                class_spec=property_spec.nested,
                                property_chains=(
                                    [remaining_chain]
                                    if len(remaining_chain) > 0
                                    else None
                                ),
                                as_reference=False,
                                materialize=materialize,
                            )
                            data.append(nested_instance)
                else:  # no property chain given, we treat the object just as reference
                    nested_instance = self.fetch(
                        instance_iri=obj,
                        class_spec=property_spec.nested,
                        as_reference=True,
                    )
                    data.append(nested_instance)

            elif (
                property_spec.value_kind is PropertyValueKind.COMPLEX
            ):  # this is a property that has a range of complex type/bnode (ie due to union or intersection)

                nested_dict = {}
                query = f"""
                    SELECT ?property ?value
                    FROM <http://www.ontotext.com/explicit>
                    WHERE {{
                        <{instance_iri}> <{property_spec.iri}> ?intermediate .
                        ?intermediate ?property ?value .
                    }}
                """
                nested_query_result = (
                    self.db.query(query, convert_bindings=True)
                    .get("results", {})
                    .get("bindings", [])
                )
                for binding in nested_query_result:
                    prop_iri = binding["property"]
                    value = binding["value"]
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
        class_spec: Optional[ClassSpec] = None,
        property_chains: Optional[list[list[IRI]]] = None,
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
        if property_chains is None and self._loader is not None:
            property_chains = self._loader.expand(instance_iri)

        if class_spec is None:
            class_iri = self.db.owl_get_classes_of_individual(instance_iri)[0]
            class_spec = self.get_class_spec(
                class_iri=class_iri,
                property_chains=property_chains,
            )

        data = {}
        data["id"] = instance_iri  # every node must have an id at minimum

        if not as_reference:
            # Full fetch according to class spec (already filtered by property chains)
            for prop, prop_spec in class_spec.properties.items():
                if property_chains is not None and len(property_chains) > 0:
                    for chain in property_chains:
                        if len(chain) > 0 and chain[0] == prop_spec.iri:
                            # pass the rest of the chain for nested fetching
                            data[prop] = self._get_property_data(
                                prop_spec,
                                instance_iri=instance_iri,
                                property_chain=chain,
                                materialize=materialize,
                            )
                else:
                    data[prop] = self._get_property_data(
                        prop_spec, instance_iri=instance_iri, materialize=materialize
                    )
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

    # ------------------------------------------------------------------
    # updating existing instances
    # ------------------------------------------------------------------

    def commit(
        self,
        *,
        staged_node: Optional[Node] = None,
        staged_instance: Optional[pd.BaseModel] = None,
        node_to_commit_to: Optional[Node] = None,
        instance_to_commit_to: Optional[pd.BaseModel] = None,
    ) -> bool:

        if staged_node is None and staged_instance is None:
            raise ValueError("Either staged_node or staged_instance must be provided.")
        if node_to_commit_to is None and instance_to_commit_to is None:
            self.logger.warning(
                "No target node or instance provided to commit to; use create instead."
            )
            return False

        if staged_node is None and staged_instance is not None:
            staged_node = Node(
                id=getattr(staged_instance, "id", None),
                class_spec=ClassSpec.specify_from_model(
                    model_cls=type(staged_instance),
                    ogm=self,
                ),
                data=staged_instance.model_dump(),
                ogm=self,
            )

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
