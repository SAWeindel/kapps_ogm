import os
import uvicorn
import logging
import json

import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.loaders.minimal_loader import minimal_loader
from circular_factory_ogm.builders.minimal_builder import minimal_builder
from circular_factory_ogm.loaders.loader_eh import loader_eh

NODE_ID = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#ConveyorBelt1_left"
    # "https://www.sfb1574.kit.edu/ontologies/DemoStructureInstance#NodeBInstance"
)


def main():
    logger = logging.getLogger("demo_script")
    logger.setLevel(logging.DEBUG)

    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(credentials=credentials)
    db.logger.setLevel(logging.DEBUG)
    ogm = OGM(db=db, loader_func=loader_eh, builder_func=minimal_builder)

    node = ogm.create_node(id=NODE_ID)
    logger.debug(f"Node created:\n\t\t{node}")

    node_model = node.build()
    logger.debug(f"Node built:\n\t\t{node_model}")

    loaded_instance = node.load()
    logger.debug(
        f"Node loaded:\n\t\t{json.dumps(loaded_instance.model_dump(), indent=4)}"
    )

    data_model = aas.DataModel.from_models(node.instance)

    middleware = aas.AasMiddleware()
    middleware.load_data_model(
        name=NODE_ID.fragment, data_model=data_model, persist_instances=True
    )
    middleware.generate_rest_api_for_data_model(NODE_ID.fragment)
    uvicorn.run(middleware.app)


if __name__ == "__main__":
    main()
