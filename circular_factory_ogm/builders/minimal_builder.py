from typing import Any, Type
import pydantic as pd

from graph_db_interface import IRI, SPARQLQuery, process_bindings_select
from aas_middleware.model.core import Identifiable

from circular_factory_ogm.node.core import Node

FIELD_QUERY = """
SELECT ?attr ?attribute_node ?field_pred ?field
FROM <http://www.ontotext.com/explicit>
WHERE {{
    {class_id} ?field_pred ?field .
    FILTER(!isBlank(?field)) .
}}
"""

BNODE_QUERY = """
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>

SELECT ?attr ?attribute_node ?field_pred ?field
FROM <http://www.ontotext.com/explicit>
WHERE {{
    # Find object properties with intersection range classes
    {{
        ?attr a owl:ObjectProperty ;
            rdfs:domain {class_iri} ;
            rdfs:range ?attribute_node .
    }}
    UNION
    {{
        {class_iri} ?attr ?attribute_node .
        FILTER(isBlank(?attribute_node)) .
    }}

    # Intersection class
    ?attribute_node owl:intersectionOf ?list .

    # Iterate list members
    ?list rdf:rest*/rdf:first ?field_node .

    # Must be an OWL restriction
    ?field_node a owl:Restriction ;
                owl:onProperty ?field_pred .

    # ---- VALUE RESTRICTIONS ----
    {{
        ?field_node owl:someValuesFrom ?f .
        BIND("someValuesFrom" AS ?restrictionType)
        BIND(?f AS ?field)
    }}
    UNION
    {{
        ?field_node owl:allValuesFrom ?f .
        BIND("allValuesFrom" AS ?restrictionType)
        BIND(?f AS ?field)
    }}
    UNION
    {{
        ?field_node owl:hasValue ?f .
        BIND("hasValue" AS ?restrictionType)
        BIND(?f AS ?field)
    }}

    # ---- CARDINALITY (unqualified) ----
    UNION
    {{
        ?field_node owl:cardinality ?f .
        BIND("cardinality" AS ?restrictionType)
        BIND(?f AS ?field)
    }}
    UNION
    {{
        ?field_node owl:minCardinality ?f .
        BIND("minCardinality" AS ?restrictionType)
        BIND(?f AS ?field)
    }}
    UNION
    {{
        ?field_node owl:maxCardinality ?f .
        BIND("maxCardinality" AS ?restrictionType)
        BIND(?f AS ?field)
    }}

    # ---- QUALIFIED CARDINALITIES ----
    UNION
    {{
        ?field_node owl:qualifiedCardinality ?c ;
            owl:onClass ?cls .
        BIND("qualifiedCardinality" AS ?restrictionType)
        BIND(CONCAT(str(?c), " onClass=", str(?cls)) AS ?field)
    }}
    UNION
    {{
        ?field_node owl:minQualifiedCardinality ?c ;
            owl:onClass ?cls .
        BIND("minQualifiedCardinality" AS ?restrictionType)
        BIND(CONCAT(str(?c), " onClass=", str(?cls)) AS ?field)
    }}
    UNION
    {{
        ?field_node owl:maxQualifiedCardinality ?c ;
            owl:onClass ?cls .
        BIND("maxQualifiedCardinality" AS ?restrictionType)
        BIND(CONCAT(str(?c), " onClass=", str(?cls)) AS ?field)
    }}
}}
"""


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

    def _add_field(
        creation_dict: dict[IRI, tuple[Type[list[pd.BaseModel]], pd.Field]],
        field_iri: IRI,
        field_entry: Any,
        allow_self_reference: bool = True,
    ):
        if not allow_self_reference and field_entry == class_id:
            return  # avoid references to the node the field is added to
        elif field_iri in creation_dict:
            raise NotImplementedError(
                "Multiple types or entries for a single field not supported in minimal_builder"
            )

        if isinstance(field_entry, IRI):
            field_type = ogm.get_reference_to(id=field_entry)
            creation_dict[field_iri] = (list[field_type], [])
        elif isinstance(field_entry, type):
            field_type = field_entry
            creation_dict[field_iri] = (list[field_type], [])
        else:
            field_type = type(field_entry)
            creation_dict[field_iri] = (list[field_type], [field_entry])

    model_creation_dict: dict[IRI, tuple[Type[list[pd.BaseModel]], pd.Field]] = {}

    # find direct fields
    result = db.query(
        FIELD_QUERY.format(class_id=class_id.n3()),
        convert_bindings=True,
    )
    for binding in result["results"]["bindings"]:
        _add_field(
            creation_dict=model_creation_dict,
            field_iri=binding["field_pred"],
            field_entry=binding["field"],
            allow_self_reference=False,
        )

    # find attributes attached to blank nodes
    result = db.query(
        BNODE_QUERY.format(class_iri=class_id.n3()),
        convert_bindings=True,
    )
    bindings = result["results"]["bindings"]
    attribute_node_map = {
        bindings[i]["attr"]: bindings[i]["attribute_node"] for i in range(len(bindings))
    }
    attributes = process_bindings_select(
        bindings,
        grouping_variables=["attr", "field_pred"],
        variables=["field"],
    )

    for field_iri, bnode_fields in attributes.items():
        attr_creation_dict: dict[IRI, tuple[Type[list[pd.BaseModel]], pd.Field]] = {}
        for bnode_field_iri, field_entry_tuple in bnode_fields.items():
            _add_field(
                creation_dict=attr_creation_dict,
                field_iri=bnode_field_iri,
                field_entry=field_entry_tuple[0],
                allow_self_reference=True,
            )

        attr_model = ogm.create_bnode_type(
            bnode=attribute_node_map[field_iri],
            creation_dict=attr_creation_dict,
        )
        model_creation_dict[field_iri] = (list[attr_model], [])

    model = ogm.create_node_type(
        id=class_id,
        creation_dict=model_creation_dict,
    )

    return model
