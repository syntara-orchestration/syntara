"""Abstract base class for document retrieval from storage backends.

This module defines the DocumentRetriever interface that all document retrieval
implementations must follow for consistent integration with RetrieverService.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import structlog

from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument

logger = structlog.stdlib.get_logger(__name__)


class DocumentRetriever(ABC):
    """Abstract base class for retrieving documents from different storage backends.

    This interface defines the contract that all document retriever implementations
    must follow. Concrete implementations handle specific storage backends like
    uploaded files, databases, cloud storage, etc.

    The retriever pattern allows RetrieverService to work with multiple storage
    backends without knowing their implementation details.

    Implementation Notes:
        - Returns RelevantDocument objects with content, metadata, and source type
        - Initial relevancy_score should be set to 1.0 (neutral score before relevancy checking)
        - Must populate file_metadata, source_type, and retrieval_metadata fields
        - Should handle errors gracefully and log appropriate messages

    Example Implementation Types:
        - UploadedFileRetriever: Retrieves from uploaded files via FileManager
        - DatabaseRetriever: Retrieves from database storage
        - CloudStorageRetriever: Retrieves from cloud storage
    """

    @abstractmethod
    def retrieve_documents(self, invocation_context: dict[str, Any]) -> AsyncIterator[RelevantDocument]:
        """Retrieve documents from storage backend for the given invocation context.

        This method accesses the storage backend and returns documents as RelevantDocument
        objects with proper metadata and initial relevancy scores.

        Args:
            invocation_context: Context data from the invocation, containing file metadata
                              and other relevant information for document retrieval

        Returns:
            AsyncIterator that yields RelevantDocument objects retrieved from this storage backend.
            Yields nothing if no documents are found or accessible.

        Raises:
            DocumentRetrievalError: If retrieval fails due to storage backend issues

        Implementation Requirements:
            1. Parse invocation_context to extract relevant data (e.g., file_metadata)
            2. Access storage backend to retrieve document content
            3. Create RelevantDocument objects with:
               - content: Full document text
               - relevancy_score: 1.0 (neutral, before relevancy checking)
               - file_metadata: Reference to original file metadata
               - source_type: Identifier for this storage backend
               - retrieval_metadata: Additional retrieval context
            4. Handle errors gracefully (log and return empty list or raise appropriate exception)
            5. Return documents in consistent format regardless of storage backend

        Example:
            ```python
            async def retrieve_documents(
                self, invocation_context: dict[str, Any]
            ) -> AsyncIterator[RelevantDocument]:
                file_metadata_list = invocation_context.get("file_metadata", [])

                for file_metadata_dict in file_metadata_list:
                    file_metadata = FileMetadata(**file_metadata_dict)

                    # Retrieve document content using storage backend
                    content = await self._load_document_content(file_metadata)

                    # Create RelevantDocument with proper metadata
                    document = RelevantDocument(
                        content=content,
                        relevancy_score=1.0,  # Neutral score
                        file_metadata=file_metadata,
                        source_type="uploaded_file",
                        retrieval_metadata={
                            "retrieved_at": datetime.utcnow().isoformat(),
                            "backend_version": "1.0"
                        }
                    )
                    yield document
            ```

        """
