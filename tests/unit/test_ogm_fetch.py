"""
Unit tests for OGM fetch operations.

Tests Phase 1.1: Database Loading & Fetching
- Fetch existing instances from database
- Instance type resolution
- Error handling for missing or multiple types
"""

from unittest.mock import Mock, patch

from circular_factory_ogm.node.core import Node
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
        mock_db.owl_get_classes_of_individual.return_value = [TRANSFER_UNIT_IRI]

        # Mock get_class_spec to avoid complex database queries
        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {}
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
        mock_db.owl_get_classes_of_individual.assert_called_once_with(INSTANCE_IRI)

    def test_fetch_with_property_chains(self, ogm_with_mock_db, mock_db):
        """Test that fetch passes property_chains to get_class_spec."""
        # Setup
        mock_db.owl_get_classes_of_individual.return_value = [TRANSFER_UNIT_IRI]

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {}
        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ) as mock_get_spec:
            # Execute
            ogm_with_mock_db.fetch(
                instance_iri=INSTANCE_IRI, property_chains=PROPERTY_CHAINS
            )

            # Assert: get_class_spec was called with property_chains
            mock_get_spec.assert_called_once_with(
                class_iri=TRANSFER_UNIT_IRI,
                property_chains=PROPERTY_CHAINS,
                explore_class_properties=False,
            )

    def test_fetch_without_property_chains(self, ogm_with_mock_db, mock_db):
        """Test fetch with no property_chains specified."""
        # Setup
        mock_db.owl_get_classes_of_individual.return_value = [TRANSFER_UNIT_IRI]

        mock_class_spec = Mock(spec=ClassSpec)
        mock_class_spec.properties = {}
        with patch.object(
            ogm_with_mock_db, "get_class_spec", return_value=mock_class_spec
        ) as mock_get_spec:
            # Execute
            ogm_with_mock_db.fetch(instance_iri=INSTANCE_IRI)

            # Assert: get_class_spec was called with None for property_chains
            mock_get_spec.assert_called_once_with(
                class_iri=TRANSFER_UNIT_IRI,
                property_chains=None,
                explore_class_properties=False,
            )
