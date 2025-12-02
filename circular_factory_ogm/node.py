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
)
from pydantic import BaseModel

from graph_db_interface import IRI

if TYPE_CHECKING:
    from ogm import OGM

T = TypeVar("T", bound=BaseModel)
Loader = Callable[[IRI], Union[Dict[str, Any], T]]


class Node(Generic[T]):
    """
    A generic Node class acting as a container for Pydantic models generated from RDF data.

    The Node class contains a reference to the IRI of the RDF resource and may contain
    a Pydantic model instance if loaded. It supports lazy loading from a triplestore.

    Can be created from:
      - A IRI only (lazy reference)
      - A IRI with partial data (lazy reference with cached data)
      - A Pydantic model instance directly (already loaded)

    The .load(loader) method loads the full object if not already loaded using loader(id) -> dict|T.
    """

    # __slots__ = ("id", "_data", "instance", "_model_cls", "_ogm")

    def __init__(
        self,
        model_cls: Optional[Type[T]] = None,
        id: Optional[IRI] = None,
        data: Optional[Dict[str, Any]] = None,
        instance: Optional[T] = None,
        type_cache: Optional[Dict[IRI, Type[BaseModel]]] = None,
        ogm: Optional[OGM] = None,
    ):
        """
        Initialize a Node instance.

        Args:
            model_cls: Optional Pydantic model class
            id: Optional IRI of the RDF resource
            data: Optional partial data dict for the model
            instance: Optional already-loaded Pydantic model instance
            type_cache: Optional type cache to look up model classes by URI
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

        if instance is not None and not hasattr(instance, "id"):
            raise ValueError("Instance must have a 'id' attribute")

        if model_cls is not None and model_cls.model_fields.get("id") is None:
            raise ValueError("Model class must have a 'id' attribute")

        if (
            instance is not None
            and model_cls is not None
            and not isinstance(instance, model_cls)
        ):
            raise TypeError("instance must be of type model_cls")

        if id is not None and instance is not None and instance.id != id:
            raise ValueError("Instance URI does not match provided IRI")

        if (
            id is not None
            and model_cls is not None
            and model_cls.model_fields["id"].default != id
        ):
            raise ValueError(
                "Model class 'id' attribute default does not match provided IRI"
            )

        self._data = data
        self.instance: Optional[T] = instance
        self._ogm = ogm

        # Assign model class and id
        # 1. If model_cls is provided, use it
        # 2. If instance is provided, use it
        # 3. Use provided type cache if it has the URI
        # 4. Check OGM's type cache if it has the URI
        # 5. Build a new model class based on the URI and cache it in OGM
        if model_cls is not None:
            self._model_cls = model_cls
            self.id = model_cls.model_fields.get("id")
        elif instance is not None:
            self._model_cls = type(instance)
            self.id = instance.id
        elif type_cache and id in type_cache:
            self._model_cls = type_cache[id]
            self.id = id
        elif ogm and id in ogm.type_cache:
            self._model_cls = ogm.type_cache[id]
            self.id = id
        elif id is not None:
            self._model_cls = self._build(id)
            if ogm is not None:
                ogm.set_type(id, self._model_cls)
            self.id = id
        else:
            raise ValueError("Unable to determine model class for Node")

    def _build(self, id: IRI) -> Type[T]:
        """
        Build/generate a Pydantic model class from the URI.

        If an OGM is attached, uses the OGM's builder function.
        Otherwise raises NotImplementedError.

        Args:
            id: The IRI to build a model class for

        Returns:
            A Pydantic model class (Type[T])

        Raises:
            NotImplementedError: If no OGM is attached or builder is not implemented
        """
        if self._ogm is None:
            raise NotImplementedError(
                "Dynamic model building not yet implemented. "
                "Please provide model_cls explicitly or attach an OGM with a builder."
            )

        return self._ogm.builder(id)

    @property
    def is_loaded(self) -> bool:
        """Check if the model instance has been loaded."""
        return self.instance is not None

    def type(self) -> Type[T]:
        """
        Return the model class instead of the Node class itself.

        Returns:
            The Pydantic model class (Type[T])

        Raises:
            ValueError: If model_cls is not set
        """
        if self._model_cls is None:
            raise ValueError(
                "Model class not set. Provide model_cls, instance, or id to build the type."
            )
        return self._model_cls

    def set_loader_result(self, result: Union[Dict[str, Any], T]) -> T:
        """Helper to turn loader result into a model instance and cache it."""
        if self._model_cls is None:
            raise ValueError(
                "Model class must be set before loading. Call build() first."
            )

        if isinstance(result, self._model_cls):
            self.instance = result
            return self.instance

        if isinstance(result, dict):
            if self.id and "id" not in result:
                result = {**result, "id": str(self.id)}
            self.instance = self._model_cls.model_validate(result)
            return self.instance

        raise TypeError("loader must return a dict or a model instance")

    def load(self, loader: Loader, /) -> T:
        """
        Synchronously load the referenced object using the loader callable.

        The loader is called as loader(id) and must return either a dict or an instance.
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

        if self._model_cls is None:
            raise ValueError(
                "Model class must be set before loading. Call build() first."
            )

        if self.id is not None:
            result = loader(self.id)
            return self.set_loader_result(result)

        if self._data is not None:
            self.instance = self._model_cls.model_validate(self._data)
            return self.instance

        raise ValueError("No URI and no data to load from.")

    def try_load(self, loader: Loader, default: Optional[T] = None) -> Optional[T]:
        """
        Like load but returns default instead of raising on error.

        Args:
            loader: Callable that takes a IRI and returns dict or model instance
            default: Value to return if loading fails

        Returns:
            The loaded model instance or the default value
        """
        try:
            return self.load(loader)
        except Exception:
            return default

    # def __getattr__(self, item: str) -> Any:
    #     """
    #     Allow accessing attributes of the wrapped object directly.

    #     For example: node.some_field instead of node.instance.some_field
    #     """
    #     if item.startswith("_"):
    #         raise AttributeError(item)

    #     if not self.instance:
    #         raise AttributeError(
    #             f"Attribute '{item}' requested but target not loaded. "
    #             "Call .load(loader) first or access via .instance"
    #         )

    #     return getattr(self.instance, item)

    def __repr__(self) -> str:
        if self.instance:
            return f"<Node loaded {self.instance!r}>"
        return f"<Node id='{self.id}' data={bool(self._data)}>"
