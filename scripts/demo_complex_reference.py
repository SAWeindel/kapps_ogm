import os
import logging
import json

from graph_db_interface import GraphDBCredentials, GraphDB, IRI

from kapps_ogm.node.core import Node
from kapps_ogm.ogm import OGM
from kapps_ogm.utils.json_ogm_encoder import OGMEncoder
from kapps_ogm.utils.pretty_print import format_triples_turtle
from kapps_ogm.utils.class_scope import ClassScope

# We have the triples
#
# cfc:Resource rdf:type owl:Class .
# fc:FlexConveyorModule rdf:type owl:Class ;
#     rdfs:subClassOf cfc:Resource .
# fc:Service rdf:type owl:Class .
# fc:ReserveService rdf:type owl:Class ;
#     rdfs:subClassOf fc:Service .
# fc:hasService rdf:type owl:ObjectProperty ;
#     rdfs:domain cfc:Resource ;
#     rdfs:range fc:Service .
# fc:isServiceOf rdf:type owl:ObjectProperty ;
#     owl:inverseOf fc:hasService ;
#     rdfs:domain fc:Service ;
#     rdfs:range cfc:Resource .
# fc:accessibleAt rdf:type owl:DatatypeProperty ;
#     rdfs:domain fc:Service ;
#     rdfs:range xsd:anyURI .
#
# fci:Module1 rdf:type fc:FlexConveyorModule ;
#     rdf:type owl:NamedIndividual ;
#     fc:hasService fci:ReserveService1 ;
#     fc:hasConnection fci:Connection1 .
# fci:ReserveService1 rdf:type fc:ReserveService ;
#     rdf:type owl:NamedIndividual ;
#     fc:isServiceOf fci:Module1 ;
#     fc:accessibleAt "http://example.org/accessible-at" .
# fci:Module2 rdf:type fc:FlexConveyorModule ;
#     rdf:type owl:NamedIndividual ;
#     fc:hasService fci:ReserveService2 ;
#     fc:hasConnection fci:Connection2 .
# fci:ReserveService2 rdf:type fc:ReserveService ;
#     rdf:type owl:NamedIndividual ;
#     fc:isServiceOf fci:Module2 ;
#     fc:accessibleAt "http://example.org/accessible-at" .
# fci:Connection1 rdf:type fc:Connection ;
#     rdf:type owl:NamedIndividual ;
#     fc:connectsTo fci:Module2 .
# fci:Connection2 rdf:type fc:Connection ;
#     rdf:type owl:NamedIndividual ;
#     fc:connectsTo fci:Module1 .

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

credentials = GraphDBCredentials(
    base_url="https://graphdb.iam-mms.kit.edu/",
    username=os.getenv("GRAPHDB_USERNAME"),
    password=os.getenv("GRAPHDB_PASSWORD"),
    repository="OGM",
)
db = GraphDB(credentials=credentials)
ogm = OGM(db=db)
ogm.logger.setLevel(logging.DEBUG)


def demo_complex_reference():
    """
    This resolves to
        {
            "id": "http://w3id.org/circularfactory/FlexConveyorInstances#ReserveService1",
            "http://w3id.org/circularfactory/FlexConveyor#isServiceOf": [
                {"id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module1"}
            ],
            "http://w3id.org/circularfactory/FlexConveyor#accessibleAt": [
                "http://example.org/accessible-at"
            ]
        }
    which must result in the triple
        fci:ReserveService1 fc:isServiceOf fci:Module1 .
    instead of the literal
        fci:ReserveService1 fc:isServiceOf "{'id': IRI('http://w3id.org/circularfactory/FlexConveyorInstances#Module1')}"^xsd:string .

    """
    print("\n\n\n=== Demo: Complex References ===")
    instance_iri = IRI(
        "http://w3id.org/circularfactory/FlexConveyorInstances#ReserveService1"
    )
    class_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#ReserveService")
    property_chains = [
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
        ],
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#isServiceOf"),
        ],
    ]

    class_scope = ClassScope.from_property_chains(property_chains)
    class_spec = ogm.get_class_spec(
        class_iri=class_iri,
        class_scope=class_scope,
    )
    fetched_node = ogm.fetch(
        instance_iri=instance_iri,
        class_spec=class_spec,
        class_scope=class_scope,
        materialize=True,
    )

    print(json.dumps(fetched_node.instance, indent=4, cls=OGMEncoder))
    print(format_triples_turtle(fetched_node.to_triples()))

    pass


def demo_full_description():
    """
    A nested referenced node should be resolved to triples including both rdf:type triples:
        http://w3id.org/circularfactory/FlexConveyorInstances#Module1
            rdf:type owl:NamedIndividual ;
            rdf:type http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule .
            http://w3id.org/circularfactory/FlexConveyor#hasService http://w3id.org/circularfactory/FlexConveyorInstances#ReserveService1 ;

        http://w3id.org/circularfactory/FlexConveyorInstances#ReserveService1
            rdf:type owl:NamedIndividual .
            rdf:type http://w3id.org/circularfactory/FlexConveyor#hasService ;
            http://w3id.org/circularfactory/FlexConveyor#accessibleAt http://example.org/accessible-at ;
            http://w3id.org/circularfactory/FlexConveyor#isServiceOf http://w3id.org/circularfactory/FlexConveyorInstances#Module1 ;
    This has not been the case previously, omitting them:
        http://w3id.org/circularfactory/FlexConveyorInstances#ReserveService1
            http://w3id.org/circularfactory/FlexConveyor#accessibleAt http://example.org/accessible-at ;
            http://w3id.org/circularfactory/FlexConveyor#isServiceOf http://w3id.org/circularfactory/FlexConveyorInstances#Module1 ;
    """
    print("\n\n\n=== Demo: Full Description ===")
    instance_iri = IRI("http://w3id.org/circularfactory/FlexConveyorInstances#Module1")
    class_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule")
    property_chains = [
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasService"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
        ],
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasService"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#isServiceOf"),
        ],
    ]

    class_scope = ClassScope.from_property_chains(property_chains)
    class_spec = ogm.get_class_spec(
        class_iri=class_iri,
        class_scope=class_scope,
    )
    fetched_node = ogm.fetch(
        instance_iri=instance_iri,
        class_spec=class_spec,
        class_scope=class_scope,
        materialize=True,
    )

    print(json.dumps(fetched_node.instance, indent=4, cls=OGMEncoder))
    print(format_triples_turtle(fetched_node.to_triples()))


def demo_from_data():
    """
    This should resolve the nested reference to Module1 to a Node instance, instead of a dictionary, and serialize it correctly to triples.
    """
    print("\n\n\n=== Demo: From Data ===")
    node_data = {
        "id": "http://w3id.org/circularfactory/FlexConveyorInstances#ReserveService2",
        "http://w3id.org/circularfactory/FlexConveyor#isServiceOf": [
            {"id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module2"}
        ],
        "http://w3id.org/circularfactory/FlexConveyor#accessibleAt": [
            "http://example.org/accessible-at"
        ],
    }
    class_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#ReserveService")
    class_scope = ClassScope.from_property_chains(
        [
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#isServiceOf"),
            ],
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
            ],
        ]
    )

    node = ogm.create(
        class_iri=class_iri,
        data=node_data,
        class_scope=class_scope,
        persist=False,
    )

    print(json.dumps(node.instance, indent=4, cls=OGMEncoder))
    print(format_triples_turtle(node.to_triples()))

    pass


def demo_full_fetch():
    print("\n\n\n=== Demo: Full Fetch ===")
    instance_iri = IRI("http://w3id.org/circularfactory/FlexConveyorInstances#Module1")
    property_chains = [
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasService"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
        ],
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection"),
        ],
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasService"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
        ],
    ]
    class_scope = ClassScope.from_property_chains(property_chains)
    fetched_node = ogm.fetch(
        instance_iri=instance_iri, class_scope=class_scope, materialize=True
    )

    # Print in JSON format (instance model_dump)
    print("\n=== Fetched Node (Lined JSON - Python/Pydantic safe keys) ===")
    print(json.dumps(fetched_node.instance.model_dump(), indent=4))

    # Print in Pretty JSON format (full IRIs)
    print("\n=== Fetched Node (Pretty JSON - Full IRI display) ===")
    print(json.dumps(fetched_node.instance, indent=4, cls=OGMEncoder))

    # Print in JSON-LD format
    print("\n=== Fetched Node as JSON-LD ===")
    print(json.dumps(fetched_node.to_json_ld(), indent=4))

    # Print as triples
    print("\n=== Fetched Node as Triples ===")
    print(format_triples_turtle(fetched_node.to_triples()))


def demo_full_create():
    print("\n\n\n=== Demo: Full Create ===")
    class_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule")
    node_data = {
        "id": "http://w3id.org/circularfactory/FlexConveyorInstances#ModuleN",
        "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_hasConnection": [
            {
                "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_connectsTo": [
                    {
                        "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module2"
                    }
                ],
                "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_hasDirection": [
                    {"id": "http://w3id.org/circularfactory/FlexConveyor#South"}
                ],
            }
        ],
    }

    property_chains = [
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo"),
        ],
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection"),
        ],
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasService"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
        ],
    ]
    class_scope = ClassScope.from_property_chains(property_chains)
    new_node = ogm.create(
        class_iri=class_iri,
        class_scope=class_scope,
        data=node_data,
        persist=False,
    )

    # Print in JSON format (instance model_dump)
    print("\n=== New Node (Lined JSON - Python/Pydantic safe keys) ===")
    print(json.dumps(new_node.instance.model_dump(), indent=4))

    # Print in Pretty JSON format (full IRIs)
    print("\n=== New Node (Pretty JSON - Full IRI display) ===")
    print(json.dumps(new_node.instance, indent=4, cls=OGMEncoder))

    # Print in JSON-LD format
    print("\n=== New Node as JSON-LD ===")
    print(json.dumps(new_node.to_json_ld(), indent=4))

    # Print as triples
    print("\n=== New Node as Triples ===")
    print(format_triples_turtle(new_node.to_triples()))


if __name__ == "__main__":
    demo_complex_reference()
    demo_full_description()
    demo_from_data()
    demo_full_fetch()
    demo_full_create()
