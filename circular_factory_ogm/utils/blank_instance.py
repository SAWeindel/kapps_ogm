from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING
import pydantic as pd

from graph_db_interface import IRI

from circular_factory_ogm.builders.mapping.class_spec import ClassSpec, specify
from circular_factory_ogm.builders.mapping.property_spec import PropertySpec

if TYPE_CHECKING:
    from circular_factory_ogm.ogm import OGM


def _blank_value_for_property(ogm: "OGM", prop: PropertySpec) -> Any:
    """
    Produce a blank value for a property based on its kind and hydration.
    - data/literal: None
    - object: nested blank instance if hydrated, else None (IRI placeholder)
    - complex: requires hydrated nested ClassSpec; returns nested blank instance
    """
    if prop.value_kind in ("data", "literal"):
        return None

    if prop.value_kind == "object":
        if prop.nested and getattr(prop.nested, "_hydrated", False):
            return _blank_instance_from_class_spec(ogm, class_spec=prop.nested)
        return None  # unresolved object → IRI placeholder

    if prop.value_kind == "complex":
        if not prop.nested or not getattr(prop.nested, "_hydrated", False):
            raise RuntimeError(
                f"Complex property {prop.iri} requires hydrated nested ClassSpec"
            )
        return _blank_instance_from_class_spec(ogm, class_spec=prop.nested)

    raise ValueError(f"Unknown value_kind: {prop.value_kind}")


def _blank_instance_from_class_spec(
    ogm: "OGM",
    *,
    class_spec: ClassSpec,
    instance_iri: Optional[IRI] = None,
) -> pd.BaseModel:
    """Build a blank pydantic instance for a given ClassSpec."""
    model_cls = class_spec.to_pydantic_model()

    data: dict[str, Any] = {}

    # attach id only at root or when explicitly provided
    if instance_iri is not None:
        data["id"] = instance_iri

    for prop in class_spec.properties.values():
        field_name = prop.iri.lined

        # Always lists
        values: list[Any] = []

        # Always add one blank value, regardless of requiredness
        values.append(_blank_value_for_property(ogm, prop))

        data[field_name] = values

    return model_cls.model_construct(**data)


def _create_blank_instance(
    ogm: "OGM",
    *,
    instance_iri: IRI,
    class_iri: IRI,
    property_chains: Optional[list[list[IRI]]] = None,
) -> pd.BaseModel:
    """Resolve schema (respecting property chains) and return a blank instance."""
    class_spec = specify(
        class_iri=class_iri,
        ogm=ogm,
        property_chains=property_chains,
    )

    return _blank_instance_from_class_spec(
        ogm,
        class_spec=class_spec,
        instance_iri=instance_iri,
    )
