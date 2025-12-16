import os
import logging
import json

import uvicorn
import aas_middleware as aas
from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.builders.mapping.class_spec import ClassSpec
from circular_factory_ogm.loaders.loader_eh import loader_eh

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
    "id": "https://example.org/instances/transferUnit_1",
    "https_www_sfb1574_kit_edu_ontologies_TransferUnit_hasConveyorBelt": [
        {
            "https_www_sfb1574_kit_edu_ontologies_TransferUnit_hasConveyorPosition": [
                {
                    "https_www_sfb1574_kit_edu_ontologies_inf_hasValue": [1.25],
                    "https_www_sfb1574_kit_edu_ontologies_inf_hasUnit": [
                        "https://example.org/units/meter"
                    ],
                }
            ],
            "https_www_sfb1574_kit_edu_ontologies_TransferUnit_hasConveyorSpeed": [
                {
                    "https_www_sfb1574_kit_edu_ontologies_inf_hasValue": [0.75],
                    "https_www_sfb1574_kit_edu_ontologies_inf_hasUnit": [
                        "https://example.org/units/meter_per_second"
                    ],
                }
            ],
        }
    ],
    "https_www_sfb1574_kit_edu_ontologies_TransferUnit_hasLightBarrier": [
        {
            "https_www_sfb1574_kit_edu_ontologies_TransferUnit_isOccupied": [
                {
                    "https_www_sfb1574_kit_edu_ontologies_inf_hasValue": [False],
                    "https_www_sfb1574_kit_edu_ontologies_inf_hasUnit": [
                        "https://example.org/units/boolean"
                    ],
                }
            ]
        }
    ],
}


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
    db.logger.setLevel(logging.INFO)
    # Refactored OGM: pass loader only
    ogm = OGM(db=db, loader=loader_eh)

    # Specify TransferUnit with property chains - should be fully hydrated
    class_spec = ClassSpec.specify(
        class_iri=NODE_ID, ogm=ogm, property_chains=property_chains
    )
    print("TransferUnit ClassSpec (fully hydrated):")
    print(class_spec.to_string())
    with open(os.path.join(PATH, "output/transfer_unit_class_spec.txt"), "w") as f:
        f.write(class_spec.to_string())

    # Create Pydantic model from fully hydrated ClassSpec and dump JSON Schema
    model_cls = class_spec.to_pydantic_model()
    schema = model_cls.model_json_schema()
    print("\nTransferUnit Pydantic JSON Schema (with nested classes):")
    print(json.dumps(schema, indent=2))
    with open(os.path.join(PATH, "output/transfer_unit_json_schema.json"), "w") as f:
        json.dump(schema, f, indent=2)

    # node = ogm.create_node(id=NODE_ID)
    # classify_outgoing_properties(node)
    blank_instance = ogm.create_blank_instance(
        class_iri=NODE_ID,
        property_chains=property_chains,
        instance_iri="http://example.org/instances/TransferUnit1",
    )
    print("\nBlank instance of TransferUnit with nested properties:")
    print(blank_instance.model_dump_json(indent=2))
    with open(os.path.join(PATH, "output/transfer_unit_blank_instance.json"), "w") as f:
        f.write(blank_instance.model_dump_json(indent=2))

    node1 = ogm.create(
        class_iri=NODE_ID,
        data=mock_data,
        property_chains=property_chains,
    )
    node2 = ogm.create(
        class_iri=NODE_ID,
        data=mock_data,
        property_chains=property_chains,
    )
    node1.materialize()
    node2.materialize()

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
