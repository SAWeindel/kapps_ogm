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

# The triple-level diff this commit sends to the store, logged at DEBUG by OGM.commit.
# Note it is smaller than the data change suggests, because since #6 an anonymous node
# carries a Skolem IRI that survives a write: the position node keeps its address, so
# replacing its value is a one-triple swap rather than tearing the whole complex
# attribute down and rebuilding it. hasConveyorPosition and hasUnit are never touched.
#
# --- removed (2) ---
# <genid/A> hasValue 1.25
# ConveyorBeltFromData1 isWorking true
#
# --- added (5) ---
# <genid/A> hasValue -1.25                       # same node as above, not a new one
# <genid/B> hasValue 1.23
# <genid/B> hasUnit "meter_per_second"
# ConveyorBeltFromData1 isWorking false
# ConveyorBeltFromData1 hasConveyorSpeed <genid/B>
#
# The two "Diff for ..." lines the script prints are a different comparison: input data
# against fetched payload. <empty> there is the pass condition, meaning the round trip
# returned exactly what was written.


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


class _DiffCapture(logging.Handler):
    """Collects the one DEBUG record in which OGM.commit reports its triple diff."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "Updating instance" in message:
            self.messages.append(message)


def _commit_printing_triple_diff(ogm: OGM, instance_iri: IRI, data: dict) -> Node:
    """Commit `data`, printing the triple-level diff the write actually sends.

    The "Diff for ..." comparisons check intent against result — that what came back out
    equals what went in — so they say nothing about what *changed* in the store, which is
    where the interesting behaviour is. OGM.commit already computes that diff and logs it
    at DEBUG, so this captures the record rather than recomputing it here and drifting
    from what is really written.
    """
    capture = _DiffCapture()
    previous_level = ogm.logger.level
    ogm.logger.setLevel(logging.DEBUG)
    ogm.logger.addHandler(capture)
    try:
        node = ogm.commit(instance_iri=instance_iri, data=data)
    finally:
        ogm.logger.removeHandler(capture)
        ogm.logger.setLevel(previous_level)

    for message in capture.messages:
        print(f"\n{message}")
    return node


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

    new_node = _commit_printing_triple_diff(
        ogm, instance_iri=old_node.id, data=new_data
    )

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
