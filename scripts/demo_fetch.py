import os
import logging
import json
import pydantic as pd

import uvicorn
import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.loaders.loader_eh import loader_eh
# property_chains = [
#     [
#         IRI("https://.../TransferUnit#hasConveyorBelt"),
#         IRI("https://.../TransferUnit#hasConveyorPosition"),
#     ],
#     [
#         IRI("https://.../TransferUnit#hasConveyorBelt"),
#         IRI("https://.../TransferUnit#hasConveyorSpeed"),
#     ],
# ]'
property_chains = [
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"),
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorPosition"),
    ],
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"),
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorSpeed"),
    ],
]
instance_iri = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#TransferUnit1"
)


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,  
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get root logger
    logger = logging.getLogger()

    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(credentials=credentials)

    # Refactored OGM: pass loader only
    ogm = OGM(db=db, loader=None, logger=logger)
    node = ogm.fetch(
        instance_iri=instance_iri, property_chains=property_chains, materialize=True
    )
    print(node.instance.model_dump_json(indent=4))




if __name__ == "__main__":
    main()
