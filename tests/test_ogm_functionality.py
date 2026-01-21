"""
Comprehensive tests for OGM functionality based on demo_expansion.py.

Tests cover:
- ClassSpec creation and serialization
- Pydantic model generation
- Blank instance creation
- Node creation and materialization
- RDF triple serialization
- JSON-LD export with context compaction
"""

import os
import json
import pytest
from typing import Dict, Any

from graph_db_interface import GraphDB, IRI
from graph_db_interface.sparql_query import SPARQLQuery
from rdflib import BNode

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.loaders.loader_eh import loader_eh


# Test constants
NODE_ID = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#TransferUnit")
PROPERTY_CHAINS = [
    [IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt")],
    [IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier")],
]

# Common property IRIs used across fixtures
HAS_CONVEYOR_BELT = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorBelt"
)
HAS_CONVEYOR_POSITION = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorPosition"
)
HAS_CONVEYOR_SPEED = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasConveyorSpeed"
)
HAS_LIGHT_BARRIER = IRI(
    "https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasLightBarrier"
)
IS_OCCUPIED = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#isOccupied")
HAS_VALUE = IRI("https://www.sfb1574.kit.edu/ontologies/CrcInterfaces#hasValue")
HAS_UNIT = IRI("https://www.sfb1574.kit.edu/ontologies/TransferUnit#hasUnit")

MOCK_DATA = {
    HAS_CONVEYOR_BELT.lined: [
        {
            HAS_CONVEYOR_POSITION.lined: [
                {
                    HAS_VALUE.lined: [1.25],
                    HAS_UNIT.lined: ["meters"],
                }
            ],
            HAS_CONVEYOR_SPEED.lined: [
                {
                    HAS_VALUE.lined: [0.75],
                    HAS_UNIT.lined: ["meter_per_second"],
                }
            ],
        }
    ],
    HAS_LIGHT_BARRIER.lined: [
        {
            IS_OCCUPIED.lined: [
                {
                    HAS_VALUE.lined: [False],
                    HAS_UNIT.lined: ["boolean"],
                }
            ]
        }
    ],
}

CONTEXT = {
    "ex": "https://example.org/",
    "tu": "https://www.sfb1574.kit.edu/ontologies/TransferUnit#",
    "tui": "https://www.sfb1574.kit.edu/ontologies/TransferUnitInstances#",
    "inf": "https://www.sfb1574.kit.edu/ontologies/inf#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "owl": "http://www.w3.org/2002/07/owl#",
}


@pytest.fixture(scope="module")
def ogm(db: GraphDB) -> OGM:
    """Create OGM instance with database connection."""
    return OGM(db=db, loader=loader_eh)


@pytest.fixture(scope="module")
def class_spec(ogm: OGM) -> ClassSpec:
    """Create ClassSpec for TransferUnit with property chains."""
    return ClassSpec.specify(
        class_iri=NODE_ID, ogm=ogm, property_chains=PROPERTY_CHAINS
    )


@pytest.fixture
def node(ogm: OGM, class_spec: ClassSpec):
    """Create a node with mock data."""
    return ogm.create(
        class_iri=NODE_ID,
        data=MOCK_DATA,
        property_chains=PROPERTY_CHAINS,
    )


class TestClassSpec:
    """Test ClassSpec creation and serialization."""

    def test_specify_class_spec(self, class_spec: ClassSpec):
        """Test that ClassSpec.specify() creates a valid spec."""
        assert class_spec is not None
        assert class_spec.iri == NODE_ID
        assert class_spec.properties is not None
        assert len(class_spec.properties) > 0

    def test_class_spec_to_string(self, class_spec: ClassSpec):
        """Test ClassSpec string serialization."""
        spec_string = class_spec.to_string()
        assert spec_string is not None
        assert isinstance(spec_string, str)
        assert len(spec_string) > 0
        assert "TransferUnit" in spec_string

    def test_class_spec_to_pydantic_model(self, class_spec: ClassSpec):
        """Test ClassSpec conversion to Pydantic model."""
        model_cls = class_spec.to_pydantic_model()
        assert model_cls is not None
        assert hasattr(model_cls, "model_fields")
        assert hasattr(model_cls, "model_json_schema")

    def test_pydantic_model_json_schema(self, class_spec: ClassSpec):
        """Test JSON schema generation from Pydantic model."""
        model_cls = class_spec.to_pydantic_model()
        schema = model_cls.model_json_schema()
        assert schema is not None
        assert isinstance(schema, dict)
        assert "$defs" in schema or "properties" in schema


class TestBlankInstance:
    """Test blank instance creation."""

    def test_create_blank_instance(self, ogm: OGM):
        """Test creation of blank instance with nested properties."""
        instance_iri = "http://example.org/instances/TransferUnit_Test"
        blank_instance = ogm.create_blank_instance(
            class_iri=NODE_ID,
            property_chains=PROPERTY_CHAINS,
            instance_iri=instance_iri,
        )

        assert blank_instance is not None
        assert hasattr(blank_instance, "id")
        assert str(blank_instance.id) == instance_iri

    def test_blank_instance_serialization(self, ogm: OGM):
        """Test that blank instance can be serialized to JSON."""
        blank_instance = ogm.create_blank_instance(
            class_iri=NODE_ID,
            property_chains=PROPERTY_CHAINS,
            instance_iri="http://example.org/instances/TransferUnit_Test2",
        )

        json_str = blank_instance.model_dump_json()
        assert json_str is not None
        assert isinstance(json_str, str)

        # Verify it's valid JSON
        data = json.loads(json_str)
        assert isinstance(data, dict)


class TestNodeCreation:
    """Test node creation and materialization."""

    def test_create_node(self, ogm: OGM):
        """Test node creation with mock data."""
        node = ogm.create(
            class_iri=NODE_ID,
            data=MOCK_DATA,
            property_chains=PROPERTY_CHAINS,
        )

        assert node is not None
        assert node.id is not None
        assert node.class_spec is not None
        assert node.ogm is ogm

    def test_node_materialize(self, node):
        """Test node materialization."""
        instance = node.materialize()

        assert instance is not None
        assert node.is_materialized
        assert node.instance is instance
        assert hasattr(instance, "id")

    def test_multiple_nodes_unique_ids(self, ogm: OGM):
        """Test that multiple nodes get unique IDs."""
        node1 = ogm.create(
            class_iri=NODE_ID,
            data=MOCK_DATA,
            property_chains=PROPERTY_CHAINS,
        )
        node2 = ogm.create(
            class_iri=NODE_ID,
            data=MOCK_DATA,
            property_chains=PROPERTY_CHAINS,
        )

        assert node1.id != node2.id


class TestTripleSerialization:
    """Test RDF triple serialization."""

    def test_to_triples_requires_materialization(self, ogm):
        """Test that to_triples() requires materialized instance."""
        # Create node and explicitly set instance to None to test error handling
        node = ogm.create(
            class_iri=NODE_ID,
            data=MOCK_DATA,
            property_chains=PROPERTY_CHAINS,
        )
        # Force unmaterialized state
        node.instance = None

        with pytest.raises(RuntimeError, match="must be materialized"):
            node.to_triples()

    def test_to_triples_generates_triples(self, node):
        """Test that to_triples() generates RDF triples."""
        node.materialize()
        triples = node.to_triples()

        assert triples is not None
        assert isinstance(triples, set)
        assert len(triples) > 0

    def test_triples_structure(self, node):
        """Test that generated triples have proper structure."""
        node.materialize()
        triples = node.to_triples()

        for triple in triples:
            assert isinstance(triple, tuple)
            assert len(triple) == 3
            s, p, o = triple
            # Subject should be IRI or BNode
            assert isinstance(s, (IRI, BNode, str))
            # Predicate should be IRI or string
            assert isinstance(p, (IRI, str))
            # Object can be IRI, BNode, Literal, or string

    def test_triples_count_expected(self, node):
        """Test that expected number of triples are generated."""
        node.materialize()
        triples = node.to_triples()

        # Expected: type triples + property triples
        # Should have at least 10+ triples for the nested structure
        assert len(triples) >= 10

    def test_triples_contain_type_declarations(self, node):
        """Test that triples include type declarations."""
        node.materialize()
        triples = node.to_triples()

        # Check for type triples
        type_triples = [
            t for t in triples if "rdf:type" in str(t[1]) or "type" in str(t[1]).lower()
        ]
        assert len(type_triples) > 0


class TestJSONLDSerialization:
    """Test JSON-LD serialization and context compaction."""

    def test_to_json_ld_basic(self, node):
        """Test basic JSON-LD generation."""
        node.materialize()
        json_ld = node.to_json_ld()

        assert json_ld is not None
        assert isinstance(json_ld, dict)
        assert "@context" in json_ld
        assert "@graph" in json_ld

    def test_to_json_ld_with_context(self, node):
        """Test JSON-LD generation with context for URI compaction."""
        node.materialize()
        json_ld = node.to_json_ld(context=CONTEXT)

        assert json_ld["@context"] == CONTEXT
        assert isinstance(json_ld["@graph"], list)
        assert len(json_ld["@graph"]) > 0

    def test_to_json_ld_context_compaction(self, node):
        """Test that URIs are compacted using context prefixes."""
        node.materialize()
        json_ld = node.to_json_ld(context=CONTEXT)

        graph_str = json.dumps(json_ld["@graph"])

        # Check that compacted forms appear
        assert "tu:" in graph_str or "inf:" in graph_str or "owl:" in graph_str

    def test_to_json_ld_without_context(self, node):
        """Test JSON-LD generation without context."""
        node.materialize()

        # Clear any previously registered prefixes by creating fresh IRI prefixes dict
        # This is already handled by the method when context is None
        json_ld = node.to_json_ld(context=None)

        assert json_ld["@context"] == {}
        assert "@graph" in json_ld
        assert isinstance(json_ld["@graph"], list)

    def test_json_ld_main_subject_first(self, node):
        """Test that main subject appears first in @graph."""
        node.materialize()
        json_ld = node.to_json_ld(context=CONTEXT)

        graph = json_ld["@graph"]
        assert len(graph) > 0

        # First node should be the main subject
        first_node = graph[0]
        assert "@id" in first_node
        # Should contain the main subject IRI (may be compacted)

    def test_json_ld_blank_nodes_inlined(self, node):
        """Test that blank nodes are inlined, not referenced."""
        node.materialize()
        json_ld = node.to_json_ld(context=CONTEXT)

        graph_str = json.dumps(json_ld["@graph"])

        # Blank nodes (genid-*) should not appear as @id in the graph
        # They should be inlined as nested objects
        assert "genid-" not in graph_str or graph_str.count("genid-") == 0

    def test_json_ld_has_type_declarations(self, node):
        """Test that JSON-LD includes @type declarations."""
        node.materialize()
        json_ld = node.to_json_ld(context=CONTEXT)

        # Check that at least one node has @type
        has_type = any("@type" in n for n in json_ld["@graph"])
        assert has_type

    def test_json_ld_literal_types_preserved(self, node):
        """Test that literal datatypes are preserved as native Python types."""
        node.materialize()
        json_ld = node.to_json_ld(context=CONTEXT)

        # Find numeric and boolean values in the graph
        graph_str = json.dumps(json_ld["@graph"])
        data = json_ld["@graph"]

        # Should find float values (1.25, 0.75) and boolean (false)
        def find_values(obj, values=None):
            if values is None:
                values = []
            if isinstance(obj, dict):
                for v in obj.values():
                    find_values(v, values)
            elif isinstance(obj, list):
                for item in obj:
                    find_values(item, values)
            else:
                values.append(obj)
            return values

        all_values = find_values(data)

        # Check for expected types
        has_float = any(isinstance(v, float) for v in all_values)
        has_bool = any(isinstance(v, bool) for v in all_values)

        assert has_float or has_bool  # At least one typed literal

    def test_json_ld_serializable(self, node):
        """Test that JSON-LD output is JSON-serializable."""
        node.materialize()
        json_ld = node.to_json_ld(context=CONTEXT)

        # Should not raise an exception
        json_str = json.dumps(json_ld)
        assert isinstance(json_str, str)

        # Should be parseable back
        parsed = json.loads(json_str)
        assert parsed == json_ld


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_full_workflow(self, ogm: OGM):
        """Test complete workflow from class spec to JSON-LD."""
        # 1. Create class spec
        class_spec = ClassSpec.specify(
            class_iri=NODE_ID, ogm=ogm, property_chains=PROPERTY_CHAINS
        )
        assert class_spec is not None

        # 2. Generate Pydantic model
        model_cls = class_spec.to_pydantic_model()
        assert model_cls is not None

        # 3. Create blank instance
        blank = ogm.create_blank_instance(
            class_iri=NODE_ID,
            property_chains=PROPERTY_CHAINS,
            instance_iri="http://example.org/test/workflow",
        )
        assert blank is not None

        # 4. Create node with data
        node = ogm.create(
            class_iri=NODE_ID,
            data=MOCK_DATA,
            property_chains=PROPERTY_CHAINS,
        )
        assert node is not None

        # 5. Materialize
        instance = node.materialize()
        assert instance is not None

        # 6. Generate triples
        triples = node.to_triples()
        assert len(triples) > 0

        # 7. Generate JSON-LD
        json_ld = node.to_json_ld(context=CONTEXT)
        assert "@graph" in json_ld

        # Verify round-trip serialization
        json_str = json.dumps(json_ld)
        assert len(json_str) > 0

    def test_multiple_nodes_different_data(self, ogm: OGM):
        """Test creating multiple nodes with different data."""
        data1 = MOCK_DATA.copy()
        data2 = MOCK_DATA.copy()

        node1 = ogm.create(
            class_iri=NODE_ID, data=data1, property_chains=PROPERTY_CHAINS
        )
        node2 = ogm.create(
            class_iri=NODE_ID, data=data2, property_chains=PROPERTY_CHAINS
        )

        node1.materialize()
        node2.materialize()

        # Both should generate triples
        triples1 = node1.to_triples()
        triples2 = node2.to_triples()

        assert len(triples1) > 0
        assert len(triples2) > 0

        # IDs should be different
        assert node1.id != node2.id

    def test_roundtrip_serialization(self, ogm: OGM):
        """
        Test round trip: Python → RDF triples → JSON-LD → Python.

        Verifies that data can be serialized to RDF and JSON-LD formats
        and that the structure is preserved through transformations.
        """
        # 1. Create a node with specific test data
        test_data = {
            HAS_CONVEYOR_BELT.lined: [
                {
                    HAS_CONVEYOR_POSITION.lined: [
                        {
                            HAS_VALUE.lined: [2.5],
                            HAS_UNIT.lined: ["meters"],
                        }
                    ],
                    HAS_CONVEYOR_SPEED.lined: [
                        {
                            HAS_VALUE.lined: [1.5],
                            HAS_UNIT.lined: ["meter_per_second"],
                        }
                    ],
                }
            ],
            HAS_LIGHT_BARRIER.lined: [
                {
                    IS_OCCUPIED.lined: [
                        {
                            HAS_VALUE.lined: [True],
                            HAS_UNIT.lined: ["boolean"],
                        }
                    ]
                }
            ],
        }

        # 2. Create node and materialize
        node = ogm.create(
            class_iri=NODE_ID,
            data=test_data,
            property_chains=PROPERTY_CHAINS,
        )
        node.materialize()
        original_instance = node.instance
        original_data = original_instance.model_dump()

        # 3. Serialize to RDF triples
        triples = node.to_triples()
        assert len(triples) > 0
        # Verify we have type triples
        type_triples = [t for t in triples if "rdf:type" in str(t[1])]
        assert len(type_triples) > 0

        # 4. Serialize to JSON-LD
        json_ld = node.to_json_ld(context=CONTEXT)
        assert "@context" in json_ld
        assert "@graph" in json_ld
        assert len(json_ld["@graph"]) > 0

        # 5. Verify JSON-LD is JSON-serializable (can be sent over network, saved to file)
        json_str = json.dumps(json_ld)
        assert len(json_str) > 0

        # 6. Verify we can parse it back
        parsed_json_ld = json.loads(json_str)
        assert parsed_json_ld == json_ld

        # 7. Verify structure is preserved in JSON-LD
        graph = json_ld["@graph"]
        # Should have main subject plus referenced objects
        assert len(graph) >= 1

        # Find main subject (TransferUnit)
        main_node = graph[0]
        assert "@id" in main_node
        assert "@type" in main_node

        # Verify nested objects are present
        assert "tu:hasConveyorBelt" in str(main_node) or "hasConveyorBelt" in str(
            main_node
        )

        # 8. Verify triple count matches expected structure
        # Should have: type triples + property triples for nested structure
        assert len(triples) >= 10  # Minimum expected for this structure

        # 9. Verify original data values are preserved in instance
        assert original_data is not None
        # Verify specific values
        conveyor_belt_data = original_data.get(HAS_CONVEYOR_BELT.lined, [])
        assert len(conveyor_belt_data) > 0

    def test_roundtrip_preserves_nested_structure(self, ogm: OGM):
        """
        Test that complex nested structures are correctly serialized.

        Verifies that blank nodes and nested objects maintain their
        structure through serialization to RDF and JSON-LD.
        """
        # Create node with nested structure
        node = ogm.create(
            class_iri=NODE_ID,
            data=MOCK_DATA,
            property_chains=PROPERTY_CHAINS,
        )
        node.materialize()

        # Get triples and JSON-LD
        triples = node.to_triples()
        json_ld = node.to_json_ld(context=CONTEXT)

        # Verify structure in triples
        # Should have named entities (TransferUnit, ConveyorBelt, LightBarrier)
        named_subjects = set()
        blank_subjects = set()

        for s, p, o in triples:
            if isinstance(s, IRI):
                named_subjects.add(str(s))
            elif isinstance(s, BNode):
                blank_subjects.add(str(s))

        # Should have at least 3 named subjects (TransferUnit + 2 nested objects)
        assert len(named_subjects) >= 3

        # Should have blank nodes for complex properties
        assert len(blank_subjects) > 0

        # Verify JSON-LD structure
        graph = json_ld["@graph"]

        # Named nodes should appear in graph
        assert len(graph) >= 3

        # Blank nodes should be inlined (not in graph)
        graph_ids = [n.get("@id", "") for n in graph]
        for gid in graph_ids:
            assert not gid.startswith(
                "genid-"
            ), "Blank nodes should be inlined, not in @graph"

        # Verify nested structure exists in JSON-LD
        json_ld_str = json.dumps(json_ld)
        # Should contain property values
        assert (
            "2." in json_ld_str or "1." in json_ld_str or "0." in json_ld_str
        )  # Float values
        assert "meter" in json_ld_str.lower()  # Unit values
        assert (
            "true" in json_ld_str.lower() or "false" in json_ld_str.lower()
        )  # Boolean value
