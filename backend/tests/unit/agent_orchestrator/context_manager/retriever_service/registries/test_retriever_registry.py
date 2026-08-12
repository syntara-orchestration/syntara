"""Unit tests for RetrieverRegistry class.

This module tests the functionality of RetrieverRegistry,
ensuring proper registration, retrieval, and error handling for document retrievers.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import RegistryError
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.document_retriever import DocumentRetriever
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.agent_orchestrator.context_manager.retriever_service.registries.retriever_registry import RetrieverRegistry


async def _empty_async_iterator() -> AsyncIterator[RelevantDocument]:
    """Return empty async iterator."""
    _empty: list[RelevantDocument] = []
    for d in _empty:
        yield d


# Mock implementations for testing
class MockDocumentRetriever(DocumentRetriever):
    """Mock DocumentRetriever for testing."""

    def retrieve_documents(self, _invocation_context: dict[str, Any]) -> AsyncIterator[RelevantDocument]:
        """Retrieve mock documents."""
        return _empty_async_iterator()


class TestRetrieverRegistry:
    """Test RetrieverRegistry functionality."""

    def test_create_empty_registry(self) -> None:
        """Test creating an empty RetrieverRegistry."""
        registry = RetrieverRegistry()
        assert registry.list_retrievers() == []

    def test_register_retriever(self) -> None:
        """Test registering a document retriever."""
        registry = RetrieverRegistry()
        registry.register_retriever("mock", MockDocumentRetriever)

        retrievers = registry.list_retrievers()
        assert "mock" in retrievers
        assert len(retrievers) == 1

    def test_get_retriever(self) -> None:
        """Test retrieving a registered retriever."""
        registry = RetrieverRegistry()
        registry.register_retriever("mock", MockDocumentRetriever)

        retriever = registry.get_retriever("mock")
        assert isinstance(retriever, MockDocumentRetriever)

    def test_get_unregistered_retriever_raises_error(self) -> None:
        """Test getting unregistered retriever raises RegistryError."""
        registry = RetrieverRegistry()

        with pytest.raises(RegistryError) as exc_info:
            registry.get_retriever("nonexistent")
        assert "not registered" in str(exc_info.value).lower()
        assert "nonexistent" in str(exc_info.value)

    def test_register_duplicate_retriever_raises_error(self) -> None:
        """Test registering duplicate retriever name raises RegistryError."""
        registry = RetrieverRegistry()
        registry.register_retriever("duplicate", MockDocumentRetriever)

        with pytest.raises(RegistryError) as exc_info:
            registry.register_retriever("duplicate", MockDocumentRetriever)
        assert "already registered" in str(exc_info.value).lower()

    def test_register_multiple_retrievers(self) -> None:
        """Test registering multiple retrievers."""
        registry = RetrieverRegistry()

        class AnotherMockRetriever(DocumentRetriever):
            def retrieve_documents(self, _invocation_context: dict[str, Any]) -> AsyncIterator[RelevantDocument]:
                return _empty_async_iterator()

        registry.register_retriever("mock1", MockDocumentRetriever)
        registry.register_retriever("mock2", AnotherMockRetriever)

        retrievers = registry.list_retrievers()
        assert set(retrievers) == {"mock1", "mock2"}

        # Both should be retrievable
        retriever1 = registry.get_retriever("mock1")
        retriever2 = registry.get_retriever("mock2")
        assert isinstance(retriever1, MockDocumentRetriever)
        assert isinstance(retriever2, AnotherMockRetriever)

    def test_get_all_retrievers(self) -> None:
        """Test getting all registered retrievers."""
        registry = RetrieverRegistry()
        registry.register_retriever("mock", MockDocumentRetriever)

        all_retrievers = registry.get_all_retrievers()
        assert len(all_retrievers) == 1
        assert "mock" in all_retrievers
        assert isinstance(all_retrievers["mock"], MockDocumentRetriever)
