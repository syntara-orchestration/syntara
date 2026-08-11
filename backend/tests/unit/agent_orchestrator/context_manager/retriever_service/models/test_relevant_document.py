"""Unit tests for RelevantDocument model.

This module tests the validation behavior and functionality of the RelevantDocument
model, ensuring proper data validation and error handling.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.files.models import FileMetadata


class TestRelevantDocumentValidation:
    """Test validation rules for RelevantDocument model."""

    def test_relevancy_score_range_validation(self) -> None:
        """Test relevancy_score must be between 0.0 and 1.0."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="test.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/test.txt",
            status="converted",
        )

        # Test score too low
        with pytest.raises(ValidationError) as exc_info:
            RelevantDocument(
                content="Test content",
                relevancy_score=-0.1,  # Invalid: below 0.0
                file_metadata=file_metadata,
                source_type="uploaded_file",
                retrieval_metadata={},
            )
        assert "relevancy_score" in str(exc_info.value)

        # Test score too high
        with pytest.raises(ValidationError) as exc_info:
            RelevantDocument(
                content="Test content",
                relevancy_score=1.5,  # Invalid: above 1.0
                file_metadata=file_metadata,
                source_type="uploaded_file",
                retrieval_metadata={},
            )
        assert "relevancy_score" in str(exc_info.value)

        # Test valid boundary values
        doc_zero = RelevantDocument(
            content="Test content",
            relevancy_score=0.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )
        assert doc_zero.relevancy_score == pytest.approx(0.0)

        doc_one = RelevantDocument(
            content="Test content",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )
        assert doc_one.relevancy_score == pytest.approx(1.0)
