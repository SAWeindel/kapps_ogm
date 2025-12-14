"""Mapping module for OWL class and property specifications."""

from .class_spec import (
    ClassSpec,
    classify_outgoing_properties,
)
from .property_spec import (
    PropertySpec,
    process_literal_property,
    process_class_property,
    process_complex_property,
)

__all__ = [
    "ClassSpec",
    "PropertySpec",
    "classify_outgoing_properties",
    "process_literal_property",
    "process_class_property",
    "process_complex_property",
]
