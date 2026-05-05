import copy
import os
import logging
import json

from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope

DEMO = "http://demo.org/TransferUnit"
DEMO_GRAPH = IRI("http://demo.org/TransferUnitInstances")

class_iri = IRI("TransferUnit", DEMO)

initial_data = {
    IRI("hasConveyorBelt", DEMO): [
        {
            IRI("isWorking", DEMO): [True],
            IRI("hasConveyorPosition", DEMO): [
                {
                    IRI("hasValue", DEMO): [1.25],
                    IRI("hasUnit", DEMO): ["meter"],
                }
            ],
        }
    ]
}


def setup_demo(ogm: OGM) -> IRI:
    print("Clearing default graph...")
    assert ogm.db.clear_graph(DEMO_GRAPH)

    class_scope = ClassScope.from_data_dict(initial_data)

    created_node = ogm.create(
        class_iri=class_iri,
        data=initial_data,
        class_scope=class_scope,
        persist=True,
    )
    instance_iri = created_node.id
    print(f"\n=== Created instance: {instance_iri} ===")
    print(json.dumps(created_node.instance.model_dump(), indent=4))
    return instance_iri


def main():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="Hackathon",
    )
    db = GraphDB(credentials=credentials)
    ogm = OGM(db=db)
    instance_iri = setup_demo(ogm)

    class_scope = ClassScope.from_data_dict(initial_data)

    # --- 1. Fetch the instance from the DB ---
    fetched_node = ogm.fetch(
        instance_iri=instance_iri,
        class_scope=class_scope,
        materialize=True,
    )
    print("\n=== Fetched instance ===")
    print(json.dumps(fetched_node.instance.model_dump(), indent=4))

    # --- 2. Modify a value in the fetched data ---
    updated_data = fetched_node.instance.model_dump()

    BELT_KEY = IRI("hasConveyorBelt", DEMO).lined
    POSITION_KEY = IRI("hasConveyorPosition", DEMO).lined
    VALUE_KEY = IRI("hasValue", DEMO).lined

    new_speed = 1.5
    updated_data[BELT_KEY][0][POSITION_KEY][0][VALUE_KEY][0] = new_speed
    print(f"\n=== Updating conveyor speed to {new_speed} ===")

    # --- 3. Commit the updated data back to the DB ---
    updated_node = ogm.commit(
        instance_iri=instance_iri,
        data=updated_data,
    )
    print("\n=== Committed updated instance ===")
    print(json.dumps(updated_node.instance.model_dump(), indent=4))


if __name__ == "__main__":
    main()
