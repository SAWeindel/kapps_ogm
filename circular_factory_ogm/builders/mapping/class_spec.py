from typing import Optional, Type, Any, Dict
from dataclasses import dataclass, field
from graph_db_interface import IRI
from circular_factory_ogm.utils.pretty_print import class_spec_to_string
from circular_factory_ogm.builders.mapping.property_spec import PropertySpec
from circular_factory_ogm.node import Node
from circular_factory_ogm.utils.constants import (
    FUNDAMENTAL_CONCEPTS as fc,
    PROPERTY_TYPES,
    PROPERTY_CHARACTERISTICS,
)
from graph_db_interface import SPARQLQuery
from graph_db_interface.utils.processing import process_bindings_select
import logging

# If you use logger.warning, define logger or use logging.warning directly
logger = logging.getLogger(__name__)


@dataclass
class ClassSpec:
    iri: IRI
    label: Optional[str] = None
    properties: Dict[IRI, "PropertySpec"] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_string(self) -> str:
        return class_spec_to_string(self)


def classify_direct_predicates(
    node: Node,
):
    sub = node.id
    ogm = node.ogm
    db = ogm.db
    rdf_type = fc["RDF_TYPE"]
    rdfs_subclassof = fc["RDFS_SUBCLASSOF"]
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
    node: Node,
    iri: Optional[IRI] = None,
):
    domain = iri if iri is not None else node.id
    ogm = node.ogm
    db = ogm.db

    query = SPARQLQuery(include_implicit=True)
    where_clauses = [
        f"?property <{fc['RDFS_DOMAIN']}> <{domain}> .",
    ]
    query.add_select_block(variables=["?property"], where_clauses=where_clauses)
    result = db.query(query.to_string())
    properties = [
        IRI(binding["property"]["value"]) for binding in result["results"]["bindings"]
    ]
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

        query_result = node.ogm.db.query(sparql_query)
        range_types = [
            binding["rangeType"]["value"]
            for binding in query_result["results"]["bindings"]
        ]

        property_spec = None
        if range_types:
            match range_types[0]:
                case "literal":
                    property_spec = process_literal_property(node.ogm, prop)
                case "class":
                    property_spec = process_class_property(node.ogm, prop)
                case "complex":
                    property_spec = process_complex_property(node.ogm, prop)
                case _:
                    logging.warning(f"Unknown range type for property {prop}")

        # Apply characteristics to the property_spec if it exists
        if property_spec and "functional" in characteristics:
            property_spec.max_count = 1

        if property_spec:
            print(f"Processed property {prop}: {property_spec}")
            node.model_data[prop] = property_spec

    print(f"Final model data properties: {node.model_data}")
