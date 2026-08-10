"""Registry for managing document retriever implementations.

This module provides the RetrieverRegistry class for registering and managing
different DocumentRetriever implementations in a pluggable architecture.
"""

import functools

import structlog

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import RegistryError
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.document_retriever import DocumentRetriever
from syntara.agent_orchestrator.context_manager.retriever_service.retrievers.uploaded_file_retriever import (
    UploadedFileRetriever,
)

logger = structlog.stdlib.get_logger(__name__)


class RetrieverRegistry:
    """Registry for managing document retriever implementations.

    This class implements the Registry pattern to allow dynamic registration
    and retrieval of DocumentRetriever implementations. This enables the
    RetrieverService to work with multiple storage backends without knowing
    their specific implementations.

    The registry supports:
    - Registration of new retriever types
    - Type-safe retriever instantiation
    - Enumeration of available retrievers
    - Error handling for invalid operations

    Example Usage:
        ```python
        registry = RetrieverRegistry()

        # Register retrievers
        registry.register_retriever("uploaded_file", UploadedFileRetriever)
        registry.register_retriever("database", DatabaseRetriever)

        # Get specific retriever
        retriever = registry.get_retriever("uploaded_file")

        # Get all retrievers for batch operations
        all_retrievers = registry.get_all_retrievers()
        ```
    """

    def __init__(self) -> None:
        """Initialize retriever registry with default implementations."""
        self._retrievers: dict[str, type[DocumentRetriever]] = {}

    def register_retriever(self, name: str, retriever_class: type[DocumentRetriever]) -> None:
        """Register a document retriever implementation.

        Args:
            name: Unique identifier for this retriever type
            retriever_class: DocumentRetriever subclass to register

        Raises:
            RegistryError: If retriever name is already registered
            TypeError: If retriever_class is not a DocumentRetriever subclass

        """
        if not name or not name.strip():
            error_msg = "Retriever name cannot be empty"
            raise RegistryError(error_msg)

        if name in self._retrievers:
            error_msg = f"Retriever '{name}' is already registered"
            raise RegistryError(error_msg)

        self._retrievers[name] = retriever_class
        logger.info("Registered retriever", retriever_name=name, retriever_class=retriever_class.__name__)

    def get_retriever(self, name: str) -> DocumentRetriever:
        """Get a retriever instance by name.

        Args:
            name: Name of the registered retriever

        Returns:
            New instance of the requested retriever

        Raises:
            RegistryError: If retriever name is not registered

        """
        if name not in self._retrievers:
            error_msg = f"Retriever '{name}' is not registered. Available: {list(self._retrievers.keys())}"
            raise RegistryError(error_msg)

        retriever_class = self._retrievers[name]
        retriever_instance = retriever_class()

        logger.debug("Created retriever instance", retriever_name=name)
        return retriever_instance

    def get_all_retrievers(self) -> dict[str, DocumentRetriever]:
        """Get instances of all registered retrievers.

        Returns:
            Dictionary mapping retriever names to their instances

        """
        all_retrievers = {}
        for name, retriever_class in self._retrievers.items():
            all_retrievers[name] = retriever_class()

        logger.debug("Created instances for retrievers", retriever_count=len(all_retrievers))
        return all_retrievers

    def list_retrievers(self) -> list[str]:
        """List names of all registered retrievers.

        Returns:
            List of registered retriever names

        """
        return list(self._retrievers.keys())


# ===================================================
# Generator for dependency injection
# ---------------------------------------------------
def _setup_default_registry() -> "RetrieverRegistry":
    """Set up default retriever registry with uploaded file retriever."""
    # Register default retrievers
    registry: RetrieverRegistry = RetrieverRegistry()
    registry.register_retriever("uploaded_file", UploadedFileRetriever)

    logger.info(
        "Initialized RetrieverRegistry with default retrievers", retriever_count=len(registry.list_retrievers())
    )

    return registry


@functools.lru_cache(maxsize=1)
def get_retriever_registry() -> RetrieverRegistry:
    """Get retriever registry for dependency injection.

    Returns:
        RetrieverRegistry for dependency injection

    Example:
        from syntara.agent_orchestrator.context_manager.retriever_service.registries.retriever_registry import (
            get_retriever_registry,
        )

        registry = get_retriever_registry()
        retriever = registry.get_retriever("uploaded_file")
        documents = await retriever.retrieve_documents(context)

    """
    return _setup_default_registry()


# ===================================================
