"""Shared fixtures for unit tests."""

import pytest
from typing import Dict, Any
from unittest.mock import Mock, MagicMock

from graph_db_interface import GraphDB, IRI
from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.node.core import Node


# Test data constants
TRANSFER_UNIT_IRI = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit"
)
INSTANCE_IRI = IRI("https://example.org/instances/transfer_unit_001")
RDF_TYPE = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

PROPERTY_CHAINS = [
    [IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt")],
    [IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier")],
]

HAS_CONVEYOR_BELT = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"
)
HAS_CONVEYOR_SPEED = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorSpeed"
)
HAS_VALUE = IRI("https://www.sfb1574.kit.edu/ontologies/CrcInterfaces#hasValue")
HAS_UNIT = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasUnit")

MOCK_INSTANCE_DATA = {
    HAS_CONVEYOR_BELT.lined: [
        {
            HAS_CONVEYOR_SPEED.lined: [
                {
                    HAS_VALUE.lined: [1.5],
                    HAS_UNIT.lined: ["m/s"],
                }
            ]
        }
    ]
}


@pytest.fixture
def mock_db():
    """Create a mock GraphDB instance."""
    db = Mock(spec=GraphDB)
    db.triples_get = Mock(return_value=[])
    db.iri_exists = Mock(return_value=False)
    db.owl_is_named_individual = Mock(return_value=False)
    return db


@pytest.fixture
def ogm_with_mock_db(mock_db):
    """Create an OGM instance with a mocked database."""
    from circular_factory_ogm.loaders.loader_eh import loader_eh

    ogm = OGM(
        db=mock_db,
        loader=loader_eh,
    )
    return ogm


@pytest.fixture
def simple_class_spec():
    """Create a simple ClassSpec for testing."""
    # Create a minimal mock ClassSpec without database queries
    class_spec = Mock(spec=ClassSpec)
    class_spec.iri = TRANSFER_UNIT_IRI
    class_spec.properties = {}
    return class_spec


@pytest.fixture
def mock_node(ogm_with_mock_db, simple_class_spec):
    """Create a mock Node without loading data."""
    node = Node(
        id=INSTANCE_IRI,
        class_spec=simple_class_spec,
        ogm=ogm_with_mock_db,
    )
    return node
