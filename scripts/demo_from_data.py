import copy
import difflib
import os
import logging
import json
import sys
import textwrap

from kapps_triplestore_interface import GraphDBCredentials, GraphDB, IRI

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

# The triple-level diff step 4 prints is smaller than the data change implies, because
# since #6 an anonymous node carries a Skolem IRI that survives a write: the position node
# keeps its address, so replacing its value is a one-triple swap rather than tearing the
# whole complex attribute down and rebuilding it.
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

TOTAL_STEPS = 5
INDENT = " " * 6


def _sorted_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _banner(*lines: str) -> None:
    rule = "=" * 78
    print(f"\n{rule}")
    for line in lines:
        print(line)
    print(rule)


def _step(number: int, title: str) -> None:
    print(f"\n[{number}/{TOTAL_STEPS}] {title}")


def _note(text: str) -> None:
    """Indented prose explaining what the step above is demonstrating."""
    for line in textwrap.wrap(text, width=72):
        print(f"{INDENT}{line}")


def _check_round_trip(what: str, wrote: dict, read_back: dict) -> bool:
    """Compare what we asked the store to hold against what it handed back.

    Identical is the success condition, so it is reported as PASS rather than as an empty
    diff — "no differences" is easy to misread as "nothing happened".
    """
    diff_lines = list(
        difflib.unified_diff(
            _sorted_json(wrote).splitlines(),
            _sorted_json(read_back).splitlines(),
            fromfile="what we wrote",
            tofile="what we read back",
            lineterm="",
        )
    )
    print(f"\n{INDENT}CHECK  {what}")
    if diff_lines:
        print(f"{INDENT}       FAIL - the store did not hand back what we wrote:")
        for line in diff_lines:
            print(f"{INDENT}       {line}")
        return False
    print(f"{INDENT}       PASS - identical, so the round trip lost nothing.")
    return True


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

    The round-trip checks compare intent against result — that what came back out equals
    what went in — so they say nothing about what *changed* in the store, which is where
    the interesting behaviour is. OGM.commit already computes that diff and logs it at
    DEBUG, so this captures the record rather than recomputing it here and drifting from
    what is really written.
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
        print()
        for line in message.splitlines():
            print(f"{INDENT}{line}" if line else "")
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

    _banner(
        "kapps_ogm demo: writing and updating an instance from plain data",
        "",
        "Builds a TransferUnit from a plain dict, commits a change to it, and checks",
        "that both survive a round trip through the triple store unchanged.",
    )

    _step(1, 'Clearing the default graph of repository "OGM"')
    print(f"{INDENT}cleared: {db.clear_graph()}")

    old_class_scope = _scope_from_data(ogm, old_data)
    new_class_scope = _scope_from_data(ogm, new_data)

    _step(2, "Creating TransferUnitFromData1 from `old_data`, and persisting it")
    _note(
        "One TransferUnit holding a ConveyorBelt (isWorking, and a conveyor position "
        "of 1.25 meter) and a LightBarrier (isOccupied). The conveyor position is a "
        "complex attribute, so it lives on an anonymous node of its own."
    )
    old_node = ogm.create(
        class_iri=class_iri,
        data=old_data,
        class_scope=old_class_scope,
        persist=True,
    )
    print(f"{INDENT}created: {old_node.id}")

    _step(3, "Reading it back out of the store, materialised through its ClassSpec")
    fetched_before_update = ogm.fetch(
        instance_iri=old_node.id,
        class_spec=old_node.class_spec,
        class_scope=old_class_scope,
        materialize=True,
    )
    fetched_before_payload = fetched_before_update.instance.model_dump()
    print(_sorted_json(fetched_before_payload))
    create_ok = _check_round_trip(
        "what came back vs. the `old_data` we wrote", old_data, fetched_before_payload
    )

    _step(4, "Committing `new_data` over it")
    _note(
        "Three changes at once: isWorking True -> False, the conveyor position value "
        "1.25 -> -1.25, and a brand new hasConveyorSpeed attribute. The light barrier "
        "is left out of `new_data` entirely, and under the Open World Assumption an "
        "omission is not a deletion, so it has to survive untouched."
    )
    print()
    _note(
        "Below are the triples the commit actually sent to the store. There are fewer "
        "than the data change implies: the position node keeps the Skolem address it "
        "was given on create, so changing its value is a one-triple swap rather than a "
        "teardown and rebuild of the whole attribute. hasConveyorPosition and hasUnit "
        "are never touched."
    )
    new_node = _commit_printing_triple_diff(
        ogm, instance_iri=old_node.id, data=new_data
    )

    _step(5, "Reading it back again, now that the commit has landed")
    fetched_after_update = ogm.fetch(
        instance_iri=old_node.id,
        class_spec=new_node.class_spec,
        class_scope=new_class_scope,
        materialize=True,
    )
    fetched_after_payload = fetched_after_update.instance.model_dump()
    print(_sorted_json(fetched_after_payload))
    commit_ok = _check_round_trip(
        "what came back vs. the `new_data` we committed",
        new_data,
        fetched_after_payload,
    )

    print("\nTidying up: clearing the default graph again.")
    print(f"{INDENT}cleared: {db.clear_graph()}")

    checks = [create_ok, commit_ok]
    _banner(f"{sum(checks)}/{len(checks)} checks passed.")
    if not all(checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
