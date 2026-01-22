import os
import logging
import json
from copy import deepcopy

import uvicorn
import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.utils.json_ogm_encoder import OGMEncoder
from circular_factory_ogm.utils.pretty_print import format_triples_turtle

PATH = os.path.dirname(os.path.abspath(__file__))

NODE_ID = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit"
    # "https://www.sfb1574.kit.edu/ontologies/DemoStructureInstance#NodeB"
    # "https://www.sfb1574.kit.edu/ontologies/examples#TopLevelEntity"
)
property_chains = [
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"),
    ],
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier"),
    ],
]

mock_data = {
    # "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#TransferUnit1",
    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorBelt": [
        {
            # "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#ConveyorBelt1_left",
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorPosition": [
                {
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_CrcInterfaces_h_hasValue": [
                        1.25
                    ],
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasUnit": [
                        "meters"
                    ],
                }
            ],
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorSpeed": [
                {
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_CrcInterfaces_h_hasValue": [
                        0.75
                    ],
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasUnit": [
                        "meter_per_second"
                    ],
                }
            ],
        }
    ],
    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasLightBarrier": [
        {
            # "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#LightBarrier1_front",
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


def main():
    logger = logging.getLogger()
    logger.setLevel(logging.ERROR)

    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(credentials=credentials)
    db.logger.setLevel(logging.ERROR)
    ogm = OGM(db=db)

    # Specify TransferUnit with property chains - should be fully hydrated
    class_spec = ClassSpec.specify(
        class_iri=NODE_ID, ogm=ogm, property_chains=property_chains
    )
    # print("TransferUnit ClassSpec (fully hydrated):")
    # print(class_spec.to_string())
    with open(os.path.join(PATH, "output/transfer_unit_class_spec.txt"), "w") as f:
        f.write(class_spec.to_string())

    # Create Pydantic model from fully hydrated ClassSpec and dump JSON Schema
    model_cls = class_spec.to_pydantic_model()
    schema = model_cls.model_json_schema()
    # print("\nTransferUnit Pydantic JSON Schema (with nested classes):")
    # print(json.dumps(schema, indent=2))
    with open(os.path.join(PATH, "output/transfer_unit_json_schema.json"), "w") as f:
        json.dump(schema, f, indent=2)

    blank_instance = ogm.create_blank_instance(
        class_iri=NODE_ID,
        property_chains=property_chains,
        instance_iri="http://example.org/instances/TransferUnit1",
    )
    # print("\nBlank instance of TransferUnit with nested properties:")
    # print(blank_instance.model_dump_json(indent=2))
    with open(os.path.join(PATH, "output/transfer_unit_blank_instance.json"), "w") as f:
        f.write(blank_instance.model_dump_json(indent=2))

    node1 = ogm.create(
        class_iri=NODE_ID,
        data=deepcopy(mock_data),  # is modified by adding ids
        property_chains=property_chains,
    )
    node2 = ogm.create(
        class_iri=NODE_ID,
        data=deepcopy(mock_data),  # is modified by adding ids
        property_chains=property_chains,
        persist=True,
        named_graph=IRI(
            "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances_generated"
        ),
    )
    node1.materialize()
    node2.materialize()
    node_1_instance = node1.instance
    print("\nMaterialized instance of node1:")
    print(json.dumps(node_1_instance, indent=2, cls=OGMEncoder))
    with open(os.path.join(PATH, "output/transfer_unit_node1_instance.json"), "w") as f:
        f.write(json.dumps(node_1_instance, indent=2, cls=OGMEncoder))

    # Test to_triples
    triples = node1.to_triples()
    print("Generated triples:")
    print(format_triples_turtle(triples))
    print(f"\nTotal: {len(triples)} triples\n")

    # Test to_json_ld
    json_ld = node1.to_json_ld(
        context={
            "ex": "https://example.org/",
            "tu": "https://www.sfb1574.kit.edu/ontologies/TransferUnit#",
            "tui": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#",
            "inf": "https://www.sfb1574.kit.edu/ontologies/Crcinterfaces#",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "owl": "http://www.w3.org/2002/07/owl#",
        }
    )
    print("\nJSON-LD representation:")
    print(json.dumps(json_ld, indent=2))

    print("\n JSON-LD Without Context:  ")
    json_ld_no_context = node1.to_json_ld(context=None)
    print(json.dumps(json_ld_no_context, indent=2))

    # Exit early to avoid starting the server

    middleware = aas.AasMiddleware()
    middleware.load_data_model(
        name=node1.id,
        data_model=aas.DataModel.from_models(node1.instance),
        persist_instances=True,
    )
    middleware.load_data_model(
        name=node2.id,
        data_model=aas.DataModel.from_models(node2.instance),
        persist_instances=True,
    )
    middleware.generate_rest_api_for_data_model(node1.id)
    middleware.generate_rest_api_for_data_model(node2.id)
    uvicorn.run(middleware.app)


if __name__ == "__main__":
    main()
