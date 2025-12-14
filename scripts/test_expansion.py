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
    class_spec = specify(class_iri=NODE_ID, ogm=ogm)
    print("ClassSpec:")
    print(class_spec.to_string())

    # Create Pydantic model from ClassSpec and dump JSON Schema
    model_cls = class_spec.to_pydantic_model()
    schema = model_cls.model_json_schema()
    print("\nPydantic model JSON Schema:")
    print(json.dumps(schema, indent=2))

    # Next: fully hydrate nested classes (ConveyorBelt, LightBarrier) and dump schemas
    conveyor_belt_iri = IRI(
        "https://www.sfb1574.kit.edu/ontologies/TransferUnit#ConveyorBelt"
    )
    light_barrier_iri = IRI(
        "https://www.sfb1574.kit.edu/ontologies/TransferUnit#LightBarrier"
    )

    cb_spec = specify(class_iri=conveyor_belt_iri, ogm=ogm)
    lb_spec = specify(class_iri=light_barrier_iri, ogm=ogm)

    print("\nConveyorBelt ClassSpec:")
    print(cb_spec.to_string())
    try:
        cb_model = cb_spec.to_pydantic_model()
        cb_schema = cb_model.model_json_schema()
        print("\nConveyorBelt JSON Schema:")
        print(json.dumps(cb_schema, indent=2))
    except Exception as e:
        print(f"\nConveyorBelt JSON Schema generation failed: {e}")

    print("\nLightBarrier ClassSpec:")
    print(lb_spec.to_string())
    try:
        lb_model = lb_spec.to_pydantic_model()
        lb_schema = lb_model.model_json_schema()
        print("\nLightBarrier JSON Schema:")
        print(json.dumps(lb_schema, indent=2))
    except Exception as e:
        print(f"\nLightBarrier JSON Schema generation failed: {e}")

    # node = ogm.create_node(id=NODE_ID)
    # classify_outgoing_properties(node)


if __name__ == "__main__":
    main()
