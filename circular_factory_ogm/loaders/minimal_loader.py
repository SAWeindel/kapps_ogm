from typing import Dict, Any

from graph_db_interface import GraphDB, IRI
from graph_db_interface.utils.xsd_typemap import XSDToPythonTypes

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

    instance_data = {"id": IRI(id)}

    triples = db.triples_get(sub=id)
    for _, pred, obj in triples:
        if isinstance(obj, IRI):
            node = ogm.create_node(id=obj)
            instance_data[pred] = node
        else:
            instance_data[pred] = obj

    return instance_data
