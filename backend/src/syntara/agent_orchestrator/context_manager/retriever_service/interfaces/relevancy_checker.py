"""Abstract base class for relevancy checking algorithms.

This module defines the RelevancyChecker interface that all relevancy checking
implementations must follow for consistent integration with RetrieverService.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
        RelevancyConfiguration,
    )
    from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
    from syntara.agent_orchestrator.models.llm_credential_config import LLMCredentialConfig

logger = structlog.stdlib.get_logger(__name__)


class RelevancyChecker(ABC):
    """Abstract base class for algorithms that determine document relevance.

    This interface defines the contract that all relevancy checker implementations
    must follow. Concrete implementations use different algorithms like LLM-based
    checking, keyword matching, semantic similarity, etc.

    The checker pattern allows RetrieverService to use different relevancy algorithms
    without knowing their implementation details, and supports fallback strategies.

    Implementation Notes:
        - Receives RelevantDocument with full context (content, metadata, source info)
        - Can leverage file_metadata (size, type, creation date) for enhanced relevancy scoring
        - Returns single relevancy score (0.0 to 1.0) that updates document.relevancy_score
        - Should consider source_type and retrieval_metadata in scoring algorithms
        - Must handle errors gracefully and support fallback mechanisms

    Example Implementation Types:
        - LLMRelevancyChecker: Uses LangChain + OpenRouter for LLM-based checking with metadata context
        - KeywordRelevancyChecker: Keyword-based relevancy with file name and path consideration
        - SemanticRelevancyChecker: Semantic embedding-based checking with metadata weighting
    """

    @abstractmethod
    async def check_relevancy(
        self,
        document: RelevantDocument,
        query: str,
        config: RelevancyConfiguration,
        llm_credential_config: LLMCredentialConfig | None = None,
    ) -> float:
        """Determine the relevancy score of a document for the given query.

        This method analyzes the document content, metadata, and query to compute
        a relevancy score that indicates how well the document matches the query.

        Args:
            document: RelevantDocument containing content and metadata to analyze
            query: User query to match against document
            config: Configuration parameters for this relevancy checking algorithm
            llm_credential_config: Credential config from the agentic node for LLM-based checkers

        Returns:
            Relevancy score between 0.0 and 1.0, where:
            - 0.0 indicates no relevance
            - 1.0 indicates perfect relevance
            - Values in between indicate degrees of relevance

        Raises:
            RelevancyCheckError: If relevancy checking fails due to algorithm issues
            LLMRelevancyError: If LLM-specific checking fails (for LLM implementations)

        Implementation Requirements:
            1. Analyze document.content for relevance to query
            2. Consider document.file_metadata for additional context:
               - filename (may contain relevant keywords)
               - size_bytes (document length consideration)
               - mime_type (document type relevance)
               - status and conversion info
            3. Use document.source_type and retrieval_metadata for enhanced scoring
            4. Apply config parameters to tune algorithm behavior:
               - Use config.similarity_threshold for score adjustments
               - Apply config.ranking_weights for multi-factor scoring
               - Use config.algorithm_parameters for algorithm-specific tuning
               - Consider config.recency_weight for time-based adjustments
            5. Handle errors gracefully:
               - Log errors with context
               - Raise appropriate exceptions for fallback handling
               - Never return scores outside 0.0-1.0 range
            6. Return consistent, comparable scores across different document types

        Example:
            ```python
            async def check_relevancy(
                self,
                document: RelevantDocument,
                query: str,
                config: RelevancyConfiguration
            ) -> float:
                try:
                    # Analyze content relevance using algorithm-specific method
                    content_score = await self._analyze_content(document.content, query)

                    # Consider filename context
                    filename_score = self._analyze_filename(document.file_metadata.filename, query)

                    # Apply configuration weights
                    weights = config.ranking_weights
                    combined_score = (
                        content_score * weights.get("content", 0.8) +
                        filename_score * weights.get("filename", 0.2)
                    )

                    # Apply threshold and normalize
                    final_score = max(0.0, min(1.0, combined_score))

                    logger.debug(
                        "Relevancy check completed",
                        document_filename=document.file_metadata.filename,
                        query=query,
                        score=final_score
                    )

                    return final_score

                except Exception as e:
                    logger.error(
                        "Relevancy check failed",
                        document_filename=document.file_metadata.filename,
                        error=str(e)
                    )
                    raise RelevancyCheckError(f"Failed to check relevancy: {e}")
            ```

        """
