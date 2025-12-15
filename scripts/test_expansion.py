import os
import uvicorn
import logging
import json

import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.builders.mapping.class_spec import ClassSpec, specify
from circular_factory_ogm.loaders.minimal_loader import minimal_loader
from circular_factory_ogm.loaders.loader_eh import loader_eh
from circular_factory_ogm.builders.mapping.class_spec import (
    classify_outgoing_properties,
)

NODE_ID = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit"
    # "https://www.sfb1574.kit.edu/ontologies/DemoStructureInstance#NodeB"
    # "https://www.sfb1574.kit.edu/ontologies/examples#TopLevelEntity"
)
property_chains = [
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"),
    ],
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier"),
    ],
]


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
    # Refactored OGM: pass loader only
    ogm = OGM(db=db, loader=loader_eh)

    # Specify TransferUnit with property chains - should be fully hydrated
    class_spec = specify(class_iri=NODE_ID, ogm=ogm, property_chains=property_chains)
    print("TransferUnit ClassSpec (fully hydrated):")
    print(class_spec.to_string())

    # Create Pydantic model from fully hydrated ClassSpec and dump JSON Schema
    model_cls = class_spec.to_pydantic_model()
    schema = model_cls.model_json_schema()
    print("\nTransferUnit Pydantic JSON Schema (with nested classes):")
    print(json.dumps(schema, indent=2))

    # node = ogm.create_node(id=NODE_ID)
    # classify_outgoing_properties(node)
    blank_instance = ogm.create_blank_instance(
        class_iri=NODE_ID,
        property_chains=property_chains,
        instance_iri="http://example.org/instances/TransferUnit1",
    )
    print("\nBlank instance of TransferUnit with nested properties:")
    print(blank_instance.model_dump_json(indent=2))
if __name__ == "__main__":
    main()



