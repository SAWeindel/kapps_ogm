import os
import logging
import json

from kapps_triplestore_interface import GraphDBCredentials, GraphDB, IRI

from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
from kapps_ogm.utils.json_ogm_encoder import OGMEncoder


# Original TransferUnit property chains (commented out)
# property_chains = [
#     [
#         IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"),
#     ],
#     [
#         IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier"),
#     ],
# ]
# instance_iri = IRI(
#     "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#TransferUnit1"
# )
# class_iri = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")

# FlexConveyor property chains
property_chains = [
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
        IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo"),
    ],
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection"),
    ],
]
instance_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#TestModule1")
class_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule")


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
    ogm = OGM(db=db)
    ogm.logger.setLevel(logging.DEBUG)

    # Convert property_chains to ClassScope
    class_scope = ClassScope.from_property_chains(property_chains)

    # Create blank instance
    blank_instance = ogm.create_blank_instance(
        instance_iri=instance_iri,
        class_iri=class_iri,
        class_scope=class_scope,
    )

    print("\n=== Blank Instance (Lined JSON - Python/Pydantic safe keys) ===")
    print(json.dumps(blank_instance.model_dump(), indent=4))

    print("\n=== Blank Instance (Pretty JSON - Full IRI display) ===")
    print(json.dumps(blank_instance, indent=4, cls=OGMEncoder))


if __name__ == "__main__":
    main()
