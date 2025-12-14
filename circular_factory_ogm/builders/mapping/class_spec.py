from typing import Optional, Type, Any, Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field
from graph_db_interface import IRI, SPARQLQuery
from graph_db_interface.utils.processing import process_bindings_select
import logging
from .property_spec import process_literal_property, process_class_property, process_complex_property

from ...utils.constants import (
    FUNDAMENTAL_CONCEPTS as fc,
    PROPERTY_TYPES,
    PROPERTY_CHARACTERISTICS,
)

if TYPE_CHECKING:
    from .property_spec import PropertySpec
    from ...ogm import OGM
    from ...node import Node
    from ...utils.pretty_print import class_spec_to_string

logger = logging.getLogger(__name__)


@dataclass
class ClassSpec:
    iri: Optional[IRI]
    label: Optional[str] = None
    properties: Dict[IRI, "PropertySpec"] = field(default_factory=dict)
    types: List[IRI] = field(default_factory=list)
    superclasses: List[IRI] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_string(self) -> str:
        from ...utils.pretty_print import class_spec_to_string

        return class_spec_to_string(self)


def specify(class_iri: IRI, ogm: "OGM") -> ClassSpec:
    """
    create a ClassSpec for the given IRI by analyzing its RDF data in the GraphDB via the OGM instance.

        Args:
            iri: The IRI of the class to specify
            ogm: The OGM instance with access to the GraphDB
        Returns:
            A ClassSpec instance representing the class specification"""
    db = ogm.db

    # first we get all types of the class
    triples = db.triples_get(sub=class_iri, pred=fc["RDF_TYPE"], include_implicit=True)
    class_types = [triple[2] for triple in triples]
    if fc["OWL_CLASS"] not in class_types and fc["RDFS_CLASS"] not in class_types:
        raise ValueError(f"IRI {class_iri} is not an OWL/RDFS Class.")

    class_spec = ClassSpec(iri=class_iri)
    class_spec.types = class_types

    label_triples = db.triples_get(
        sub=class_iri, pred=fc["RDFS_LABEL"], include_implicit=True
    )
    if label_triples:
        class_spec.label = str(label_triples[0][2])

    superclasses = [
        triple[2]
        for triple in db.triples_get(
            sub=class_iri, pred=fc["RDFS_SUBCLASS_OF"], include_implicit=True
        )
    ]
    if class_iri in superclasses:
        superclasses.remove(class_iri)
    else:
        logger.warning(
            f"{class_iri} should be implicitely a subclass of itself but is not found in rdfs:subClassOf."
        )
    if superclasses:
        class_spec.superclasses = superclasses

    class_spec.properties = classify_outgoing_properties(class_iri, ogm)

    print(f"Specifying class {class_iri} as {class_spec.to_string()}")

    return class_spec


def classify_direct_predicates(
    node: "Node",
):
    sub = node.id
    ogm = node.ogm
    db = ogm.db
    rdf_type = fc["RDF_TYPE"]
    owl_class = fc["OWL_CLASS"]

    query = SPARQLQuery(include_implicit=False)
    query.add_select_block(
        variables=["?predicate", "?object"],
        where_clauses=[f"<{sub}> ?predicate ?object ."],
    )
    result = db.query(query.to_string())
    predicate_dict: Dict[IRI, tuple[IRI, ...]] = process_bindings_select(
        result["results"]["bindings"],
        variables=["object"],
        grouping_variables=["predicate"],
    )

    if owl_class in predicate_dict.get(rdf_type, []):
        # Track handled predicates
        handled_predicates = set()

        # Assign FC values to variables for match statement
        rdfs_label = fc["RDFS_LABEL"]

        # Process each predicate with specific handlers
        for predicate, values in predicate_dict.items():
            match predicate:
                case _ if predicate == rdf_type:
                    for type_iri in values:
                        node.add_rdf_type(type_iri)
                    handled_predicates.add(predicate)

                case _ if predicate == rdfs_label:
                    if values:
                        node.model_data[rdfs_label] = [str(label) for label in values]
                    handled_predicates.add(predicate)

                # Add more cases here for other known predicates
                case _:
                    # Not handled, will be added to remaining_predicates
                    pass

        # Update model_data with remaining predicates (excluding handled ones)
        if handled_predicates != set(predicate_dict.keys()):
            remaining_predicates = {
                k: v for k, v in predicate_dict.items() if k not in handled_predicates
            }
            logger.warning(
                "discovered not explicitely handeled direct predicates in OWL Class: %s",
                remaining_predicates,
            )
            node.model_data.update(remaining_predicates)

    logging.debug("Classified predicates: %s", predicate_dict)


def classify_outgoing_properties(
    class_iri: IRI, ogm: "OGM"
) -> dict[IRI, "PropertySpec"]:
    db = ogm.db

    properties = [
        triple[0]
        for triple in db.triples_get(
            pred=fc["RDFS_DOMAIN"], obj=class_iri, include_implicit=True
        )
    ]
    property_spec_dict: dict[IRI, PropertySpec] = {}
    for prop in properties:
        ### first we categorize the property regarding its type and characteristics
        # query for property type
        query_result = db.triples_get(
            sub=prop, pred=fc["RDF_TYPE"], include_implicit=False
        )
        property_types = [triple[2] for triple in query_result]

        if not property_types:
            raise ValueError(f"Property {prop} has no rdf:type defined.")

        # Categorize property types and check if functional property
        base_types = []
        characteristics = []

        for ptype in property_types:
            if ptype in PROPERTY_TYPES:
                base_types.append(PROPERTY_TYPES[ptype])
            elif ptype in PROPERTY_CHARACTERISTICS:
                characteristics.append(PROPERTY_CHARACTERISTICS[ptype])

        ### while the domain is clear (the node we are analyzing) the range needs to be analyzed
        sparql_query = f"""
        SELECT ?rangeType
        WHERE {{
            BIND(<{str(prop)}> AS ?property) .
            ?property <{fc['RDFS_RANGE']}> ?range .
            BIND(IF(EXISTS {{ ?range <{fc['RDF_TYPE']}> <http://www.w3.org/2000/01/rdf-schema#Datatype> }}, "literal",
                IF(EXISTS {{ ?range <{fc['RDF_TYPE']}> <http://www.w3.org/2002/07/owl#DatatypeProperty> }}, "literal",
                IF((EXISTS {{ ?range <{fc['RDF_TYPE']}> <{fc['OWL_CLASS']}> }} || EXISTS {{ ?range <{fc['RDF_TYPE']}> <http://www.w3.org/2000/01/rdf-schema#Class> }} ) && isIRI(?range), "class",
                IF(EXISTS {{ ?range <{fc['RDF_TYPE']}> <http://www.w3.org/2002/07/owl#Restriction> }}
                    || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#intersectionOf> ?x }}
                    || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#unionOf> ?y }}
                    || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#complementOf> ?z }}
                    || EXISTS {{ ?range <http://www.w3.org/2002/07/owl#oneOf> ?w }},
                    "complex",
                    "unknown"
                )))) AS ?rangeType)
        }}
        """

        query_result = db.query(sparql_query)
        range_types = [
            binding["rangeType"]["value"]
            for binding in query_result["results"]["bindings"]
        ]

        property_spec = None
        if range_types:
            match range_types[0]:
                case "literal":
                    property_spec = process_literal_property(ogm, prop)
                case "class":
                    property_spec = process_class_property(ogm, prop)
                case "complex":
                    property_spec = process_complex_property(ogm, prop)
                case _:
                    logging.warning(f"Unknown range type for property {prop}")

        # Apply characteristics to the property_spec if it exists
        if property_spec and "functional" in characteristics:
            property_spec.max_count = 1

        if property_spec:
            print(f"Processed property {prop}: {property_spec.to_string()}")
            property_spec_dict[prop] = property_spec

    print(f"Final model data properties: {property_spec_dict}")
    return property_spec_dict
