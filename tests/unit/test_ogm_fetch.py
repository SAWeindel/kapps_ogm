"""
Unit tests for OGM fetch operations.

Tests Phase 1.1: Database Loading & Fetching
- Fetch existing instances from database
- Instance type resolution
- Error handling for missing or multiple types
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from graph_db_interface import IRI
from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.node import Node
from circular_factory_ogm.mapping.class_spec import ClassSpec

from .conftest import (
    TRANSFER_UNIT_IRI,
    INSTANCE_IRI,
    RDF_TYPE,
    PROPERTY_CHAINS,
)


class TestOGMFetch:
    """Test OGM.fetch() method for loading existing instances."""

    def test_fetch_existing_instance(self, ogm_with_mock_db, mock_db):
        """Test fetching an existing instance from the database."""
        # Setup: Mock database returns type information
        mock_db.triples_get.return_value = [(INSTANCE_IRI, RDF_TYPE, TRANSFER_UNIT_IRI)]

        # Mock get_class_spec to avoid complex database queries
        mock_class_spec = Mock(spec=ClassSpec)
        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ):
            # Execute
            node = ogm_with_mock_db.fetch(
                instance_iri=INSTANCE_IRI, property_chains=PROPERTY_CHAINS
            )

        # Assert
        assert isinstance(node, Node)
        assert node.id == INSTANCE_IRI
        assert node.class_spec == mock_class_spec
        assert node.ogm == ogm_with_mock_db

        # Verify database was queried for type
        mock_db.triples_get.assert_called_once_with(
            sub=INSTANCE_IRI, pred=RDF_TYPE, include_implicit=True
        )

    def test_fetch_with_property_chains(self, ogm_with_mock_db, mock_db):
        """Test that fetch passes property_chains to get_class_spec."""
        # Setup
        mock_db.triples_get.return_value = [(INSTANCE_IRI, RDF_TYPE, TRANSFER_UNIT_IRI)]

        mock_class_spec = Mock(spec=ClassSpec)
        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ) as mock_get_spec:
            # Execute
            ogm_with_mock_db.fetch(
                instance_iri=INSTANCE_IRI, property_chains=PROPERTY_CHAINS
            )

            # Assert: get_class_spec was called with property_chains
            mock_get_spec.assert_called_once_with(
                class_iri=TRANSFER_UNIT_IRI, property_chains=PROPERTY_CHAINS
            )

    def test_fetch_without_property_chains(self, ogm_with_mock_db, mock_db):
        """Test fetch with no property_chains specified."""
        # Setup
        mock_db.triples_get.return_value = [(INSTANCE_IRI, RDF_TYPE, TRANSFER_UNIT_IRI)]

        mock_class_spec = Mock(spec=ClassSpec)
        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ) as mock_get_spec:
            # Execute
            ogm_with_mock_db.fetch(instance_iri=INSTANCE_IRI)

            # Assert: get_class_spec was called with None for property_chains
            mock_get_spec.assert_called_once_with(
                class_iri=TRANSFER_UNIT_IRI, property_chains=None
            )


class TestInstanceTypeResolution:
    """Test _resolve_instance_type() method."""

    def test_resolve_single_type(self, ogm_with_mock_db, mock_db):
        """Test resolving instance with single rdf:type."""
        # Setup
        mock_db.triples_get.return_value = [(INSTANCE_IRI, RDF_TYPE, TRANSFER_UNIT_IRI)]

        # Execute
        resolved_type = ogm_with_mock_db._resolve_instance_type(INSTANCE_IRI)

        # Assert
        assert resolved_type == TRANSFER_UNIT_IRI

    def test_resolve_multiple_types_uses_first(self, ogm_with_mock_db, mock_db, caplog):
        """Test that multiple rdf:types logs warning and uses first."""
        # Setup
        type1 = TRANSFER_UNIT_IRI
        type2 = IRI("https://example.org/SomeOtherClass")
        mock_db.triples_get.return_value = [
            (INSTANCE_IRI, RDF_TYPE, type1),
            (INSTANCE_IRI, RDF_TYPE, type2),
        ]

        # Execute
        with caplog.at_level("WARNING"):
            resolved_type = ogm_with_mock_db._resolve_instance_type(INSTANCE_IRI)

        # Assert
        assert resolved_type == type1
        assert "Multiple rdf:types" in caplog.text

    def test_resolve_no_type_raises_error(self, ogm_with_mock_db, mock_db):
        """Test that missing rdf:type raises ValueError."""
        # Setup: No types returned
        mock_db.triples_get.return_value = []

        # Execute & Assert
        with pytest.raises(ValueError, match="No rdf:type found"):
            ogm_with_mock_db._resolve_instance_type(INSTANCE_IRI)

    def test_resolve_queries_with_include_implicit(self, ogm_with_mock_db, mock_db):
        """Test that type resolution includes implicit triples."""
        # Setup
        mock_db.triples_get.return_value = [(INSTANCE_IRI, RDF_TYPE, TRANSFER_UNIT_IRI)]

        # Execute
        ogm_with_mock_db._resolve_instance_type(INSTANCE_IRI)

        # Assert
        mock_db.triples_get.assert_called_once_with(
            sub=INSTANCE_IRI, pred=RDF_TYPE, include_implicit=True
        )
