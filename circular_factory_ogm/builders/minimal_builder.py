from typing import Type
import pydantic as pd

from graph_db_interface import GraphDB, IRI
from aas_middleware.model.core import Identifiable


def minimal_builder(id: IRI, db: GraphDB) -> Type[Identifiable]:
    """
    A minimal builder function that creates a simple Pydantic model class
    for the given URI.

    Args:
        id: The RDF URI reference of the object to build a model class for
        db: GraphDB instance (not used in this minimal example)

    Returns:
        A simple Pydantic model class
    """
    minimal_model = pd.create_model(
        "MinimalModel",
        __base__=Identifiable,
        id=(IRI, id),
    )

    return minimal_model
