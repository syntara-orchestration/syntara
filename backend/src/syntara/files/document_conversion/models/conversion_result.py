"""Result model for document conversion operations.

This module provides the ConversionResult class that captures all outcomes
and metadata from document conversion operations.
"""

from typing import Any

from pydantic import BaseModel, Field


class ConversionResult(BaseModel):
    """Result of a document conversion operation.

    Captures success/failure status, timing, error details, and metadata
    for comprehensive conversion monitoring and debugging.
    """

    success: bool = Field(description="Whether the conversion completed successfully")

    converted_content: str | None = Field(default=None, description="The converted markdown content (if successful)")

    conversion_time_ms: int = Field(description="Time taken for conversion in milliseconds", ge=0)

    error_message: str | None = Field(default=None, description="Human-readable error message (if conversion failed)")

    error_type: str | None = Field(default=None, description="Categorized error type for programmatic handling")

    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional conversion metadata and metrics")

    @classmethod
    def success_result(
        cls, converted_content: str, conversion_time_ms: int, metadata: dict[str, Any] | None = None
    ) -> "ConversionResult":
        r"""Create successful conversion result.

        Args:
            converted_content: The converted markdown content
            conversion_time_ms: Time taken for conversion
            metadata: Optional additional metadata

        Returns:
            ConversionResult indicating successful conversion

        Example:
            result = ConversionResult.success_result(
                "# Document Title\n\nConverted content...",
                1500,
                {"converter": "MSWordConverter"}
            )
            assert result.success is True
            assert result.converted_content.startswith("# Document")

        """
        return cls(
            success=True,
            converted_content=converted_content,
            conversion_time_ms=conversion_time_ms,
            metadata=metadata or {},
        )

    @classmethod
    def failure_result(
        cls, error_message: str, error_type: str, conversion_time_ms: int, metadata: dict[str, Any] | None = None
    ) -> "ConversionResult":
        """Create failed conversion result.

        Args:
            error_message: Human-readable error description
            error_type: Categorized error type for handling
            conversion_time_ms: Time taken before failure
            metadata: Optional additional metadata

        Returns:
            ConversionResult indicating conversion failure

        Example:
            result = ConversionResult.failure_result(
                "File not found: /missing.pdf",
                "file_not_found",
                500
            )
            assert result.success is False
            assert result.error_type == "file_not_found"

        """
        return cls(
            success=False,
            converted_content=None,
            conversion_time_ms=conversion_time_ms,
            error_message=error_message,
            error_type=error_type,
            metadata=metadata or {},
        )
