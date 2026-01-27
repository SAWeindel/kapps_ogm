import os
import json
import pytest
import deepdiff

from graph_db_interface import IRI
from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.utils.class_scope import ClassScope

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_data")

TEST_CASES = [
    (
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit"),
        [
            [
                IRI(
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"
                ),
            ],
            [
                IRI(
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier"
                ),
            ],
        ],
        "TransferUnit1_data.json",
    ),
]


@pytest.mark.parametrize("class_iri, property_chains, data_json_name", TEST_CASES)
def test_roundtrip(
    class_iri: IRI,
    property_chains: list[list[IRI]],
    data_json_name: str,
    ogm: OGM,
):
    data = json.load(open(os.path.join(DATA_DIR, data_json_name), "r"))

    # Convert property_chains to ClassScope
    class_scope = ClassScope.from_property_chains(property_chains=property_chains)

    node = ogm.create(
        class_iri=class_iri,
        class_scope=class_scope,
        data=data,
        persist=True,
    )

    node_fetched = ogm.fetch(
        instance_iri=node.id,
        class_scope=class_scope,
        materialize=True,
    )

    verified_data = node.to_json_ld()
    fetched_data = node_fetched.to_json_ld()

    diff = deepdiff.DeepDiff(verified_data, fetched_data, ignore_order=True)
    assert diff == {}
