import pytest

import aas_middleware as aas
from graph_db_interface import GraphDB

from circular_factory_ogm.loaders.minimal_loader import minimal_loader
from circular_factory_ogm.builders.minimal_builder import minimal_builder
from circular_factory_ogm.ogm import OGM

CLASS_ID = "https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit"
INSTANCE_ID = (
    "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#TransferUnit1"
)

REFERENCE_DICT = {
    "id": INSTANCE_ID,
}

FIRST_LEVEL_DICT = {
    "id": INSTANCE_ID,
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type": "http://www.w3.org/2002/07/owl#Class",
    "http://www.w3.org/2000/01/rdf-schema#label": "Transfer Unit",
    "http://www.w3.org/2000/01/rdf-schema#subClassOf": "https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit",
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt": {
        "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnit#ConveyorBelt"
    },
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier": {
        "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnit#LightBarrier"
    },
}


def test_class_failing(db: GraphDB):
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)
    with pytest.raises(Exception):
        ogm.create_node(id=CLASS_ID)


def test_reference(db: GraphDB, mw: aas.AasMiddleware):
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)

    node = ogm.create_node(id=INSTANCE_ID)

    assert node.id == INSTANCE_ID
    assert node.data == REFERENCE_DICT

    assert not node.is_loaded
    assert node.model is None
    assert node.instance is None

    data_model = aas.DataModel.from_models(node.instance)

    model_dict = data_model.model_dump()
    assert model_dict == {"id": INSTANCE_ID}


def test_load(db: GraphDB):
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)

    node = ogm.create_node(id=INSTANCE_ID)
    loaded_instance = node.load()

    assert node.id == INSTANCE_ID
    assert node.is_loaded
    assert node.data == FIRST_LEVEL_DICT

    assert node.model is not None
    assert node.instance is not None

    data_model = aas.DataModel.from_models(loaded_instance)

    model_dict = data_model.model_dump()
    assert model_dict == FIRST_LEVEL_DICT
