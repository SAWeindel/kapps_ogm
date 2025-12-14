import os
import uvicorn
import logging
import json

import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.builders.mapping.class_spec import ClassSpec, specify
from circular_factory_ogm.loaders.minimal_loader import minimal_loader
from circular_factory_ogm.builders.minimal_builder import minimal_builder
from circular_factory_ogm.loaders.loader_eh import loader_eh
from circular_factory_ogm.builders.mapping.class_spec import (
    classify_direct_predicates,
    classify_outgoing_properties,
)

NODE_ID = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit"
    # "https://www.sfb1574.kit.edu/ontologies/DemoStructureInstance#NodeB"
    # "https://www.sfb1574.kit.edu/ontologies/examples#TopLevelEntity"
)


def main():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(credentials=credentials)
    db.logger.setLevel(logging.INFO)
    ogm = OGM(db=db, loader_func=loader_eh, builder_func=minimal_builder)
    class_spec = specify(class_iri=NODE_ID, ogm=ogm)
    print("ClassSpec:")
    print(class_spec.to_string())

    # node = ogm.create_node(id=NODE_ID)
    # classify_direct_predicates(node)
    # classify_outgoing_properties(node)


if __name__ == "__main__":
    main()
