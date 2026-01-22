import os
import logging
import json

from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.utils.json_ogm_encoder import OGMEncoder
from circular_factory_ogm.utils.pretty_print import format_triples_turtle


# property_chains = [
#     # [
#     #     IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"),
#     #     # IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorPosition"),
#     # ],
#     # [
#     #     IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier"),
#     #     # IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorSpeed"),
#     # ],
# ]
# instance_iri = IRI(
#     "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#TransferUnit1"
# )
# class_iri = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")

property_chains = [
    [
        IRI("https://www.sfb1574.kit.edu/ontologies/DemoStructure#hasNodeB"),
        IRI("https://www.sfb1574.kit.edu/ontologies/DemoStructure#hasNodeC"),
    ]
]
instance_iri = IRI(
    "https://www.sfb1574.kit.edu/ontologies/DemoStructureInstance#NodeAInstance1"
)
class_iri = IRI("https://www.sfb1574.kit.edu/ontologies/DemoStructure#NodeA")


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get root logger
    logger = logging.getLogger()

    credentials = GraphDBCredentials(
        base_url="https://graphdb.iam-mms.kit.edu/",
        username=os.getenv("GRAPHDB_USERNAME"),
        password=os.getenv("GRAPHDB_PASSWORD"),
        repository="OGM",
    )
    db = GraphDB(credentials=credentials)

    # Refactored OGM: pass loader only
    ogm = OGM(db=db, loader=None)
    ogm.logger.setLevel(logging.DEBUG)
    node = ogm.fetch(
        instance_iri=instance_iri,
        property_chains=property_chains,
        materialize=True,
    )
    print("=== Fetched Minimal Node Triples ===")
    print(format_triples_turtle(node.to_triples()))
    print("\n=== Fetched Minimal Node JSON ===")
    print(json.dumps(node, indent=4, cls=OGMEncoder))
    print("\n=== Fetched Minimal Node Instance ===")
    print(json.dumps(node.instance, indent=4, cls=OGMEncoder))

    class_spec = ogm.get_class_spec(
        class_iri=class_iri,
        property_chains=property_chains,
        explore_class_properties=True,
    )
    node2 = ogm.fetch(
        instance_iri=instance_iri,
        class_spec=class_spec,
        property_chains=property_chains,
        materialize=True,
    )
    print("=== Fetched Full Node Triples ===")
    print(format_triples_turtle(node2.to_triples()))
    print("\n=== Fetched Full Node JSON ===")
    print(json.dumps(node2, indent=4, cls=OGMEncoder))
    print("\n=== Fetched Full Node Instance ===")
    print(json.dumps(node2.instance, indent=4, cls=OGMEncoder))

    node3 = ogm.create(
        class_iri=class_iri,
        property_chains=property_chains,
        data=node.data,
        persist=True,
    )

    print(json.dumps(node3.to_triples(), indent=4, cls=OGMEncoder))
    print(json.dumps(node3, indent=4, cls=OGMEncoder))

    pass


if __name__ == "__main__":
    main()
