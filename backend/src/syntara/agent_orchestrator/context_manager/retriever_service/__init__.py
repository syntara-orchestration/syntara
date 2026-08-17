"""RetrieverService framework initialization and service registration.

This module provides service registration and dependency injection setup
for the RetrieverService framework components.
"""

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import (
    RegistryError,
    RetrieverServiceError,
)

__all__ = [
    # Exceptions
    "RegistryError",
    "RetrieverServiceError",
]
