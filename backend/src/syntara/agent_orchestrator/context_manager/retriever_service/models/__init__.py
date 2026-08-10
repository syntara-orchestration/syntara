"""Data models for RetrieverService framework."""

from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument

__all__ = [
    # Models
    "RelevancyConfiguration",
    "RelevantDocument",
]
