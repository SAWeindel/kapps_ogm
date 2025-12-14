from typing import Optional, Type, TYPE_CHECKING, Any, List
from dataclasses import dataclass
from graph_db_interface import IRI
import logging
import pydantic as pd

from ...utils.constants import FUNDAMENTAL_CONCEPTS as fc
from ...utils.type_conversion import toPythonType

if TYPE_CHECKING:
    from .class_spec import ClassSpec
    from ...ogm import OGM
    from ...utils.pretty_print import property_spec_to_string

logger = logging.getLogger(__name__)


@dataclass
class PropertySpec:
    iri: IRI
    value_kind: str  # 'data' or 'object'
    python_range_type: Optional[Type] = None
    required: bool = False
    min_count: Optional[int] = None
    max_count: Optional[int] = None
    nested: Optional["ClassSpec"] = None  # Use string annotation

    def to_string(self) -> str:
        from ...utils.pretty_print import property_spec_to_string

        return property_spec_to_string(self)

    def to_pydantic_field(self) -> tuple[Any, Any]:
        """
        Convert this PropertySpec into a Pydantic field.
        """
        # Determine base type
        base_type = None
        if self.value_kind in ("data", "literal"):
            base_type = self.python_range_type or Any
        elif self.value_kind == "object":
            if not self.nested:
                raise ValueError(f"Object property {self.iri} missing nested ClassSpec")
            base_type = self.nested.to_pydantic_model()
        elif self.value_kind == "complex":
            if not self.nested:
                raise ValueError(f"Complex property {self.iri} missing nested ClassSpec")
            base_type = self.nested.to_pydantic_model()
        else:
            raise ValueError(f"Unknown value_kind: {self.value_kind}")

        # Determine if this is a list based on cardinality
        is_multi = (self.max_count is not None and self.max_count > 1) or (
            self.min_count is not None and self.min_count > 1
        )

        field_type: Any = List[base_type] if is_multi else base_type

        # Wrap in Optional if not required
        if not self.required:
            field_type = Optional[field_type]

        # Define Pydantic Field metadata
        field = pd.Field(
            default=... if self.required else None,
            title=str(self.iri),
        )

        return field_type, field


def process_literal_property(ogm: "OGM", prop: IRI) -> PropertySpec:
    triples = ogm.db.triples_get(sub=prop, pred=fc["RDFS_RANGE"], include_implicit=True)
    range_iris = [triple[2] for triple in triples]
    if len(range_iris) > 1:
        raise ValueError(
            f"Literal property {prop} has multiple rdfs:range defined: {range_iris}"
        )
    if not range_iris:
        raise ValueError(f"Literal property {prop} has no rdfs:range defined.")
    range_iri = range_iris[0]
    python_type = toPythonType(iri=range_iri, db=ogm.db)
    property_spec = PropertySpec(
        iri=prop,
        value_kind="data",
        python_range_type=python_type,
        required=False,
        max_count=None,
        min_count=None,
        nested=None,
    )
    logger.warning(
        f"Warning: The property {prop} has not been checked for OWL constraints yet. You might want to verify cardinality and existential constraints."
    )
    return property_spec


def process_class_property(ogm: "OGM", prop: IRI) -> PropertySpec:
    from .class_spec import ClassSpec

    triples = ogm.db.triples_get(sub=prop, pred=fc["RDFS_RANGE"], include_implicit=True)
    range_iris = [triple[2] for triple in triples]
    if len(range_iris) > 1:
        raise ValueError(
            f"Class property {prop} has multiple rdfs:range defined: {range_iris}"
        )
    if not range_iris:
        raise ValueError(f"Class property {prop} has no rdfs:range defined.")
    range_iri = range_iris[0]
    property_spec = PropertySpec(
        iri=prop,
        value_kind="object",
        python_range_type=None,  # Will be another ClassSpec
        required=False,
        max_count=None,
        min_count=None,
        nested=ClassSpec(iri=range_iri),
    )
    return property_spec


def process_complex_property(ogm: "OGM", prop: IRI) -> PropertySpec:
    """
    Processes a complex OWL property and returns a PropertySpec with a nested ClassSpec
    that includes intersection, union, complement, and enumerated restrictions.
    """
    from .class_spec import ClassSpec

    # Initialize top-level PropertySpec
    property_spec = PropertySpec(
        iri=prop,
        value_kind="complex",
        python_range_type=None,
        required=False,
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
        <{str(prop)}> <http://www.w3.org/2000/01/rdf-schema#range> ?range .

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
        return property_spec

    # Initialize nested ClassSpec for the anonymous range
    property_spec.nested = ClassSpec(
        iri=None, label=None, properties={}, metadata={}  # Anonymous class
    )

    # Process each restriction
    for restriction in bindings:
        if "onProperty" in restriction:
            nested_property = IRI(restriction["onProperty"]["value"])
            nested_spec = PropertySpec(
                iri=nested_property,
                value_kind=(
                    "literal"
                    if "someValuesFrom" in restriction or "allValuesFrom" in restriction
                    else "object"
                ),
                python_range_type=None,
                required=False,
                min_count=None,
                max_count=None,
                nested=None,
            )

            # Determine type and requiredness
            if "someValuesFrom" in restriction:
                nested_spec.python_range_type = toPythonType(
                    iri=IRI(restriction["someValuesFrom"]["value"]), db=ogm.db
                )
                nested_spec.required = True

            elif "allValuesFrom" in restriction:
                nested_spec.python_range_type = toPythonType(
                    iri=IRI(restriction["allValuesFrom"]["value"]), db=ogm.db
                )
                nested_spec.required = False

            # Cardinality
            if "effectiveMinCardinality" in restriction:
                nested_spec.min_count = int(
                    restriction["effectiveMinCardinality"]["value"]
                )
                if nested_spec.min_count > 0:
                    nested_spec.required = True

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
            property_spec.nested.metadata["oneOf"] = first_binding["oneOfList"]["value"]

    print(f"Complex property {prop} processed: {property_spec.to_string()}")
    return property_spec
