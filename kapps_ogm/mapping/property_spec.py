from __future__ import annotations

from typing import Optional, Type, TYPE_CHECKING, Any, Union, Annotated
from enum import Enum
from dataclasses import dataclass
from graph_db_interface import IRI, XSDToPythonTypes
import logging
from pydantic import BeforeValidator, Field, conlist

from kapps_ogm.utils.constants import (
    PROPERTY_TYPES,
    PROPERTY_CHARACTERISTICS,
)
from kapps_ogm.utils.class_scope import ClassScope

if TYPE_CHECKING:
    from kapps_ogm.mapping.class_spec import ClassSpec, ClassHydrationLevel
    from kapps_ogm.ogm import OGM

logger = logging.getLogger("kapps_pspec")
logger.setLevel(logging.INFO)


class PropertyValueKind(Enum):
    LITERAL = "literal"
    OBJECT = "object"
    COMPLEX = "complex"


@dataclass
class PropertySpec:
    iri: IRI
    value_kind: PropertyValueKind  # 'data' or 'object' or 'complex'
    python_range_type: Optional[Type] = None
    min_count: Optional[int] = None
    max_count: Optional[int] = None
    some_from: Optional[Union[IRI, Type]] = None
    all_from: Optional[Union[IRI, Type]] = None
    nested: Optional["ClassSpec"] = None

    @property
    def required(self) -> bool:
        return False  # Under OWA, OWL restrictions never enforce requiredness.

    def to_string(self) -> str:
        from ..utils.pretty_print import format_property_spec

        return format_property_spec(self)

    def to_pydantic_field(self) -> tuple[Any, Any]:
        """Convert this PropertySpec into a Pydantic field with validators."""
        from .class_spec import ClassHydrationLevel

        if not self.value_kind in PropertyValueKind:
            raise ValueError(f"Unknown value_kind: {self.value_kind}")

        logger.debug(
            f"Converting PropertySpec ({self.value_kind.value}) '{self.iri.fragment}' to pydantic field"
        )

        validators = []

        match self.value_kind:
            case PropertyValueKind.LITERAL:
                # If all_from is set, use it as type restriction
                if self.all_from:
                    if isinstance(self.all_from, IRI):
                        raise ValueError(
                            f"Literal property {self.iri} cannot have allValuesFrom as Object IRI"
                        )
                    base_type = self.all_from
                else:
                    base_type = self.python_range_type or Any
            case PropertyValueKind.OBJECT:
                # Nested hydrated class becomes Pydantic model; else fallback to IRI
                if (
                    not self.nested
                    or self.nested.hydration_level is ClassHydrationLevel.REFERENCE
                ):
                    base_type = IRI
                else:
                    nested_model = self.nested.to_pydantic_model()
                    base_type = nested_model

                    def coerce_object(value):
                        parse = getattr(
                            nested_model, "model_validate", None
                        ) or getattr(nested_model, "parse_obj", None)
                        if value is None:
                            return value
                        if isinstance(value, nested_model):
                            return value
                        try:
                            from kapps_ogm.node.core import (
                                Node,
                            )  # Lazy import to avoid cycles
                        except Exception:
                            Node = None

                        if Node is not None and isinstance(value, Node):
                            payload = getattr(value, "instance", None) or getattr(
                                value, "data", None
                            )
                            if payload is not None and parse is not None:
                                return parse(payload)
                            return value

                        if isinstance(value, dict) and parse is not None:
                            return parse(value)
                        return value

                    validators.append(BeforeValidator(coerce_object))
            case PropertyValueKind.COMPLEX:
                # Complex properties have nested ClassSpec that should be converted to Pydantic model
                if (
                    not self.nested
                    or self.nested.hydration_level is ClassHydrationLevel.REFERENCE
                ):
                    base_type = Any
                else:
                    nested_model = self.nested.to_pydantic_model()
                    base_type = nested_model

                    def coerce_complex(value):
                        parse = getattr(
                            nested_model, "model_validate", None
                        ) or getattr(nested_model, "parse_obj", None)
                        if value is None:
                            return value
                        if isinstance(value, nested_model):
                            return value
                        try:
                            from kapps_ogm.node.core import (
                                Node,
                            )  # Lazy import to avoid cycles
                        except Exception:
                            Node = None

                        if Node is not None and isinstance(value, Node):
                            payload = getattr(value, "instance", None) or getattr(
                                value, "data", None
                            )
                            if payload is not None and parse is not None:
                                return parse(payload)
                            return value

                        if isinstance(value, dict) and parse is not None:
                            return parse(value)
                        return value

                    validators.append(BeforeValidator(coerce_complex))
            case _:
                raise RuntimeError

        # cardinality
        min_count = self.min_count or 0
        max_count = self.max_count

        # Always treat multiple cardinality as list
        is_multi = max_count is None or max_count > 1 or min_count > 1
        if is_multi:
            field_type = conlist(base_type, min_length=min_count, max_length=max_count)
            default = ... if self.required else []
        else:
            field_type = base_type
            default = ... if self.required else None

        # Apply some_from / all_from validators using Annotated types
        if self.some_from or self.all_from:

            def validate_some_all(v):
                if v is None:
                    return v
                values = v if isinstance(v, list) else [v]

                if self.some_from is not None:
                    if not any(isinstance(x, self.some_from) for x in values):
                        raise ValueError(
                            f"Property {self.iri} requires at least one value of type {self.some_from}"
                        )

                if self.all_from is not None:
                    if not all(isinstance(x, self.all_from) for x in values):
                        raise ValueError(
                            f"Property {self.iri} requires all values to be of type {self.all_from}"
                        )

                return v

            validators.append(BeforeValidator(validate_some_all))

        if validators:
            field_type = Annotated[field_type, *validators]

        # Wrap in Optional if not required
        if not self.required:
            field_type = Optional[field_type]

        # Create Pydantic Field
        field = Field(
            default=default,
            title=str(self.iri),
            description=f"PropertySpec for {self.iri}",
        )

        return field_type, field

    @classmethod
    def specify(
        cls,
        prop_iri: IRI,
        nested_scope: Optional["ClassScope"],
        ogm: "OGM",
        hydration_level: "ClassHydrationLevel",
    ) -> PropertySpec:
        # Categorize the property regarding its type and characteristics
        query_result = ogm.db.triples_get(
            sub=prop_iri, pred="rdf:type", include_implicit=False
        )
        property_types = [triple[2] for triple in query_result]

        if not property_types:
            raise ValueError(f"Property {prop_iri} has no rdf:type defined.")

        base_types = []
        characteristics = []

        for ptype in property_types:
            if ptype in PROPERTY_TYPES:
                base_types.append(PROPERTY_TYPES[ptype])
            elif ptype in PROPERTY_CHARACTERISTICS:
                characteristics.append(PROPERTY_CHARACTERISTICS[ptype])

        # Determine the property specification based on its range
        query_result = ogm.db.triples_get(
            sub=prop_iri, pred="rdfs:range", include_implicit=True
        )

        range_set = set(triple[2] for triple in range_query_result)
        range_set -= {IRI("http://www.w3.org/2002/07/owl#Thing")}

        if len(range_set) == 0:
            raise ValueError(f"Property {prop_iri} has no rdfs:range defined.")
        elif len(range_set) > 1:
            raise ValueError(
                f"Property {prop_iri} has multiple rdfs:range defined: {range_set}"
            )

        prop_range = range_set.pop()
        if isinstance(prop_range, type):
            if nested_scope:
                raise ValueError(
                    f"Property {prop_iri} cannot be part of a property chain as it has a literal range {prop_range}"
                )
            property_spec = cls._specify_literal_property(
                prop_iri=prop_iri,
                python_type=prop_range,
            )
        elif isinstance(prop_range, IRI):
            property_spec = cls._specify_class_property(
                prop_iri=prop_iri,
                range_iri=prop_range,
                nested_scope=nested_scope,
                ogm=ogm,
                hydration_level=hydration_level,
            )
        else:
            # Is blank node: Check if valid structure for complex datatype
            query_is_complex_type = f"""
                ASK {{
                    BIND({prop_iri.n3()} AS ?property)
                    ?property <http://www.w3.org/2000/01/rdf-schema#range> ?range .
                    {{
                        ?range a <http://www.w3.org/2002/07/owl#Restriction>
                    }}
                    UNION
                    {{
                        ?range <http://www.w3.org/2002/07/owl#intersectionOf> ?x
                    }}
                    UNION
                    {{
                        ?range <http://www.w3.org/2002/07/owl#unionOf> ?y
                    }}
                    UNION
                    {{
                        ?range <http://www.w3.org/2002/07/owl#complementOf> ?z
                    }}
                    UNION
                    {{
                        ?range <http://www.w3.org/2002/07/owl#oneOf> ?w
                    }}
                }}
            """
            if ogm.db.query(query_is_complex_type).get("boolean", False):
                property_spec = cls._specify_complex_property(
                    prop_iri=prop_iri,
                    ogm=ogm,
                )
            else:
                raise ValueError(
                    f"Unknown property_type: {prop_range} for property {prop_iri}"
                )

        # Apply characteristics to the property_spec
        if "functional" in characteristics:
            property_spec.max_count = 1

        return property_spec

    @classmethod
    def _specify_literal_property(
        cls,
        prop_iri: IRI,
        python_type: type,
    ) -> PropertySpec:
        property_spec = cls(
            iri=prop_iri,
            value_kind=PropertyValueKind.LITERAL,
            python_range_type=python_type,
            max_count=None,
            min_count=None,
            nested=None,
        )
        return property_spec

    @classmethod
    def _specify_class_property(
        cls,
        prop_iri: IRI,
        range_iri: IRI,
        nested_scope: Optional["ClassScope"],
        ogm: "OGM",
        hydration_level: "ClassHydrationLevel",
    ) -> PropertySpec:
        from .class_spec import ClassSpec

        nested_class_spec = ClassSpec.specify(
            ogm=ogm,
            class_iri=range_iri,
            class_scope=nested_scope,
            hydration_level=hydration_level,
        )

        property_spec = cls(
            iri=prop_iri,
            value_kind=PropertyValueKind.OBJECT,
            python_range_type=None,  # Will be another ClassSpec
            max_count=None,
            min_count=None,
            nested=nested_class_spec,
        )

        return property_spec

    @classmethod
    def _specify_complex_property(
        cls,
        prop_iri: IRI,
        ogm: "OGM",
    ) -> PropertySpec:
        """
        Processes a complex OWL property and returns a PropertySpec with a nested ClassSpec
        that includes intersection, union, complement, and enumerated restrictions.
        """
        from .class_spec import ClassSpec, ClassHydrationLevel

        # Initialize top-level PropertySpec
        property_spec = cls(
            iri=prop_iri,
            value_kind=PropertyValueKind.COMPLEX,
            python_range_type=None,
            min_count=None,
            max_count=None,
            nested=None,
        )

        # SPARQL query to get range restrictions and structural elements
        query = f"""SELECT
            ?range ?restriction ?onProperty ?someValuesFrom ?allValuesFrom
            ?minCardinality ?maxCardinality ?cardinality
            ?effectiveMinCardinality ?effectiveMaxCardinality
            ?intersectionList ?unionList ?complementClass ?oneOfList
        WHERE {{
            {prop_iri.n3()} <http://www.w3.org/2000/01/rdf-schema#range> ?range .

            # IntersectionOf members
            OPTIONAL {{
                ?range <http://www.w3.org/2002/07/owl#intersectionOf> ?intersectionList .
                ?intersectionList <http://www.w3.org/1999/02/22-rdf-syntax-ns#rest>*/<http://www.w3.org/1999/02/22-rdf-syntax-ns#first> ?restriction .
                ?restriction a <http://www.w3.org/2002/07/owl#Restriction> .
            }}

            # UnionOf members
            OPTIONAL {{
                ?range <http://www.w3.org/2002/07/owl#unionOf> ?unionList .
                ?unionList <http://www.w3.org/1999/02/22-rdf-syntax-ns#rest>*/<http://www.w3.org/1999/02/22-rdf-syntax-ns#first> ?restriction .
                ?restriction a <http://www.w3.org/2002/07/owl#Restriction> .
            }}

            # Restriction details
            OPTIONAL {{ ?restriction <http://www.w3.org/2002/07/owl#onProperty> ?onProperty }}
            OPTIONAL {{ ?restriction <http://www.w3.org/2002/07/owl#someValuesFrom> ?someValuesFrom }}
            OPTIONAL {{ ?restriction <http://www.w3.org/2002/07/owl#allValuesFrom> ?allValuesFrom }}
            OPTIONAL {{ ?restriction <http://www.w3.org/2002/07/owl#minCardinality> ?minCardinality }}
            OPTIONAL {{ ?restriction <http://www.w3.org/2002/07/owl#maxCardinality> ?maxCardinality }}
            OPTIONAL {{ ?restriction <http://www.w3.org/2002/07/owl#cardinality> ?cardinality }}

            # Normalize cardinality
            BIND(IF(BOUND(?cardinality), ?cardinality, ?minCardinality) AS ?effectiveMinCardinality)
            BIND(IF(BOUND(?cardinality), ?cardinality, ?maxCardinality) AS ?effectiveMaxCardinality)

            # Complement and enumeration
            OPTIONAL {{ ?range <http://www.w3.org/2002/07/owl#complementOf> ?complementClass }}
            OPTIONAL {{ ?range <http://www.w3.org/2002/07/owl#oneOf> ?oneOfList }}
        }}"""

        # Execute query
        query_result = ogm.db.query(query)
        bindings = query_result["results"]["bindings"]

        if not bindings:
            # No restrictions; treat as simple object with empty ClassSpec
            # Anonymous class is fully specified in-place
            property_spec.nested = ClassSpec(
                iri=None,
                properties={},
                metadata={},
                hydration_level=ClassHydrationLevel.FULL,
            )

            return property_spec

        # Initialize nested ClassSpec for the anonymous range
        # Anonymous class is fully specified in-place
        property_spec.nested = ClassSpec(
            iri=None,
            label=None,
            properties={},
            metadata={},
            hydration_level=ClassHydrationLevel.FULL,  # Anonymous class
        )

        # Process each restriction
        for restriction in bindings:
            if "onProperty" in restriction:
                nested_property = IRI(restriction["onProperty"]["value"])
                nested_spec = cls(
                    iri=nested_property,
                    value_kind=(
                        PropertyValueKind.LITERAL
                        if "someValuesFrom" in restriction
                        or "allValuesFrom" in restriction
                        else PropertyValueKind.OBJECT
                    ),
                    python_range_type=None,
                    min_count=None,
                    max_count=None,
                    nested=None,
                )

                # Determine type and requiredness
                if "someValuesFrom" in restriction:
                    range_iri = IRI(restriction["someValuesFrom"]["value"])
                    range_type = XSDToPythonTypes[range_iri]
                    if range_type:
                        nested_spec.some_from = range_type
                    else:
                        nested_spec.some_from = range_iri

                    nested_spec.min_count = 1

                elif "allValuesFrom" in restriction:
                    nested_spec.python_range_type = XSDToPythonTypes[
                        IRI(restriction["allValuesFrom"]["value"])
                    ]

                # Cardinality
                if "effectiveMinCardinality" in restriction:
                    nested_spec.min_count = int(
                        restriction["effectiveMinCardinality"]["value"]
                    )

                if "effectiveMaxCardinality" in restriction:
                    nested_spec.max_count = int(
                        restriction["effectiveMaxCardinality"]["value"]
                    )

                # Add nested property to ClassSpec
                property_spec.nested.properties[nested_property] = nested_spec

                # Update metadata for intersectionOf
                if "intersectionList" in restriction:
                    if "intersectionOf" not in property_spec.nested.metadata:
                        property_spec.nested.metadata["intersectionOf"] = []
                    property_spec.nested.metadata["intersectionOf"].append(
                        str(nested_property)
                    )

        # Store unionOf, complementOf, oneOf in metadata from first binding
        if bindings:
            first_binding = bindings[0]

            if "unionList" in first_binding:
                # Note: resolve_rdf_list method would need to be implemented in GraphDB
                property_spec.nested.metadata["unionOf"] = first_binding["unionList"][
                    "value"
                ]

            if "complementClass" in first_binding:
                property_spec.nested.metadata["complementOf"] = first_binding[
                    "complementClass"
                ]["value"]

            if "oneOfList" in first_binding:
                # Note: resolve_rdf_list method would need to be implemented in GraphDB
                property_spec.nested.metadata["oneOf"] = first_binding["oneOfList"][
                    "value"
                ]
        # print(f"Complex property {prop} processed: {property_spec.to_string()}")
        return property_spec
