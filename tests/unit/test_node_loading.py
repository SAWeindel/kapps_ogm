"""
Unit tests for Node lazy loading operations.

Tests Phase 1.2: Node Lazy Loading
- load_data() caching and reload behavior
- materialize() with automatic data loading
- Error handling when OGM is missing
- ValidationError propagation
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pydantic import ValidationError, BaseModel

from graph_db_interface import IRI
from circular_factory_ogm.node import Node
from circular_factory_ogm.mapping.class_spec import ClassSpec

from .conftest import (
    INSTANCE_IRI,
    MOCK_INSTANCE_DATA,
)


class TestNodeLoadData:
    """Test Node.load_data() method."""

    def test_load_data_calls_loader(self, mock_node, ogm_with_mock_db):
        """Test that load_data() calls the OGM's loader."""
        # Setup: Mock loader function
        mock_loader_result = {"test": "data"}
        ogm_with_mock_db.loader = Mock(return_value=mock_loader_result)

        # Execute
        result = mock_node.load_data()

        # Assert
        assert result == mock_loader_result
        assert mock_node.data == mock_loader_result
        ogm_with_mock_db.loader.assert_called_once_with(mock_node)

    def test_load_data_caching(self, mock_node, ogm_with_mock_db):
        """Test that load_data() caches result and doesn't reload."""
        # Setup
        mock_loader_result = {"test": "data"}
        ogm_with_mock_db.loader = Mock(return_value=mock_loader_result)

        # Execute: Load twice
        result1 = mock_node.load_data()
        result2 = mock_node.load_data()

        # Assert: Loader called only once
        assert result1 == result2 == mock_loader_result
        ogm_with_mock_db.loader.assert_called_once()

    def test_load_data_reload_flag(self, mock_node, ogm_with_mock_db):
        """Test that reload=True forces re-loading data."""
        # Setup
        ogm_with_mock_db.loader = Mock(
            side_effect=[{"first": "load"}, {"second": "load"}]
        )

        # Execute: Load, then reload
        result1 = mock_node.load_data()
        result2 = mock_node.load_data(reload=True)

        # Assert: Loader called twice
        assert result1 == {"first": "load"}
        assert result2 == {"second": "load"}
        assert ogm_with_mock_db.loader.call_count == 2

    def test_load_data_without_ogm_raises(self, simple_class_spec):
        """Test that load_data() raises RuntimeError when no OGM attached."""
        # Setup: Node without OGM
        node = Node(
            id=INSTANCE_IRI,
            class_spec=simple_class_spec,
            ogm=None,
        )

        # Execute & Assert
        with pytest.raises(RuntimeError, match="No OGM attached"):
            node.load_data()

    def test_load_data_returns_existing_without_reload(self, mock_node):
        """Test that existing data is returned without calling loader."""
        # Setup: Pre-populate data
        existing_data = {"pre": "existing"}
        mock_node.data = existing_data
        mock_node.ogm.loader = Mock()

        # Execute
        result = mock_node.load_data()

        # Assert: Returns existing, doesn't call loader
        assert result == existing_data
        mock_node.ogm.loader.assert_not_called()


class TestNodeMaterialize:
    """Test Node.materialize() method."""

    def test_materialize_creates_instance(self, mock_node, ogm_with_mock_db):
        """Test that materialize() creates and caches Pydantic instance."""
        # Setup
        mock_node.data = MOCK_INSTANCE_DATA
        mock_instance = Mock(spec=BaseModel)
        ogm_with_mock_db.create_node_instance = Mock(return_value=mock_instance)

        # Execute
        result = mock_node.materialize()

        # Assert
        assert result == mock_instance
        assert mock_node.instance == mock_instance
        ogm_with_mock_db.create_node_instance.assert_called_once_with(mock_node)

    def test_materialize_caching(self, mock_node, ogm_with_mock_db):
        """Test that materialize() caches instance."""
        # Setup
        mock_node.data = MOCK_INSTANCE_DATA
        mock_instance = Mock(spec=BaseModel)
        ogm_with_mock_db.create_node_instance = Mock(return_value=mock_instance)

        # Execute: Materialize twice
        result1 = mock_node.materialize()
        result2 = mock_node.materialize()

        # Assert: create_node_instance called only once
        assert result1 == result2 == mock_instance
        ogm_with_mock_db.create_node_instance.assert_called_once()

    def test_materialize_auto_loads_data(self, mock_node, ogm_with_mock_db):
        """Test that materialize() automatically loads data if not present."""
        # Setup: No data initially
        assert mock_node.data is None
        mock_loader_data = MOCK_INSTANCE_DATA
        mock_instance = Mock(spec=BaseModel)

        ogm_with_mock_db.loader = Mock(return_value=mock_loader_data)
        ogm_with_mock_db.create_node_instance = Mock(return_value=mock_instance)

        # Execute
        result = mock_node.materialize()

        # Assert: Data was loaded
        assert mock_node.data == mock_loader_data
        ogm_with_mock_db.loader.assert_called_once_with(mock_node)
        assert result == mock_instance

    def test_materialize_reload_flag(self, mock_node, ogm_with_mock_db):
        """Test that reload=True reloads data before materialization."""
        # Setup: Pre-existing data
        mock_node.data = {"old": "data"}
        new_data = {"new": "data"}
        mock_instance = Mock(spec=BaseModel)

        ogm_with_mock_db.loader = Mock(return_value=new_data)
        ogm_with_mock_db.create_node_instance = Mock(return_value=mock_instance)

        # Execute
        mock_node.materialize(reload=True)

        # Assert: Data was reloaded
        assert mock_node.data == new_data
        ogm_with_mock_db.loader.assert_called_once()

    def test_materialize_without_ogm_raises(self, simple_class_spec):
        """Test that materialize() raises RuntimeError when no OGM attached."""
        # Setup: Node without OGM
        node = Node(
            id=INSTANCE_IRI,
            class_spec=simple_class_spec,
            ogm=None,
        )

        # Execute & Assert
        with pytest.raises(RuntimeError, match="No OGM attached"):
            node.materialize()

    def test_materialize_returns_cached_instance(self, mock_node):
        """Test that existing instance is returned without recreation."""
        # Setup: Pre-existing instance
        existing_instance = Mock(spec=BaseModel)
        mock_node.instance = existing_instance
        mock_node.ogm.create_node_instance = Mock()

        # Execute
        result = mock_node.materialize()

        # Assert: Returns existing, doesn't create new
        assert result == existing_instance
        mock_node.ogm.create_node_instance.assert_not_called()


class TestNodeRepr:
    """Test Node.__repr__() for different states."""

    def test_repr_with_instance(self, mock_node):
        """Test __repr__ when node has materialized instance."""
        # Setup
        mock_instance = Mock(spec=BaseModel)
        mock_instance.__repr__ = Mock(return_value="<MockInstance>")
        mock_node.instance = mock_instance

        # Execute
        repr_str = repr(mock_node)

        # Assert
        assert "Node<instance" in repr_str
        assert "<MockInstance>" in repr_str

    def test_repr_without_instance(self, mock_node):
        """Test __repr__ when node is not materialized."""
        # Setup: No instance, no data
        assert mock_node.instance is None
        assert mock_node.data is None

        # Execute
        repr_str = repr(mock_node)

        # Assert
        assert "Node<ref" in repr_str
        assert str(INSTANCE_IRI) in repr_str
        assert "data=False" in repr_str
        assert "class_spec=True" in repr_str

    def test_repr_with_data_but_not_materialized(self, mock_node):
        """Test __repr__ when node has data but no instance."""
        # Setup
        mock_node.data = {"some": "data"}

        # Execute
        repr_str = repr(mock_node)

        # Assert
        assert "Node<ref" in repr_str
        assert "data=True" in repr_str
        assert "class_spec=True" in repr_str
