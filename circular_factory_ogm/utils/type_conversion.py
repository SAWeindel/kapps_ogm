
import logging
from graph_db_interface import IRI, GraphDB
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
    logging.warning(
        f"Warning: TODO: The datatype {iri} has not been fully checked for OWL datatype definitions yet. Defaulting to basic type mapping."
    )
    datatype_mapping = {
        "http://www.w3.org/2001/XMLSchema#string": str,
        "http://www.w3.org/2001/XMLSchema#integer": int,
        "http://www.w3.org/2001/XMLSchema#float": float,
        "http://www.w3.org/2001/XMLSchema#double": float,
        "http://www.w3.org/2001/XMLSchema#boolean": bool,
        "http://www.w3.org/2001/XMLSchema#dateTime": str,
        "http://www.w3.org/2001/XMLSchema#date": str,
    }

    # Check mapping FIRST before querying database
    iri_str = str(iri)
    if iri_str in datatype_mapping:
        return datatype_mapping[iri_str]

    # Default to string if not in mapping
    return str
