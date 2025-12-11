from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type, Union
import pydantic as pd
import logging
from rdflib import BNode

from aas_middleware.model.core import Identifiable

from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.node import Node


class OGM:
    """
    RDF Object-Graph Mapper (OGM) for managing Node creation and RDF-to-Pydantic mapping.

    Centrally manages:
    - Database interface connection
    - Type cache for Pydantic model classes
    - Loader function for fetching RDF data
    - Builder function for dynamic model generation
    """

    def __init__(
        self,
        db: GraphDB,
        loader_func: Optional[Callable[[IRI, GraphDB], Dict[str, Any]]] = None,
        builder_func: Optional[Callable[[IRI, GraphDB], Type[pd.BaseModel]]] = None,
        expansion_blacklist: Optional[set[IRI]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the OGM.

        Args:
            db: GraphDB interface instance
            loader_func: Optional custom loader function (id, db) -> dict
            builder_func: Optional custom builder function (id, db) -> Type[BaseModel]
        """
        self.db = db
        self.nodes: Dict[IRI, Node] = {}
        self.type_references: set[IRI] = set()
        self.type_cache: Dict[IRI, Type[pd.BaseModel]] = {}
        self._loader_func = loader_func or self._default_loader
        self._builder_func = builder_func or self._default_builder
        self.expansion_blacklist = expansion_blacklist or set()

        self.logger = logger or logging.getLogger("cf_ogm")

    def _default_loader(self, node: Node) -> Dict[str, Any]:
        """
        Default loader stub.

        Should query RDF store and return a dict of predicate/object pairs.
        """
        raise NotImplementedError(
            "Default loader not implemented. Provide loader_func or implement _default_loader."
        )

    def _default_builder(self, node: Node) -> Type[pd.BaseModel]:
        """
        Default builder stub for dynamic Pydantic model generation.

        This should query the RDF type/schema and generate a Pydantic model.
        Currently raises NotImplementedError.
        """
        raise NotImplementedError(
            "Dynamic model building not yet implemented. "
            "Use set_type() to register model classes or provide a custom builder_func."
        )

    def loader(self, node: Node) -> Dict[str, Any]:
        """
        Partial loader function that uses the OGM's database connection.

        This can be passed to Node.load() method.
        """
        return self._loader_func(node)

    def builder(self, node: Node) -> Type[pd.BaseModel]:
        """
        Partial builder function that uses the OGM's database connection.

        This is used internally when Node._build() is called.
        """
        model = self._builder_func(node)
        self.set_type(node.id, model)
        return model

    def set_type(self, id: IRI, model_cls: Type[pd.BaseModel]) -> None:
        """
        Register a Pydantic model class for a specific URI in the type cache.

        Args:
            id: The URI to associate with the model class
            model_cls: The Pydantic model class
        """
        self.type_cache[id] = model_cls

    def get_type(self, id: IRI) -> Optional[Type[pd.BaseModel]]:
        """
        Retrieve a Pydantic model class from the type cache.

        Args:
            id: The URI to look up

        Returns:
            The cached model class or None if not found
        """
        return self.type_cache.get(id)

    def create_reference_type(self, id: IRI):
        type_model = list[f"models['{id.lined}']"]
        self.type_references.add(id)
        self.logger.info(f"Created reference type for {id}")
        return type_model

    def create_resolved_type(
        self,
        id: IRI,
        creation_dict: Dict[IRI, tuple[Type[list[Any]], pd.Field]],
    ) -> Type[Identifiable]:
        type_model = pd.create_model(
            id.lined,
            __base__=Identifiable,
            id=(IRI, id),
            **creation_dict,
        )
        self.type_references.add(id)
        self.type_cache[id] = type_model
        self.logger.info(f"Created resolved type for {id}")
        return type_model

    def create_bnode_type(
        self,
        bnode: BNode,
        creation_dict: Dict[IRI, tuple[Type[list[Any]], pd.Field]],
    ):
        type_model = pd.create_model(
            bnode,
            __base__=pd.BaseModel,
            **creation_dict,
        )
        self.logger.info(f"Created blank node type for {bnode}")
        return type_model

    def create_node(
        self,
        model_cls: Optional[Type[pd.BaseModel]] = None,
        id: Optional[Union[str, IRI]] = None,
        data: Optional[Dict[str, Any]] = None,
        instance: Optional[pd.BaseModel] = None,
    ) -> Node:
        """
        Create a Node with the OGM's type cache and OGM reference.

        Args:
            model_cls: Optional Pydantic model class
            id: Optional IRI
            data: Optional partial data dict
            instance: Optional already-loaded instance

        Returns:
            A new Node instance configured with this OGM's type cache and OGM reference
        """
        if id in self.nodes:
            self.logger.warning(f"Node with id {id} already exists. Overwriting.")

        node = Node[id.lined](
            model_cls=model_cls,
            id=id,
            data=data,
            instance=instance,
            type_cache=self.type_cache,
            ogm=self,
        )

        self.nodes[node.id] = node
        self.logger.info(f"Created node for id {node.id}")
        return node

    def resolve_types(self):
        """
        For all referenced types collected during building, ensure their model
        classes exist in the type cache or are created as reference nodes.
        Resolves all forward references.
        """
        models = {}
        for class_iri in self.type_references:
            if class_iri in self.type_cache:
                model = self.type_cache[class_iri]
                self.logger.info(f"Resolve Types: Found model for {class_iri}")
            else:
                # Referenced node has not been built yet, create an empty reference type
                self.logger.info(f"Resolve Types: Did not find model for {class_iri}")
                model = self.create_resolved_type(id=class_iri, creation_dict={})
            models[class_iri.lined] = model

        for model in models.values():
            model.model_rebuild()
