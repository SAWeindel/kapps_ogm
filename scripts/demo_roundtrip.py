import os
import deepdiff
import logging

from kapps_triplestore_interface import IRI, GraphDBCredentials, GraphDB
from kapps_ogm.ogm import OGM

test_data = {
    "id": IRI(
        "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#TransferUnit1"
    ),
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt": [
        {
            # "id": IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#ConveyorBelt1_right"),
            # "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasNonExistingProperty": [
            #     "this field is not defined in the model and should raise an error in strict mode",
            # ],
            "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorPosition": [
                {
                    "https://www.sfb1574.kit.edu/ontologies/CrcInterfaces#hasValue": [
                        103.5
                    ],
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasUnit": [
                        "mm",
                    ],
                },
            ],
            "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorSpeed": [
                {
                    "https://www.sfb1574.kit.edu/ontologies/CrcInterfaces#hasValue": [
                        10.2,
                    ],
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasUnit": [
                        "m/s",
                    ],
                },
            ],
            "https://www.sfb1574.kit.edu/ontologies/TransferUnit#isWorking": [
                True,
            ],
        },
        {
            "id": IRI(
                "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#ConveyorBelt1_left"
            ),
            "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorPosition": [
                {
                    "https://www.sfb1574.kit.edu/ontologies/CrcInterfaces#hasValue": [
                        -0.2,
                    ],
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasUnit": [
                        "mm",
                    ],
                },
            ],
            "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorSpeed": [
                {
                    "https://www.sfb1574.kit.edu/ontologies/CrcInterfaces#hasValue": [
                        12.1
                    ],
                    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasUnit": [
                        "m/s"
                    ],
                },
            ],
            "https://www.sfb1574.kit.edu/ontologies/TransferUnit#isWorking": [
                True,
            ],
        },
    ],
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier": [
        # {
        #     "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#LightBarrier1_front",
        #     "https://www.sfb1574.kit.edu/ontologies/TransferUnit#isOccupied": [
        #         {
        #             "https://www.sfb1574.kit.edu/ontologies/CrcInterfaces#hasValue": [
        #                 True,
        #             ],
        #         },
        #     ],
        #     "https://www.sfb1574.kit.edu/ontologies/TransferUnit#isWorking": [
        #         False,
        #     ],
        # },
        # {
        #     "id": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#LightBarrier1_back",
        #     "https://www.sfb1574.kit.edu/ontologies/TransferUnit#isOccupied": [
        #         {
        #             "https://www.sfb1574.kit.edu/ontologies/CrcInterfaces#hasValue": [
        #                 False,
        #             ],
        #         },
        #     ],
        #     "https://www.sfb1574.kit.edu/ontologies/TransferUnit#isWorking": [
        #         True,
        #     ],
        # },
    ],
}

class_iri = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")
property_chains = [
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"),
    ],
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier"),
    ],
]


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
    assert db.clear_graph()  # clear default graph before running demo

    ogm = OGM(db=db, loader=None)
    ogm.logger.setLevel(logging.DEBUG)

    node = ogm.create(
        class_iri=class_iri,
        property_chains=property_chains,
        data=test_data,
        persist=True,
    )

    fetched_node = ogm.fetch(
        instance_iri=node.id,
        property_chains=property_chains,
        materialize=True,
    )

    verified_data = node.to_json_ld()
    fetched_data = fetched_node.to_json_ld()

    diff = deepdiff.DeepDiff(verified_data, fetched_data)
    print(diff)
    assert diff == {}


main()
