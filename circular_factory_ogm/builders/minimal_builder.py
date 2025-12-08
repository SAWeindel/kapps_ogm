from typing import Type
import pydantic as pd

from graph_db_interface import IRI, SPARQLQuery, process_bindings_select
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
    result = db.query(query, convert_bindings=True)
    for binding in result["results"]["bindings"]:
        attr_iri = binding["attr"]
        field_entry = binding["field"]
        if field_entry == class_id:
            continue  # avoid self-references
        if isinstance(field_entry, IRI):
            print(f"build added {field_entry} to ref")
            ogm.type_references.add(field_entry)
            field_type = f"models['{field_entry.lined}']"
            model_creation_dict[attr_iri] = (list[field_type], pd.Field())
        elif isinstance(field_entry, type):
            field_type = field_entry
            model_creation_dict[attr_iri] = (list[field_type], pd.Field())
        else:
            field_type = type(field_entry)
            model_creation_dict[attr_iri] = (list[field_type], field_entry)

    # find attributes attached to blank nodes
    query = SPARQLQuery()
    query.add_select_block(
        variables=["?attr", "?attribute_node", "?sub_attr", "?field"],
        where_clauses=[
            f"""
            {class_id.n3()} ?attr ?attribute_node .
            ?attribute_node owl:intersectionOf ?fields_list .
            ?fields_list rdf:rest*/rdf:first ?field_node .
            ?field_node a owl:Restriction ;
                owl:onProperty ?sub_attr ;
                owl:someValuesFrom ?field .
            FILTER(isBlank(?attribute_node)) .
            """
        ],
    )
    result = db.query(query, convert_bindings=True)
    attributes = process_bindings_select(
        result["results"]["bindings"],
        grouping_variables=["attr"],
        variables=["attribute_node", "sub_attr", "field"],
    )
    for attr_iri, attr_fields in attributes.items():
        attr_creation_dict = {}
        for attr_node, attr_field_iri, field_entry in attr_fields:
            if isinstance(field_entry, IRI):
                print(f"build added {field_entry} to ref")
                ogm.type_references.add(field_entry)
                field_type = f"models['{field_entry.lined}']"
                attr_creation_dict[attr_field_iri] = (list[field_type], pd.Field())
            elif isinstance(field_entry, type):
                field_type = field_entry
                attr_creation_dict[attr_field_iri] = (list[field_type], pd.Field())
            else:
                field_type = type(field_entry)
                attr_creation_dict[attr_field_iri] = (list[field_type], field_entry)

        attr_model = pd.create_model(
            attr_node,
            __base__=pd.BaseModel,
            **attr_creation_dict,
        )
        model_creation_dict[attr_iri] = (list[attr_model], pd.Field())

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
