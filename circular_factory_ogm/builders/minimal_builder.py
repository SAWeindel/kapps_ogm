from typing import Type
import pydantic as pd

from graph_db_interface import IRI, SPARQLQuery, process_bindings_select
from graph_db_interface.utils.utils import convert_query_result_to_python_type
from graph_db_interface.utils.typemap import XSDToPythonTypes
from aas_middleware.model.core import Identifiable

from circular_factory_ogm.node import Node


def minimal_builder(node: Node) -> Type[Identifiable]:
    """
    A minimal builder function that creates a simple Pydantic model class
    for the given URI.

    Args:
        id: The RDF URI reference of the object to build a model class for
        db: GraphDB instance (not used in this minimal example)

    Returns:
        A simple Pydantic model class
    """
    node_id = node.id
    ogm = node.ogm
    db = ogm.db

    class_id = db.owl_get_classes_of_individual(node_id)[0]

    model_creation_dict = {}

    # find direct fields
    query = SPARQLQuery()
    query.add_select_block(
        variables=["?attr", "?field"],
        where_clauses=[
            f"""
            {class_id.n3()} ?attr ?field .
            FILTER(!isBlank(?field)) .
            """
        ],
    )
    result = db.query(query)
    for binding in result["results"]["bindings"]:
        attr = IRI(binding["attr"]["value"])
        field_type = binding["field"]["type"]
        if field_type == "uri":
            field = IRI(binding["field"]["value"])
            if field in XSDToPythonTypes:
                # Direct datatype field - type is python equivalent of XSD type
                model_creation_dict[attr] = (XSDToPythonTypes[field], pd.Field())
            else:
                # Reference to another class - type is forward reference to model of that class
                # OGM keeps track of class references to ensure they
                # are built when the pydantic model is constructed
                print(f"build added {field} to ref")
                ogm.type_references.add(field)
                model_creation_dict[attr] = (f"models['{field.lined}']", pd.Field())
        elif field_type == "literal":
            # Direct datatype field - type is python equivalent of XSD type
            literal = convert_query_result_to_python_type(binding["field"])
            model_creation_dict[attr] = (type(literal), literal)

    # find attributes attached to blank nodes
    query = SPARQLQuery()
    query.add_select_block(
        variables=["?attr", "?sub_attr", "?field"],
        where_clauses=[
            f"""
            {class_id.n3()} ?attr ?attribute_node .
            ?attribute_node owl:intersectionOf ?fields_list .
            ?fields_list rdf:rest*/rdf:first ?field_node .
            ?field_node a owl:Restriction ;
                owl:onProperty ?sub_attr ;
                owl:someValuesFrom ?field 
            """
        ],
    )
    result = db.query(query)
    attributes = process_bindings_select(
        result["results"]["bindings"],
        variables=["sub_attr", "field"],
        grouping_variables=["attr"],
    )
    # TODO fix loader to actually detect and support this
    for attr_str, attr_dict in attributes.items():
        model_creation_dict[IRI(attr_str)] = (dict, pd.Field())

    model = pd.create_model(
        class_id.lined,
        __base__=Identifiable,
        id=(IRI, class_id),
        **model_creation_dict,
    )

    # Cache the created model in the OGM's type cache
    print(f"build added {class_id} to ref")
    ogm.type_references.add(class_id)
    print(f"created node {model} for {class_id}")
    ogm.type_cache[class_id] = model

    return model
