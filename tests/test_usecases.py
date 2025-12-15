import pytest

import aas_middleware as aas
from graph_db_interface import GraphDB, IRI

from circular_factory_ogm.loaders.minimal_loader import minimal_loader
from circular_factory_ogm.builders.minimal_builder import minimal_builder
from circular_factory_ogm.ogm import OGM

IRI.add_prefix("ds", "https://www.sfb1574.kit.edu/ontologies/DemoStructure#")
IRI.add_prefix("dsi", "https://www.sfb1574.kit.edu/ontologies/DemoStructureInstance#")

NODEA_LEVEL0 = {
    "id": IRI("dsi:NodeAInstance"),
}

NODEA_LEVEL1 = {
    "id": IRI("dsi:NodeAInstance"),
    IRI("rdf:type"): {  # Node
        "id": IRI("ds:NodeA"),
    },
    IRI("rdfs:label"): "Node A",
    IRI("ds:hasNodeB"): {  # Node
        "id": IRI("dsi:NodeBInstance"),
    },
    IRI("ds:hasAttributeA"): "Attribute A Content",
    IRI("ds:hasAttributeA2"): 3.14,
}

NODEB_LEVEL0 = {
    "id": IRI("dsi:NodeBInstance"),
}

NODEB_LEVEL1 = {
    "id": IRI("dsi:NodeBInstance"),
    IRI("rdf:type"): {  # Node
        "id": IRI("ds:NodeB"),
    },
    IRI("ds:hasNodeC"): {  # Node
        "id": IRI("dsi:NodeCInstance"),
    },
    IRI("ds:hasBlankAttribute"): {  # Dict
        IRI("ds:hasValue"): "Blank Attribute Content",
        IRI("ds:hasNumber"): 123,
    },
    IRI("ds:hasAttributeB"): "Attribute B Content",
}


def test_class_failing(db: GraphDB):
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)
    with pytest.raises(Exception):
        ogm.create_node(id=IRI("ds:NodeA"))


def test_reference(db: GraphDB):
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)

    node = ogm.create_node(id=IRI("dsi:NodeAInstance"))

    assert node.id == IRI("dsi:NodeAInstance")
    assert node.data == NODEA_LEVEL0

    assert node.model is None
    assert node.instance is None
    assert not node.is_loaded

    data_model = aas.DataModel.from_models(node)

    model_dict = data_model.model_dump()
    assert model_dict == {
        "id": IRI("dsi:NodeAInstance")
    }  # ==repr(node.instance) what should be eq to repr(node)


def test_build(db: GraphDB):
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)

    node = ogm.create_node(id=IRI("dsi:NodeAInstance"))
    built_model = node.build()

    assert node.id == IRI("dsi:NodeAInstance")
    assert node.model == built_model
    assert issubclass(node.model, aas.DataModel)

    assert node.data is None
    assert node.instance is None
    assert not node.is_loaded

    data_model = aas.DataModel.from_models(node)

    model_dict = data_model.model_dump()
    assert model_dict == {"id": IRI("dsi:NodeAInstance")}  # because not loaded yet


def test_load(db: GraphDB):
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)

    node = ogm.create_node(id=IRI("dsi:NodeAInstance"))
    loaded_instance = node.load()

    assert node.id == IRI("dsi:NodeAInstance")
    assert node.data == NODEA_LEVEL1
    assert node.instance == loaded_instance
    assert issubclass(node.model, aas.DataModel)
    assert node.is_loaded

    node_data_model = aas.DataModel.from_models(node)
    instance_data_model = aas.DataModel.from_models(loaded_instance)

    node_model_dict = node_data_model.model_dump()
    instance_model_dict = instance_data_model.model_dump()

    assert node_model_dict == NODEA_LEVEL1
    assert node_model_dict == instance_model_dict


def test_load_more(db: GraphDB):
    ogm = OGM(db=db, loader_func=minimal_loader, builder_func=minimal_builder)

    node = ogm.create_node(id=IRI("dsi:NodeAInstance"))
    loaded_instance = node.load()

    assert node.id == IRI("dsi:NodeAInstance")
    assert node.data == NODEA_LEVEL1
    assert node.model is not None
    assert node.instance is not None
    assert node.is_loaded

    data_model = aas.DataModel.from_models(loaded_instance)

    model_dict = data_model.model_dump()
    assert (
        model_dict == NODEA_LEVEL1
    )  # ==repr(node.instance) what should be eq to repr(node)

    node2 = None  # getattr(node, CHILD_PROPERTY)

    assert node2.id == IRI("dsi:AttachedInstance")
    assert node2.data == {"id": IRI("dsi:AttachedInstance")}

    assert node2.model is None
    assert node2.instance is None
    assert not node2.is_loaded

    loaded_instance2 = node2.load()

    assert node2.id == IRI("dsi:AttachedInstance")
    assert node2.data == {"id": IRI("dsi:AttachedInstance")}
    assert node2.model is not None
    assert node2.instance is not None
    assert node2.is_loaded
