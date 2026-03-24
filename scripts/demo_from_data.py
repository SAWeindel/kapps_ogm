import copy
import difflib
import os
import logging
import json

from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from kapps_ogm.node.core import Node
from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope

PATH = os.path.dirname(os.path.abspath(__file__))

class_iri = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")

old_data = {
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
# in the new test data, the nested class instance iris are not transferred.
# This means that the nested instances will be created anew with new IRIs
new_data = {
    "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#TransferUnitFromData1",
    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorBelt": [
        {
            "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#ConveyorBeltFromData1",
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_isWorking": [
                False  # Value changed, was True -> Simple attribute to be updated
            ],
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorPosition": [
                {
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_CrcInterfaces_h_hasValue": [
                        -1.25  # Value changed, was 1.25 -> Whole complex attribute needs to be replaced
                    ],
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasUnit": [
                        "meter"
                    ],
                }
            ],
            # hasConveyorSpeed added -> New complex attribute to be added
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorSpeed": [
                {
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_CrcInterfaces_h_hasValue": [
                        1.23
                    ],
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasUnit": [
                        "meter_per_second"
                    ],
                }
            ],
        }
    ],
    # Note: Light barrier instance omitted -> OWA says that we CAN NOT delete it
}

# We want to see diff:
# --- removed ---
# ConveyorBeltFromData1 isWorking True
# ConveyorBeltFromData1 hasConveyorPosition ?A
# ?A hasValue 1.25
# ?A hasUnit "meter"
#
# --- added ---
# ConveyorBeltFromData1 isWorking False
# ConveyorBeltFromData1 hasConveyorSpeed ?B
# ?B hasValue 1.23
# ?B hasUnit "meter_per_second"
# ConveyorBeltFromData1 hasConveyorPosition ?C
# ?C hasValue -1.25
# ?C hasUnit "meter"


def _sorted_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _print_diff(label: str, expected: dict, actual: dict) -> None:
    expected_json = _sorted_json(expected)
    actual_json = _sorted_json(actual)
    diff_lines = list(
        difflib.unified_diff(
            expected_json.splitlines(),
            actual_json.splitlines(),
            fromfile=f"{label}_expected",
            tofile=f"{label}_actual",
            lineterm="",
        )
    )
    if diff_lines:
        print(f"\nDiff for {label}:\n" + "\n".join(diff_lines))
    else:
        print(f"\nDiff for {label}: <empty>")


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
    # db.logger.setLevel(logging.DEBUG)
    ogm = OGM(db=db)
    ogm.logger.setLevel(logging.INFO)

    print("Clearing default graph...")
    cleared = db.clear_graph()
    print(f"Default graph cleared: {cleared}")

    old_class_scope = _scope_from_data(ogm, old_data)
    new_class_scope = _scope_from_data(ogm, new_data)

    old_node = ogm.create(
        class_iri=class_iri,
        data=old_data,
        class_scope=old_class_scope,
        persist=True,
    )

    fetched_before_update = ogm.fetch(
        instance_iri=old_node.id,
        class_spec=old_node.class_spec,
        class_scope=old_class_scope,
        materialize=True,
    )
    fetched_before_payload = fetched_before_update.instance.model_dump()
    fetched_before_json = _sorted_json(fetched_before_payload)
    print("\nFetched node before update:")
    print(fetched_before_json)

    _print_diff("before_update", old_data, fetched_before_payload)

    new_node = ogm.commit(instance_iri=old_node.id, data=new_data)

    fetched_after_update = ogm.fetch(
        instance_iri=old_node.id,
        class_spec=new_node.class_spec,
        class_scope=new_class_scope,
        materialize=True,
    )
    fetched_after_payload = fetched_after_update.instance.model_dump()
    fetched_after_json = _sorted_json(fetched_after_payload)
    print("\nFetched node after update:")
    print(fetched_after_json)

    _print_diff("after_update", new_data, fetched_after_payload)

    print("\nClearing default graph after demo...")
    cleared_post = db.clear_graph()
    print(f"Default graph cleared: {cleared_post}")


if __name__ == "__main__":
    main()
