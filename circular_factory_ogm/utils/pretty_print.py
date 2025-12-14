from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from circular_factory_ogm.builders.mapping.property_spec import PropertySpec
    from circular_factory_ogm.builders.mapping.class_spec import ClassSpec


def property_spec_to_string(prop_spec: "PropertySpec", indent: int = 0) -> str:
    """
    Recursively converts a PropertySpec (with nested ClassSpec) into a formatted string.
    """
    ind = "  " * indent
    lines = [
        f"{ind}PropertySpec(",
        f"{ind}  iri={prop_spec.iri}",
        f"{ind}  value_kind={prop_spec.value_kind}",
        f"{ind}  python_range_type={prop_spec.python_range_type}",
        f"{ind}  required={prop_spec.required}",
        f"{ind}  min_count={prop_spec.min_count}",
        f"{ind}  max_count={prop_spec.max_count}",
    ]

    if prop_spec.nested:
        nested = prop_spec.nested
        lines.append(f"{ind}  nested=ClassSpec(")
        lines.append(f"{ind}    iri={nested.iri}")
        if hasattr(nested, "label") and nested.label:
            lines.append(f"{ind}    label={nested.label}")
        lines.append(f"{ind}    properties={{")
        for k, v in nested.properties.items():
            lines.append(f"{ind}      {k}:")
            lines.append(property_spec_to_string(v, indent=indent + 3))
        lines.append(f"{ind}    }}")
        if hasattr(nested, "metadata") and nested.metadata:
            lines.append(f"{ind}    metadata={nested.metadata}")
        lines.append(f"{ind}  )")
    else:
        lines.append(f"{ind}  nested=None")

    lines.append(f"{ind})")
    return "\n".join(lines)


def class_spec_to_string(class_spec, indent: int = 0) -> str:
    """
    Recursively converts a ClassSpec (with nested PropertySpec objects) into a formatted string.
    """
    ind = "  " * indent
    lines = [
        f"{ind}ClassSpec(",
        f"{ind}  iri={class_spec.iri}",
    ]

    if hasattr(class_spec, "label") and class_spec.label:
        lines.append(f"{ind}  label={class_spec.label}")

    if hasattr(class_spec, "types") and class_spec.types:
        lines.append(f"{ind}  types={class_spec.types}")

    if hasattr(class_spec, "superclasses") and class_spec.superclasses:
        lines.append(f"{ind}  superclasses={class_spec.superclasses}")

    lines.append(f"{ind}  properties={{")
    for prop_iri, prop_spec in class_spec.properties.items():
        lines.append(f"{ind}    {prop_iri}:")
        # Use the PropertySpec printer for nested properties
        lines.append(property_spec_to_string(prop_spec, indent=indent + 3))

    lines.append(f"{ind}  }}")

    if hasattr(class_spec, "metadata") and class_spec.metadata:
        lines.append(f"{ind}  metadata={class_spec.metadata}")

    lines.append(f"{ind})")
    return "\n".join(lines)
