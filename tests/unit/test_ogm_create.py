"""
Unit tests for OGM create operations and ID injection.

Tests Phase 1.3: Node ID Injection
- Auto-generation of nested object IDs
- Preservation of existing IDs
- Duplicate IRI detection
- Pydantic validation during creation
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pydantic import ValidationError, BaseModel, Field
from typing import Optional, List

from graph_db_interface import IRI
from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.node import Node
from circular_factory_ogm.mapping.class_spec import ClassSpec
from circular_factory_ogm.mapping.property_spec import PropertySpec

from .conftest import (
    TRANSFER_UNIT_IRI,
    INSTANCE_IRI,
)


class TestOGMCreate:
    """Test OGM.create() method."""

    def test_create_with_explicit_iri(self, ogm_with_mock_db, mock_db):
        """Test creating node with explicitly provided IRI."""
        # Setup
        mock_db.iri_exists.return_value = False
        data = {"name": "Test Unit"}

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {}

        # Mock Pydantic model
        mock_model_cls = Mock()
        mock_instance = Mock(spec=BaseModel)
        mock_model_cls.return_value = mock_instance
        mock_class_spec.to_pydantic_model.return_value = mock_model_cls

        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ):
            # Execute
            node = ogm_with_mock_db.create(
                class_iri=TRANSFER_UNIT_IRI, data=data, instance_iri=INSTANCE_IRI
            )

        # Assert
        assert isinstance(node, Node)
        assert node.id == INSTANCE_IRI
        assert node.instance == mock_instance
        mock_db.iri_exists.assert_called_once_with(INSTANCE_IRI)

    def test_create_with_id_in_data(self, ogm_with_mock_db, mock_db):
        """Test creating node with ID provided in data dict."""
        # Setup
        mock_db.iri_exists.return_value = False
        provided_iri = IRI("https://example.org/my_instance")
        data = {"id": str(provided_iri), "name": "Test"}

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {}
        mock_model_cls = Mock()
        mock_instance = Mock(spec=BaseModel)
        mock_model_cls.return_value = mock_instance
        mock_class_spec.to_pydantic_model.return_value = mock_model_cls

        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ):
            # Execute
            node = ogm_with_mock_db.create(class_iri=TRANSFER_UNIT_IRI, data=data)

        # Assert
        assert node.id == provided_iri

    def test_create_auto_generates_id(self, ogm_with_mock_db, mock_db):
        """Test that create auto-generates ID when none provided."""
        # Setup
        mock_db.iri_exists.return_value = False
        data = {"name": "Test"}
        generated_iri = IRI("https://example.org/generated_123")

        ogm_with_mock_db.node_naming_schema = Mock(return_value=generated_iri)

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {}
        mock_model_cls = Mock()
        mock_instance = Mock(spec=BaseModel)
        mock_model_cls.return_value = mock_instance
        mock_class_spec.to_pydantic_model.return_value = mock_model_cls

        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ):
            # Execute
            node = ogm_with_mock_db.create(class_iri=TRANSFER_UNIT_IRI, data=data)

        # Assert
        assert node.id == generated_iri
        ogm_with_mock_db.node_naming_schema.assert_called_once_with(TRANSFER_UNIT_IRI)

    def test_create_with_duplicate_iri_raises(self, ogm_with_mock_db, mock_db):
        """Test that creating with existing IRI raises ValueError."""
        # Setup: IRI already exists
        mock_db.iri_exists.return_value = True
        data = {"name": "Test"}

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {}
        mock_class_spec.to_pydantic_model.return_value = Mock()

        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ):
            # Execute & Assert
            with pytest.raises(ValueError, match="already exists"):
                ogm_with_mock_db.create(
                    class_iri=TRANSFER_UNIT_IRI, data=data, instance_iri=INSTANCE_IRI
                )

    def test_create_validates_with_pydantic(self, ogm_with_mock_db, mock_db):
        """Test that create validates data with Pydantic model."""
        # Setup: Invalid data that will fail Pydantic validation
        mock_db.iri_exists.return_value = False
        data = {"invalid_field": "bad_value"}

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {}

        # Mock Pydantic model that raises ValidationError
        mock_model_cls = Mock(
            side_effect=ValidationError.from_exception_data(
                "Test",
                [
                    {
                        "type": "missing",
                        "loc": ("required_field",),
                        "msg": "Field required",
                        "input": data,
                    }
                ],
            )
        )
        mock_class_spec.to_pydantic_model.return_value = mock_model_cls

        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ):
            # Execute & Assert
            with pytest.raises(ValueError, match="validation failed"):
                ogm_with_mock_db.create(
                    class_iri=TRANSFER_UNIT_IRI, data=data, instance_iri=INSTANCE_IRI
                )


class TestIDInjection:
    """Test _inject_missing_ids() method."""

    def test_inject_ids_for_nested_objects(self, ogm_with_mock_db):
        """Test that missing IDs are injected into nested objects."""
        # Setup: Mock class spec with nested object property
        nested_iri = IRI("https://example.org/NestedClass")
        prop_iri = IRI("https://example.org/hasNested")

        # Create nested class spec
        nested_class_spec = Mock(spec=ClassSpec)
        nested_class_spec.iri = nested_iri
        nested_class_spec.properties = {}

        nested_prop_spec = Mock(spec=PropertySpec)
        nested_prop_spec.nested = nested_class_spec
        nested_prop_spec.is_object_property = Mock(return_value=True)

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {prop_iri: nested_prop_spec}

        # Data with nested object missing ID
        data = {prop_iri.lined: [{"value": 42}]}  # No 'id' field

        # Mock naming schema to generate ID
        generated_id = IRI("https://example.org/nested_generated_123")
        ogm_with_mock_db.node_naming_schema = Mock(return_value=generated_id)

        # Execute
        ogm_with_mock_db._inject_missing_ids(data, mock_class_spec)

        # Assert: ID was injected
        assert "id" in data[prop_iri.lined][0]
        assert data[prop_iri.lined][0]["id"] == generated_id

    def test_inject_ids_preserves_existing(self, ogm_with_mock_db):
        """Test that existing IDs are not overwritten."""
        # Setup
        nested_iri = IRI("https://example.org/NestedClass")
        prop_iri = IRI("https://example.org/hasNested")

        # Create nested class spec
        nested_class_spec = Mock(spec=ClassSpec)
        nested_class_spec.iri = nested_iri
        nested_class_spec.properties = {}

        nested_prop_spec = Mock(spec=PropertySpec)
        nested_prop_spec.nested = nested_class_spec
        nested_prop_spec.is_object_property = Mock(return_value=True)

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {prop_iri: nested_prop_spec}

        # Data with nested object that HAS an ID
        existing_id = IRI("https://example.org/existing_id")
        data = {prop_iri.lined: [{"id": existing_id, "value": 42}]}

        ogm_with_mock_db.node_naming_schema = Mock()

        # Execute
        ogm_with_mock_db._inject_missing_ids(data, mock_class_spec)

        # Assert: ID was NOT changed
        assert data[prop_iri.lined][0]["id"] == existing_id
        ogm_with_mock_db.node_naming_schema.assert_not_called()

    def test_inject_ids_handles_none_values(self, ogm_with_mock_db):
        """Test that None values are handled gracefully."""
        # Setup
        prop_iri = IRI("https://example.org/hasNested")

        nested_prop_spec = Mock(spec=PropertySpec)
        nested_prop_spec.nested = None
        nested_prop_spec.is_object_property = Mock(return_value=True)

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {prop_iri: nested_prop_spec}

        # Data with None value
        data = {prop_iri.lined: None}

        # Execute - should not raise
        ogm_with_mock_db._inject_missing_ids(data, mock_class_spec)

        # Assert: Data unchanged
        assert data[prop_iri.lined] is None

    def test_inject_ids_skips_missing_fields(self, ogm_with_mock_db):
        """Test that properties not in data are skipped."""
        # Setup
        prop_iri = IRI("https://example.org/hasNested")

        nested_prop_spec = Mock(spec=PropertySpec)
        nested_prop_spec.nested = None
        nested_prop_spec.is_object_property = Mock(return_value=True)

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {prop_iri: nested_prop_spec}

        # Data without the property
        data = {"other_field": "value"}

        # Execute - should not raise
        ogm_with_mock_db._inject_missing_ids(data, mock_class_spec)

        # Assert: Data unchanged
        assert "other_field" in data
        assert prop_iri.lined not in data

    def test_inject_ids_handles_list_of_objects(self, ogm_with_mock_db):
        """Test that IDs are injected for multiple nested objects in a list."""
        # Setup
        nested_iri = IRI("https://example.org/NestedClass")
        prop_iri = IRI("https://example.org/hasNested")

        # Create nested class spec
        nested_class_spec = Mock(spec=ClassSpec)
        nested_class_spec.iri = nested_iri
        nested_class_spec.properties = {}

        nested_prop_spec = Mock(spec=PropertySpec)
        nested_prop_spec.nested = nested_class_spec
        nested_prop_spec.is_object_property = Mock(return_value=True)

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {prop_iri: nested_prop_spec}

        # Data with multiple nested objects
        data = {prop_iri.lined: [{"value": 1}, {"value": 2}, {"value": 3}]}

        # Mock naming schema to generate unique IDs
        ogm_with_mock_db.node_naming_schema = Mock(
            side_effect=[
                IRI("https://example.org/nested_1"),
                IRI("https://example.org/nested_2"),
                IRI("https://example.org/nested_3"),
            ]
        )

        # Execute
        ogm_with_mock_db._inject_missing_ids(data, mock_class_spec)

        # Assert: All objects got IDs
        assert all("id" in obj for obj in data[prop_iri.lined])
        assert ogm_with_mock_db.node_naming_schema.call_count == 3
