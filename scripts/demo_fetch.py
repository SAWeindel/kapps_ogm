import copy
import os
import logging
import json

from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from kapps_ogm.node.core import Node
from kapps_ogm.ogm import OGM
from kapps_ogm.utils.json_ogm_encoder import OGMEncoder
from kapps_ogm.utils.pretty_print import format_triples_turtle
from kapps_ogm.utils.class_scope import ClassScope


class_iri = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")

# Mock data from demo_from_data
mock_data = {
    "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#TransferUnitFromData1",
    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorBelt": [
        {
            "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#ConveyorBeltFromData1",
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_isWorking": [
                True
            ],
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorPosition": [
                {
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_CrcInterfaces_h_hasValue": [
                        1.25
                    ],
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasUnit": [
                        "meter"
                    ],
                }
            ],
        }
    ],
    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasLightBarrier": [
        {
            "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#LightBarrierFromData1",
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_isOccupied": [
                {
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_CrcInterfaces_h_hasValue": [
                        False
                    ],
                }
            ],
        }
    ],
}


def _scope_from_data(ogm: OGM, data: dict) -> ClassScope:
    temp_node = Node(data=copy.deepcopy(data), ogm=ogm)
    return ClassScope.from_node_data(temp_node)


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
    ogm = OGM(db=db)
    ogm.logger.setLevel(logging.DEBUG)

    print("Clearing default graph...")
    cleared = db.clear_graph()
    print(f"Default graph cleared: {cleared}")

    # Derive class_scope from the mock data
    class_scope = _scope_from_data(ogm, mock_data)

    # Create the node and persist it to the database
    created_node = ogm.create(
        class_iri=class_iri,
        data=mock_data,
        class_scope=class_scope,
        persist=True,
    )
    print("\n=== Created Node ===")
    print(f"Node ID: {created_node.id}")

    # Fetch the node back from the database
    fetched_node = ogm.fetch(
        instance_iri=created_node.id,
        class_spec=created_node.class_spec,
        class_scope=class_scope,
        materialize=True,
    )

    # Print in JSON format (instance model_dump)
    print("\n=== Fetched Node (Lined JSON - Python/Pydantic safe keys) ===")
    print(json.dumps(fetched_node.instance.model_dump(), indent=4))

    # Print in Pretty JSON format (full IRIs)
    print("\n=== Fetched Node (Pretty JSON - Full IRI display) ===")
    print(json.dumps(fetched_node.instance, indent=4, cls=OGMEncoder))

    # Print in JSON-LD format
    print("\n=== Fetched Node as JSON-LD ===")
    print(json.dumps(fetched_node.to_json_ld(), indent=4))

    # Print as triples
    print("\n=== Fetched Node as Triples ===")
    print(format_triples_turtle(fetched_node.to_triples()))

    print("\nClearing default graph after demo...")
    cleared_post = db.clear_graph()
    print(f"Default graph cleared: {cleared_post}")


if __name__ == "__main__":
    main()
