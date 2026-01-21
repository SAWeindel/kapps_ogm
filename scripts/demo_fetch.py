import os
import logging
import json
import pydantic as pd

import uvicorn
import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.utils.json_ogm_encoder import OGMEncoder
from circular_factory_ogm.utils.pretty_print import format_triples_turtle


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
class_iri = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")


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
    ogm = OGM(db=db, loader=None)
    ogm.logger.setLevel(logging.DEBUG)
    node = ogm.fetch(
        instance_iri=instance_iri, property_chains=property_chains, materialize=True
    )
    print("=== Fetched Node Triples ===")
    print(format_triples_turtle(node.to_triples()))
    print("\n=== Fetched Node Data ===")
    print(json.dumps(node.data, indent=4, cls=OGMEncoder))
    print("\n=== Fetched Node Instance ===")
    print(json.dumps(node.instance, indent=4, cls=OGMEncoder))

    node2 = ogm.create(
        class_iri=class_iri,
        property_chains=property_chains,
        data=node.data,
        persist=True,
    )

    print(json.dumps(node2.to_triples(), indent=4, cls=OGMEncoder))
    print(json.dumps(node2.data, indent=4, cls=OGMEncoder))

    pass


if __name__ == "__main__":
    main()
