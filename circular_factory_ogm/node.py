from __future__ import annotations
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    Optional,
    Type,
    TypeVar,
    Union,
    TypeAlias,
)
from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

from graph_db_interface import IRI, GraphDB

if TYPE_CHECKING:
    from ogm import OGM

T = TypeVar("T", bound=BaseModel)
Loader: TypeAlias = Callable[[IRI, GraphDB], Union[Dict[str, Any], T]]


class Node(Generic[T]):
    """
       A generic Node class acting as a container for Pydantic models generated from RDF data.

       The Node class contains a reference to the IRI of the RDF resource and may contain
    lazy loading from a triplestore.

       Can be created from:
         - A IRI only (lazy reference)
         - A IRI with partial data (lazy reference with cached data)
         - A Pydantic model instance directly (already loaded)

       The .load(loader) method loads the full object if not already loaded using loader(id) -> dict|T.
    """

    # __slots__ = ("id", "_data", "instance", "model_cls", "_ogm")

    def __init__(
        self,
        model_cls: Optional[Type[T]] = None,
        id: Optional[Union[str, IRI]] = None,
        data: Optional[Dict[str, Any]] = None,
        instance: Optional[T] = None,
        ogm: Optional[OGM] = None,
    ):
        """
        Initialize a Node instance.

        Args:
            model_cls: Optional Pydantic model class
            id: Optional IRI of the RDF resource
            data: Optional partial data dict for the model
            instance: Optional already-loaded Pydantic model instance
            ogm: Optional OGM instance for builder and loader functions

        Raises:
            ValueError: If none of model_cls, id, or instance is provided
            TypeError: If instance is not of type model_cls when both are provided
            ValueError: If id, model_cls, and instance have inconsistent ids when multiple are provided
            ValueError: If model_cls cannot be determined
        """
        if model_cls is None and id is None and instance is None:
            raise ValueError(
                "At least one of model_cls, id, or instance must be provided"
            )

        if id is not None and not isinstance(id, IRI):
            id = IRI(id)

        if instance is not None and not hasattr(instance, "id"):
            raise ValueError("Instance must have a 'id' attribute")

        if (
            instance is not None
            and model_cls is not None
            and not isinstance(instance, model_cls)
        ):
            raise TypeError("instance must be of type model_cls")

        if id is not None and instance is not None and instance.id != id:
            raise ValueError("Instance URI does not match provided IRI")

        self.data = data or None
        self.instance: Optional[T] = instance
        self.ogm = ogm

        # Assign model class and id
        # 1. If model_cls is provided, use it
        # 2. If instance is provided, use it
        # 3. Use provided type cache if it has the URI
        # 4. Check OGM's type cache if it has the URI
        # 5. Build a new model class based on the URI and cache it in OGM
        if model_cls is not None:
            self.model = model_cls
            self.id = model_cls.model_fields.get("id").default
        elif instance is not None:
            self.model = type(instance)
            self.id = instance.id
        elif ogm and id in ogm.type_cache:
            self.model = ogm.type_cache[id]
            self.id = id
        elif id is not None:
            self.model = None
            self.id = id
        else:
            raise ValueError("Unable to determine model class for Node")

    @property
    def is_loaded(self) -> bool:
        """Check if the model instance has been loaded."""
        return self.instance is not None

    def build(self) -> Type[T]:
        """
        Build/generate a Pydantic model class from the URI.

        If an OGM is attached, uses the OGM's builder function.
        Otherwise raises NotImplementedError.

        Returns:
            A Pydantic model class (Type[T])

        Raises:
            NotImplementedError: If no OGM is attached or builder is not implemented
        """
        if self.model is not None:
            return self.model

        if self.ogm is None:
            raise NotImplementedError(
                "Dynamic model building not yet implemented. "
                "Please provide model_cls explicitly or attach an OGM with a builder."
            )

        self.model = self.ogm.builder(self)

        return self.model

    def load(self) -> T:
        """
        Synchronously load the referenced object using the loader callable, generating an instance.

        The loader is called as loader(id) and must return a dict matching the object type.
        If already loaded, returns the cached instance without calling the loader.

        Args:
            loader: Callable that takes a IRI and returns dict or model instance

        Returns:
            The loaded model instance

        Raises:
            ValueError: If no URI and no data available to load from, or if model_cls not set
        """
        if self.instance is not None:
            return self.instance

        if self.data is None:
            self.data = self.ogm.loader(self)

        self.instance = self.ogm.create_node_instance(self)
        return self.instance

    def try_load(self, loader: Loader, default: Optional[T] = None) -> Optional[T]:
        """
        Like load but returns default instead of raising on error.

        Args:
            loader: Callable that takes a IRI and returns dict matching the object type
            default: Value to return if loading fails

        Returns:
            The loaded model instance or the default value
        """
        try:
            return self.load(loader)
        except Exception:
            return default

    def __repr__(self) -> str:
        if self.instance:
            return f"Node<instance {self.instance!r}>"
        elif self.model:
            return f"Node{self.model!r}"
        else:
            return f"Node<ref {self.id!r}, data: {bool(self.data)}>"

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
