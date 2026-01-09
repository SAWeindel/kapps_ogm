from __future__ import annotations

from typing import Optional, Type, TYPE_CHECKING, Any, Union, Annotated
from enum import Enum
from dataclasses import dataclass
from graph_db_interface import IRI, XSDToPythonTypes
import logging
from pydantic import BeforeValidator, Field, conlist

from circular_factory_ogm.utils.constants import (
    PROPERTY_TYPES,
    PROPERTY_CHARACTERISTICS,
)

if TYPE_CHECKING:
    from circular_factory_ogm.mapping.class_spec import ClassSpec
    from circular_factory_ogm.ogm import OGM

logger = logging.getLogger("cf_pspec")


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
        if self.min_count is not None and self.min_count >= 1:
            return True
        return False

    def to_string(self) -> str:
        from ..utils.pretty_print import property_spec_to_string

        return property_spec_to_string(self)

    def to_pydantic_field(self) -> tuple[Any, Any]:
        """Convert this PropertySpec into a Pydantic field with validators."""
        logger.debug(
            f"Converting PropertySpec ({self.value_kind.value}) '{self.iri.fragment}' to pydantic field"
        )

        if self.value_kind is PropertyValueKind.LITERAL:
            # If all_from is set, use it as type restriction
            if self.all_from:
                if isinstance(self.all_from, IRI):
                    raise ValueError(
                        f"Literal property {self.iri} cannot have allValuesFrom as Object IRI"
                    )
                base_type = self.all_from
            else:
                base_type = self.python_range_type or Any
        elif self.value_kind is PropertyValueKind.OBJECT:
            # Nested hydrated class becomes Pydantic model; else fallback to IRI
            if self.nested and getattr(self.nested, "_hydrated", False):
                base_type = self.nested.to_pydantic_model()
            else:
                base_type = IRI
        elif self.value_kind is PropertyValueKind.COMPLEX:
            # Complex properties have nested ClassSpec that should be converted to Pydantic model
            if self.nested:
                base_type = self.nested.to_pydantic_model()
            else:
                base_type = Any
        else:
            raise ValueError(f"Unknown value_kind: {self.value_kind}")

        # cardinality
        min_count = self.min_count or 0
        max_count = self.max_count

        # Always treat multiple cardinality as list
        is_multi = max_count is None or max_count > 1 or min_count > 1
        if is_multi:
            field_type = conlist(base_type, min_length=min_count, max_length=max_count)
        else:
            field_type = base_type

        # Apply some_from / all_from validators using Annotated types
        if self.some_from or self.all_from:

            def make_validator(some_type, all_type):
                def validate(v):
                    if v is None:
                        return v
                    values = v if isinstance(v, list) else [v]

                    if some_type is not None:
                        if not any(isinstance(x, some_type) for x in values):
                            raise ValueError(
                                f"Property {self.iri} requires at least one value of type {some_type}"
                            )

                    if all_type is not None:
                        if not all(isinstance(x, all_type) for x in values):
                            raise ValueError(
                                f"Property {self.iri} requires all values to be of type {all_type}"
                            )

                    return v

                return validate

            validator = BeforeValidator(make_validator(self.some_from, self.all_from))
            field_type = Annotated[field_type, validator]

        # Wrap in Optional if not required
        if not self.required:
            field_type = Optional[field_type]

        # Create Pydantic Field
        field = Field(
            default=... if self.required else None,
            title=str(self.iri),
            description=f"PropertySpec for {self.iri}",
        )

        return field_type, field

    @classmethod
    def specify(
        cls,
        prop_iri: IRI,
        ogm: "OGM",
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

        if len(query_result) == 0:
            raise ValueError(f"Property {prop_iri} has no rdfs:range defined.")
        elif len(query_result) > 1:
            raise ValueError(
                f"Property {prop_iri} has multiple rdfs:range defined: {[triple[2] for triple in query_result]}"
            )

        prop_range = query_result[0][2]
        if isinstance(prop_range, type):
            property_spec = cls._specify_literal_property(prop_iri, prop_range)
        elif isinstance(prop_range, IRI):
            property_spec = cls._specify_class_property(prop_iri, prop_range)
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
                property_spec = cls._specify_complex_property(ogm, prop_iri)
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
        logger.warning(
            f"Warning: The property {prop_iri} has not been checked for OWL constraints yet. You might want to verify cardinality and existential constraints."
        )
        return property_spec

    @classmethod
    def _specify_class_property(
        cls,
        prop_iri: IRI,
        range_iri: IRI,
    ) -> PropertySpec:
        from .class_spec import ClassSpec

        property_spec = cls(
            iri=prop_iri,
            value_kind=PropertyValueKind.OBJECT,
            python_range_type=None,  # Will be another ClassSpec
            max_count=None,
            min_count=None,
            nested=ClassSpec(iri=range_iri),
        )
        return property_spec

    @classmethod
    def _specify_complex_property(
        cls,
        ogm: "OGM",
        prop_iri: IRI,
    ) -> PropertySpec:
        """
        Processes a complex OWL property and returns a PropertySpec with a nested ClassSpec
        that includes intersection, union, complement, and enumerated restrictions.
        """
        from .class_spec import ClassSpec

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
            property_spec.nested = ClassSpec(iri=None, properties={}, metadata={})
            # Anonymous class is fully specified in-place
            property_spec.nested._hydrated = True
            return property_spec

        # Initialize nested ClassSpec for the anonymous range
        property_spec.nested = ClassSpec(
            iri=None, label=None, properties={}, metadata={}  # Anonymous class
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

        # Mark anonymous nested class as hydrated since it was fully built here
        if property_spec.nested is not None:
            property_spec.nested._hydrated = True

        # print(f"Complex property {prop} processed: {property_spec.to_string()}")
        return property_spec
