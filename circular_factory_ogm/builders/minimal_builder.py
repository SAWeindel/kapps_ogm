from typing import Type, Tuple, Any
import pydantic as pd

from graph_db_interface import GraphDB, IRI, SPARQLQuery
from aas_middleware.model.core import Identifiable

from circular_factory_ogm.node import Node
from circular_factory_ogm.ogm import OGM


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
    id = node.id
    ogm = node.ogm
    db = ogm.db

    def _get_fields() -> dict[str, Tuple[Type, Any]]:
        # query = SPARQLQuery()
        # query.add_select_block(
        #     variables=["?attr", "?field", "?range"],
        #     where_clauses=[
        #         f"""
        #         {id.n3()} ?attr ?field .
        #         {{
        #             ?attr {IRI("rdfs:range").n3()} ?range .
        #         }}
        #         UNION
        #         {{
        #             ?attr {IRI("rdfs:domain").n3()} {id.n3()} .
        #         }}

        #         """
        #     ],
        # )
        # result = db.query(query)
        # fields = {
        #     IRI(binding["attr"]["value"]).short(): IRI
        #     for binding in result["results"]["bindings"]
        # }

        triples_sub = db.triples_get(sub=id)
        fields = {pred: (type(obj), obj) for _, pred, obj in triples_sub}
        return fields

    def _get_attributes() -> dict[IRI, IRI]:
        query = SPARQLQuery()
        query.add_select_block(
            variables=["?attr", "?range"],
            where_clauses=[
                f"""
                ?attr {IRI("rdfs:domain").n3()} {id.n3()} .
                ?attr {IRI("rdfs:range").n3()} ?range .
                """
            ],
        )
        result = db.query(query)
        attributes = {
            IRI(binding["attr"]["value"]): (
                IRI,
                IRI(binding["range"]["value"]),
            )
            for binding in result["results"]["bindings"]
        }
        return attributes

    model_creation_dict = _get_fields() | _get_attributes()

    model = pd.create_model(
        id.fragment or id,
        __base__=Identifiable,
        id=(IRI, id),
        **model_creation_dict,
    )

    return model
