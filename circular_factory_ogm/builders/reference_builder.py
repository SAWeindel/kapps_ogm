from typing import Type
import pydantic as pd

from graph_db_interface import IRI
from aas_middleware.model.core import Identifiable


def reference_builder(node) -> Type[Identifiable]:
    id = node.id

    model = pd.create_model(
        id.fragment or id,
        __base__=Identifiable,
        id=(IRI, id),
    )

    return model
