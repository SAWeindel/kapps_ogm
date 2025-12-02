from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type
from pydantic import BaseModel

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
        builder_func: Optional[Callable[[IRI, GraphDB], Type[BaseModel]]] = None,
    ):
        """
        Initialize the OGM.

        Args:
            db: GraphDB interface instance
            loader_func: Optional custom loader function (id, db) -> dict
            builder_func: Optional custom builder function (id, db) -> Type[BaseModel]
        """
        self.db = db
        self.type_cache: Dict[IRI, Type[BaseModel]] = {}
        self._loader_func = loader_func or self._default_loader
        self._builder_func = builder_func or self._default_builder

    def _default_loader(self, id: IRI, db: GraphDB) -> Dict[str, Any]:
        """
        Default loader stub.

        Should query RDF store and return a dict of predicate/object pairs.
        """
        raise NotImplementedError(
            "Default loader not implemented. Provide loader_func or implement _default_loader."
        )

    def _default_builder(self, id: IRI, db: GraphDB) -> Type[BaseModel]:
        """
        Default builder stub for dynamic Pydantic model generation.

        This should query the RDF type/schema and generate a Pydantic model.
        Currently raises NotImplementedError.
        """
        raise NotImplementedError(
            "Dynamic model building not yet implemented. "
            "Use set_type() to register model classes or provide a custom builder_func."
        )

    def loader(self, id: IRI) -> Dict[str, Any]:
        """
        Partial loader function that uses the OGM's database connection.

        This can be passed to Node.load() method.
        """
        return self._loader_func(id, self.db)

    def builder(self, id: IRI) -> Type[BaseModel]:
        """
        Partial builder function that uses the OGM's database connection.

        This is used internally when Node._build() is called.
        """
        return self._builder_func(id, self.db)

    def set_type(self, id: IRI, model_cls: Type[BaseModel]) -> None:
        """
        Register a Pydantic model class for a specific URI in the type cache.

        Args:
            id: The URI to associate with the model class
            model_cls: The Pydantic model class
        """
        self.type_cache[id] = model_cls

    def get_type(self, id: IRI) -> Optional[Type[BaseModel]]:
        """
        Retrieve a Pydantic model class from the type cache.

        Args:
            id: The URI to look up

        Returns:
            The cached model class or None if not found
        """
        return self.type_cache.get(id)

    def create_node(
        self,
        model_cls: Optional[Type[BaseModel]] = None,
        id: Optional[IRI] = None,
        data: Optional[Dict[str, Any]] = None,
        instance: Optional[BaseModel] = None,
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
        return Node(
            model_cls=model_cls,
            id=id,
            data=data,
            instance=instance,
            type_cache=self.type_cache,
            ogm=self,
        )
