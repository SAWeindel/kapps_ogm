import os
import json
import pytest
import deepdiff

from graph_db_interface import IRI
from circular_factory_ogm.ogm import OGM

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

    node = ogm.create(
        class_iri=class_iri,
        property_chains=property_chains,
        data=data,
        persist=True,
    )

    node_fetched = ogm.fetch(
        instance_iri=node.id,
        property_chains=property_chains,
        materialize=True,
    )

    verified_data = node.to_json_ld()
    fetched_data = node_fetched.to_json_ld()

    diff = deepdiff.DeepDiff(verified_data, fetched_data, ignore_order=True)
    assert diff == {}
