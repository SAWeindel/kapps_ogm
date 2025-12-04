from typing import Dict, Any

from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.node import Node


def minimal_loader(node: Node) -> Dict[str, Any]:
    """
    A minimal loader function that retrieves all predicates and values for a given URI
    from a GraphDB triplestore and returns them as a dictionary.

    Args:
        id: The RDF URI reference of the object to load
    """
    id = node.id
    ogm = node.ogm
    db = ogm.db

    result = {"id": IRI(id)}
    triples = db.triples_get(sub=id)
    result |= {pred: obj for _, pred, obj in triples}
    return result
