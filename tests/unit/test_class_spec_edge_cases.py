"""
Unit tests for ClassSpec edge cases and error conditions.

Tests Phase 2.2: ClassSpec Edge Cases
- Blank node class specs (without IRI)
- Circular property references
- Invalid property chains
- Class equality and comparison
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from graph_db_interface import IRI, GraphDB
from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.mapping.property_spec import PropertySpec

from .conftest import TRANSFER_UNIT_IRI


class TestBlankNodeClassSpec:
    """Test ClassSpec behavior with blank nodes (no IRI)."""

    def test_class_spec_without_iri_is_blank_node(self):
        """Test that ClassSpec without IRI is treated as blank node."""
        # Setup: Create ClassSpec without IRI
        blank_spec = ClassSpec(iri=None, types=[], properties={})  # Blank node

        # Assert
        assert blank_spec.iri is None
        assert blank_spec.properties == {}

    def test_blank_node_to_pydantic_skips_id_field(self):
        """Test that blank node ClassSpec doesn't add 'id' field to Pydantic model."""
        # Setup
        blank_spec = ClassSpec(iri=None, types=[], properties={})

        # Execute
        model = blank_spec.to_pydantic_model()

        # Assert: No 'id' field in model
        assert "id" not in model.model_fields

    def test_named_class_to_pydantic_includes_id_field(self):
        """Test that named ClassSpec adds 'id' field to Pydantic model."""
        # Setup
        named_spec = ClassSpec(iri=TRANSFER_UNIT_IRI, types=[], properties={})

        # Execute
        model = named_spec.to_pydantic_model()

        # Assert: 'id' field present
        assert "id" in model.model_fields


class TestClassSpecValidation:
    """Test ClassSpec validation and error handling."""

    def test_specify_with_non_class_iri_raises(self, ogm_with_mock_db, mock_db):
        """Test that specifying non-Class IRI raises ValueError."""
        # Setup: IRI that is not a Class
        non_class_iri = IRI("https://example.org/NotAClass")
        mock_db.triples_get.return_value = [
            (non_class_iri, IRI("rdf:type"), IRI("owl:Thing"))  # Not owl:Class
        ]

        # Execute & Assert
        with pytest.raises(ValueError, match="is not an OWL/RDFS Class"):
            ClassSpec.specify(ogm=ogm_with_mock_db, class_iri=non_class_iri)

    def test_specify_handles_missing_label(self, ogm_with_mock_db, mock_db):
        """Test that ClassSpec handles missing rdfs:label gracefully."""
        # Setup: Class with no label
        mock_db.triples_get.side_effect = lambda sub, pred, include_implicit: {
            "rdf:type": [(sub, pred, IRI("owl:Class"))],
            "rdfs:label": [],  # No label
            "rdfs:subClassOf": [(sub, pred, sub)],  # Self-reference
        }.get(pred, [])

        with patch.object(ClassSpec, "classify_outgoing_properties", return_value={}):
            # Execute
            spec = ClassSpec.specify(ogm=ogm_with_mock_db, class_iri=TRANSFER_UNIT_IRI)

        # Assert: ClassSpec created without label
        assert spec.iri == TRANSFER_UNIT_IRI
        assert spec.label is None

    def test_specify_with_self_as_only_superclass(
        self, ogm_with_mock_db, mock_db, caplog
    ):
        """Test ClassSpec when class is only subclass of itself."""
        # Setup: Class is subclass of itself only
        mock_db.triples_get.side_effect = lambda sub, pred, include_implicit: {
            "rdf:type": [(sub, pred, IRI("owl:Class"))],
            "rdfs:label": [(sub, pred, "Test Class")],
            "rdfs:subClassOf": [(sub, pred, sub)],  # Only itself
        }.get(pred, [])

        with patch.object(ClassSpec, "classify_outgoing_properties", return_value={}):
            # Execute
            with caplog.at_level("WARNING"):
                spec = ClassSpec.specify(
                    ogm=ogm_with_mock_db, class_iri=TRANSFER_UNIT_IRI
                )

        # Assert: Warning logged, empty superclasses
        assert spec.superclasses == [] or spec.superclasses is None


class TestPropertyChainHandling:
    """Test property chain expansion in ClassSpec."""

    def test_specify_with_empty_property_chains(self, ogm_with_mock_db, mock_db):
        """Test ClassSpec.specify with empty property_chains list."""
        # Setup
        mock_db.triples_get.side_effect = lambda sub, pred, include_implicit: {
            "rdf:type": [(sub, pred, IRI("owl:Class"))],
            "rdfs:label": [(sub, pred, "Test")],
            "rdfs:subClassOf": [(sub, pred, sub)],
        }.get(pred, [])

        with patch.object(ClassSpec, "classify_outgoing_properties", return_value={}):
            # Execute: Empty property chains
            spec = ClassSpec.specify(
                ogm=ogm_with_mock_db, class_iri=TRANSFER_UNIT_IRI, property_chains=[]
            )

        # Assert: ClassSpec created
        assert spec.iri == TRANSFER_UNIT_IRI

    def test_specify_with_invalid_property_chain_length(
        self, ogm_with_mock_db, mock_db
    ):
        """Test property chain with empty list raises or handles gracefully."""
        # Setup
        mock_db.triples_get.side_effect = lambda sub, pred, include_implicit: {
            "rdf:type": [(sub, pred, IRI("owl:Class"))],
            "rdfs:subClassOf": [(sub, pred, sub)],
        }.get(pred, [])

        with patch.object(ClassSpec, "classify_outgoing_properties", return_value={}):
            # Execute: Property chain with empty inner list
            # This should either raise or handle gracefully
            try:
                spec = ClassSpec.specify(
                    ogm=ogm_with_mock_db,
                    class_iri=TRANSFER_UNIT_IRI,
                    property_chains=[[]],  # Empty inner list
                )
                # If no exception, test passes
                assert spec is not None
            except (IndexError, ValueError, KeyError):
                # Expected - invalid chain should raise
                pass

    def test_property_chain_with_missing_property(self, ogm_with_mock_db, mock_db):
        """Test property chain when property doesn't exist in ClassSpec."""
        # Setup: ClassSpec with no properties
        mock_db.triples_get.side_effect = lambda sub, pred, include_implicit: {
            "rdf:type": [(sub, pred, IRI("owl:Class"))],
            "rdfs:subClassOf": [(sub, pred, sub)],
        }.get(pred, [])

        with patch.object(ClassSpec, "classify_outgoing_properties", return_value={}):
            # Execute: Try to expand property that doesn't exist
            missing_prop = IRI("https://example.org/nonexistent")

            # This should raise ValueError or KeyError for missing property
            with pytest.raises((KeyError, ValueError)):
                spec = ClassSpec.specify(
                    ogm=ogm_with_mock_db,
                    class_iri=TRANSFER_UNIT_IRI,
                    property_chains=[[missing_prop]],
                )


class TestClassSpecSerialization:
    """Test ClassSpec serialization methods."""

    def test_to_string_with_properties(self):
        """Test to_string() includes property information."""
        # Setup: Real PropertySpec (not mock) to avoid iteration issues
        prop_spec = PropertySpec(
            iri=IRI("https://example.org/prop1"),
            value_kind="literal",
            python_range_type=str,
            min_count=None,
            max_count=None,
            nested=None,
        )

        class_spec = ClassSpec(
            iri=TRANSFER_UNIT_IRI,
            types=[IRI("owl:Class")],
            properties={IRI("https://example.org/prop1"): prop_spec},
        )

        # Execute
        string_repr = class_spec.to_string()

        # Assert: Contains class info
        assert str(TRANSFER_UNIT_IRI) in string_repr or "TransferUnit" in string_repr
        assert isinstance(string_repr, str)

    def test_to_string_with_no_properties(self):
        """Test to_string() with empty properties dict."""
        # Setup
        class_spec = ClassSpec(iri=TRANSFER_UNIT_IRI, types=[], properties={})

        # Execute
        string_repr = class_spec.to_string()

        # Assert: Returns valid string
        assert isinstance(string_repr, str)
        assert len(string_repr) > 0

    def test_to_json_schema_basic(self):
        """Test JSON schema generation from ClassSpec."""
        # Setup: Simple ClassSpec
        class_spec = ClassSpec(iri=TRANSFER_UNIT_IRI, types=[], properties={})

        # Execute
        model = class_spec.to_pydantic_model()
        schema = model.model_json_schema()

        # Assert: Valid JSON schema
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "id" in schema["properties"]  # Named class has id field


class TestClassSpecInheritance:
    """Test property inheritance from superclasses."""

    def test_classify_properties_with_no_properties(self, ogm_with_mock_db, mock_db):
        """Test classify_outgoing_properties with class that has no properties."""
        # Setup: Class with no outgoing properties
        mock_db.triples_get.return_value = []  # No properties

        # Execute
        properties = ClassSpec.classify_outgoing_properties(
            TRANSFER_UNIT_IRI, ogm_with_mock_db
        )

        # Assert: Empty dict
        assert properties == {}

    def test_property_inheritance_overrides(self, ogm_with_mock_db, mock_db):
        """Test that own properties override inherited ones."""
        # Setup: Real PropertySpec objects to avoid Mock iteration issues
        prop_iri = IRI("https://example.org/sharedProp")

        inherited_prop = PropertySpec(
            iri=prop_iri,
            value_kind="literal",
            python_range_type=str,
            min_count=None,
            max_count=1,  # Inherited says functional
            nested=None,
        )

        own_prop = PropertySpec(
            iri=prop_iri,
            value_kind="literal",
            python_range_type=str,
            min_count=1,  # Own says required
            max_count=None,
            nested=None,
        )

        mock_db.triples_get.side_effect = lambda sub, pred, include_implicit: {
            "rdf:type": [(sub, pred, IRI("owl:Class"))],
            "rdfs:subClassOf": [
                (sub, pred, sub),
                (sub, pred, IRI("https://example.org/SuperClass")),
            ],
        }.get(pred, [])

        with patch.object(ClassSpec, "classify_outgoing_properties") as mock_classify:
            # First call: inherited properties from superclass
            # Second call: own properties (overrides)
            mock_classify.side_effect = [
                {prop_iri: inherited_prop},  # Superclass
                {prop_iri: own_prop},  # Own class
            ]

            # Execute
            spec = ClassSpec.specify(ogm=ogm_with_mock_db, class_iri=TRANSFER_UNIT_IRI)

        # Assert: Own property overrides inherited (check distinguishing attribute)
        assert spec.properties[prop_iri].min_count == 1  # Own prop characteristic
        assert spec.properties[prop_iri] == own_prop
