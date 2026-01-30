import os
import logging
import json

from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.utils.class_scope import ClassScope
from circular_factory_ogm.utils.json_ogm_encoder import OGMEncoder

PATH = os.path.dirname(os.path.abspath(__file__))

class_iri = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")

old_data = {
    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorBelt": [
        {
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_isWorking": [
                True
            ],
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
        }
    ],
    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasLightBarrier": [
        {
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
    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorBelt": [
        {
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_isWorking": [
                True
            ],
            "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasConveyorPosition": [
                {
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_CrcInterfaces_h_hasValue": [
                        -1.25
                    ],
                    "https_c__s__s_www_d_sfb1574_d_kit_d_edu_s_ontologies_s_TransferUnit_h_hasUnit": [
                        "meters"
                    ],
                }
            ],
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
    ]
}


def main():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(credentials=credentials)
    # db.logger.setLevel(logging.DEBUG)
    ogm = OGM(db=db)
    ogm.logger.setLevel(logging.DEBUG)

    old_class_scope = ClassScope.from_property_chains(
        property_chains=[
            [
                IRI(
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"
                ),
                IRI(
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorPosition"
                ),
            ],
            [
                IRI(
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier"
                ),
                IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#isOccupied"),
            ],
        ]
    )

    old_node = ogm.create(
        class_iri=class_iri,
        data=old_data,
        class_scope=old_class_scope,
        persist=True,
    )
    old_node_dict = old_node.instance.model_dump()
    old_node_serialized = json.dumps(old_node_dict, indent=2)

    print("Created node:")
    print(old_node_serialized)

    new_node_serialized = old_node_serialized.replace(
        json.dumps(old_data, separators=(",", ":")),
        json.dumps(new_data, separators=(",", ":")),
    )

    new_data_dict = json.loads(new_node_serialized)

    new_node = ogm.commit(instance_iri=old_node.id, data=new_data_dict)

    print("Updated node:")
    print(json.dumps(new_node.to_json_ld(), indent=2, cls=OGMEncoder))
    pass


if __name__ == "__main__":
    main()
