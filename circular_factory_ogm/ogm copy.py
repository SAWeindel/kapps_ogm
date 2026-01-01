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


class OGM:
    """
    TODO: Docstring for OGM
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
        class_spec = self.get_class_spec(
            class_iri=class_iri,
            property_chains=property_chains,
        )

        model_cls = class_spec.to_pydantic_model()

        try:
            instance = model_cls.model_validate(data)
        except ValidationError as e:
            self.logger.error(
                "Data validation error for class %s: %s", class_iri, e
            )
            raise

        node_id = (
            instance_iri
            or IRI(f"http://example.org/instances/{node_naming_schema()}")
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
        return _create_blank_instance(
            ogm=self,
            instance_iri=instance_iri or IRI("urn:uuid:generated-blank-instance"),
            class_iri=class_iri,
            property_chains=property_chains,
        )
    
    
    # ------------------------------------------------------------------
    # Fetching existing instances (Read)
    # ------------------------------------------------------------------

    def fetch(
        self,
        *,
        instance_iri: IRI,
        property_chains: Optional[list[list[IRI]]] = None,
    ) -> Node:
        """
        Fetch an existing RDF instance from the database and return a Node for that instance.
        
        Args:
            instance_iri: IRI of the instance to fetch
            property_chains: Optional property chains for selective hydration
        
        Returns:
            Node representing the fetched instance
        """
        raise NotImplementedError("Fetch method is not yet implemented.")
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
        raise NotImplementedError("Commit method is not yet implemented."
       
        )
        
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
    
    
        
    
    

    
    
    
    

    

