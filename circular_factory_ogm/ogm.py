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
from circular_factory_ogm.utils.class_scope import ClassScope


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
        self.loader = loader
        self.naming_schema = naming_schema
        self.logger = logger or logging.getLogger("cf_ogm")
        self.logger.setLevel(logging.DEBUG)

    # ------------------------------------------------------------------
    # Schema orchestration
    # ------------------------------------------------------------------

    def get_class_spec(
        self,
        *,
        class_iri: IRI,
        class_scope: Optional[ClassScope] = None,
        explore_class_properties: bool = True,
    ) -> ClassSpec:
        """
        Resolve a ClassSpec for a given class IRI and ClassScope.

        ClassScope defines selective hydration of nested properties.
        """
        class_scope = class_scope or (
            self.loader.expand(class_iri) if self.loader else None
        )
        self.logger.debug(
            "Resolving ClassSpec for %s (chain=%s, explore_class_properties=%s)",
            class_iri,
            class_scope,
            explore_class_properties,
        )

        spec = ClassSpec.specify(
            class_iri=class_iri,
            ogm=self,
            class_scope=class_scope,
            explore_class_properties=explore_class_properties,
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
        class_scope: Optional[ClassScope] = None,
        instance_iri: Optional[IRI] = None,
        persist: bool = True,
        named_graph: Optional[GraphNameLike] = None,
    ) -> Node:
        """
        Create a new Node instance with given data.
        Args:
            class_iri: IRI of the class to instantiate
            class_scope: ClassScope defining the class and property structure
            data: Data dictionary for the instance (must conform to class_spec)
            instance_iri: Optional IRI for the new instance (if not provided, a new one will be generated)
            persist: Whether to persist the new instance to the graph database
        Returns:
            Node representing the newly created instance

        This is the primary entry point for:
        - REST POST
        - API writes
        - JSON import
        """
        class_scope = class_scope or (
            self.loader.expand(class_iri) if self.loader else None
        )
        class_spec = self.get_class_spec(
            class_iri=class_iri,
            class_scope=class_scope,
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
        class_scope: Optional[ClassScope] = None,
        instance_iri: Optional[IRI] = None,
    ) -> pd.BaseModel:
        """
        Create a blank pydantic instance for a given ClassScope, able to serve as a template for data population.

        Args:
            class_iri: IRI of the class to instantiate
            class_scope: ClassScope defining the class and property structure
            instance_iri: Optional IRI for the new instance
        Returns:
            pydantic BaseModel representing the blank instance
        """
        class_scope = class_scope or (
            self.loader.expand(class_iri) if self.loader else None
        )
        return _create_blank_instance(
            ogm=self,
            instance_iri=instance_iri or IRI("urn:uuid:generated-blank-instance"),
            class_iri=class_iri,
            class_scope=class_scope,
            explore_class_properties=False,
        )

    def _assign_id(self, node: Node) -> None:
        if node.class_spec is None:
            raise ValueError(f"Node {node} has no ClassSpec, cannot assign id.")
        model_iri = getattr(node.class_spec, "iri", None)
        if model_iri:
            instance_id = self.db.new_iri(base=model_iri, schema=self.naming_schema)
        else:
            instance_id = self.db.new_blank_id()
        node.id = instance_id

    # ------------------------------------------------------------------
    # Fetching existing instances (Read)
    # ------------------------------------------------------------------

    def _fetch_literal_property(
        self,
        instance_iri: IRI,
        property_spec: PropertySpec,
    ) -> list[Any]:
        triples = self.db.triples_get(sub=instance_iri, pred=property_spec.iri)
        property_data = [r[2] for r in triples]
        return property_data

    def _fetch_complex_property(
        self,
        instance_iri: IRI,
        property_iri: IRI,
    ) -> list[dict[IRI, list[Any]]]:
        """
        Helper function to fetch complex property data for a given instance and property spec.
        All properties attached to the complex class are fetched.
        """
        # Re-query anonymous node, this time including properties
        query = f"""
                SELECT ?bnode ?property ?value
                FROM <http://www.ontotext.com/explicit>
                WHERE {{
                    <{instance_iri}> <{property_iri}> ?bnode .
                    ?bnode ?property ?value .
                }}
            """
        query_result = (
            self.db.query(query, convert_bindings=True)
            .get("results", {})
            .get("bindings", [])
        )
        if not query_result:
            return []

        property_data_dict = {}
        for binding in query_result:
            bnode = str(binding["bnode"])
            prop_iri = IRI(str(binding["property"]))
            value = binding["value"]

            property_data_dict.setdefault(bnode, {})
            property_data_dict[bnode].setdefault(prop_iri, [])
            property_data_dict[bnode][prop_iri].append(value)

        # [{property_iri: [value1, value2, ...], ...}, ...]
        property_data: list[dict[IRI, list[Any]]] = list(property_data_dict.values())
        return property_data

    def _fetch_object_property(
        self,
        instance_iri: IRI,
        property_spec: PropertySpec,
        nested_class_scope: Optional[ClassScope],
        materialize: bool,
    ) -> list[Node]:
        # Query all instances of the property
        triples = self.db.triples_get(sub=instance_iri, pred=property_spec.iri)
        if not triples:
            return []
        nested_instance_iris = [r[2] for r in triples]

        # Check if this property has a child scope
        # If not, fetch as reference only
        as_reference = nested_class_scope is None

        property_data = []

        for nested_instance_iri in nested_instance_iris:
            nested_instance = self.fetch(
                instance_iri=nested_instance_iri,
                class_spec=property_spec.nested,
                class_scope=nested_class_scope,
                as_reference=as_reference,
                materialize=materialize,
            )
            property_data.append(nested_instance)

        return property_data

    def fetch(
        self,
        *,
        instance_iri: IRI,
        class_spec: Optional[ClassSpec] = None,
        class_scope: Optional[ClassScope] = None,
        as_reference: bool = False,
        materialize: bool = False,
    ) -> Node:
        """
        Fetch an existing RDF instance from the database and return a Node for that instance.

        Args:
            instance_iri: IRI of the instance to fetch
            class_spec: Optional ClassSpec to use for fetching. If not provided, it will be resolved automatically
            class_scope: Optional ClassScope for selective hydration
            as_reference: If True, fetch only the IRI without loading properties
            materialize: If True, materialize the Node's data according to the ClassSpec.
                Ignored if as_reference is True.

        Returns:
            Node representing the fetched instance
        """
        if class_scope is None and self.loader is not None:
            class_scope = self.loader.expand(instance_iri)

        if class_spec is None:
            class_iri = self.db.owl_get_classes_of_individual(instance_iri)[0]
            class_spec = self.get_class_spec(
                class_iri=class_iri,
                class_scope=class_scope,
                explore_class_properties=False,
            )

        data = {}
        if not as_reference:
            # Full fetch according to class spec and class scope
            for prop, property_spec in class_spec.properties.items():
                match property_spec.value_kind:
                    case PropertyValueKind.LITERAL:
                        # Fetch literal values directly
                        property_data = self._fetch_literal_property(
                            instance_iri=instance_iri,
                            property_spec=property_spec,
                        )
                    case PropertyValueKind.COMPLEX:
                        property_data = self._fetch_complex_property(
                            instance_iri=instance_iri,
                            property_iri=property_spec.iri,
                        )
                    case PropertyValueKind.OBJECT:
                        property_data = self._fetch_object_property(
                            instance_iri=instance_iri,
                            property_spec=property_spec,
                            nested_class_scope=class_scope.get(prop, None),
                            materialize=materialize,
                        )
                    case _:
                        raise ValueError(
                            f"Unknown value_kind {property_spec.value_kind} for property {property_spec.iri}"
                        )

                # Ignore if none found
                if property_data:
                    data[prop] = property_data

        node = Node(
            id=instance_iri,
            class_spec=class_spec,
            data=data,
            instance=None,  # instance can be materialized later if needed
            ogm=self,
        )

        if not as_reference and materialize:
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
