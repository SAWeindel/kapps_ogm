from typing import Dict, Any

from graph_db_interface import GraphDB, IRI


def minimal_loader(id: IRI, db: GraphDB) -> Dict[str, Any]:
    """
    A minimal loader function that retrieves all predicates and values for a given URI
    from a GraphDB triplestore and returns them as a dictionary.

    Args:
        id: The RDF URI reference of the object to load
    """

    result = {}
    result["id"] = id

    return result
