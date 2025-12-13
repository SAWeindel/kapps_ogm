from graph_db_interface import IRI, GraphDB, SPARQLQuery
from circular_factory_ogm.utils.constants import FUNDAMENTAL_CONCEPTS as fc
from typing import Type, Any


def toPythonType(iri: IRI, db: GraphDB) -> Type[Any]:
    """
    Converts an RDF datatype IRI to a Python type.

    Args:
        iri: The IRI representing an RDF datatype
        db: The GraphDB instance to query for type information

    Returns:
        The corresponding Python type
    """
    # Map common XSD datatypes to Python types
    datatype_mapping = {
        "http://www.w3.org/2001/XMLSchema#string": str,
        "http://www.w3.org/2001/XMLSchema#integer": int,
        "http://www.w3.org/2001/XMLSchema#float": float,
        "http://www.w3.org/2001/XMLSchema#double": float,
        "http://www.w3.org/2001/XMLSchema#boolean": bool,
        "http://www.w3.org/2001/XMLSchema#dateTime": str,
        "http://www.w3.org/2001/XMLSchema#date": str,
    }
    query = SPARQLQuery()
    query.add_ask_block(
        [f"<{str(iri)}> <{str(fc['RDF_TYPE'])}> <{str(fc['RDFS_DATATYPE'])}> ."]
    )
    result = db.query(query.to_string())
    is_datatype = result.get("boolean", False)

    if not is_datatype:
        return str

    iri_str = str(iri)
    if iri_str in datatype_mapping:
        return datatype_mapping[iri_str]

    # Default to string if datatype is unknown
    return str
