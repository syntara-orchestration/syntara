"""Configuration model for document conversion operations.

This module provides the ConversionConfig class that encapsulates all settings
needed for document conversion operations, sourced from the runtime settings
catalog and centralized configuration system.
"""

from pydantic import BaseModel, Field

from syntara.core.config.base import get_settings
from syntara.settings.cache.settings_cache import get_runtime_settings


class ConversionConfig(BaseModel):
    """Configuration for document conversion operations.

    This class provides a structured interface to document conversion settings
    while maintaining integration with the centralized configuration system.
    All values are sourced from DocumentConversionSettings in core config.
    Output format is always markdown (.md).
    """

    timeout_seconds: int = Field(
        description="Maximum time allowed for document conversion (NFR-001: under 30 seconds)", ge=1, le=300
    )

    overwrite_existing: bool = Field(description="Whether to overwrite existing converted files", default=False)

    temp_dir: str = Field(description="Temporary directory for conversion operations")

    @classmethod
    async def from_settings(cls) -> "ConversionConfig":
        """Create configuration from runtime settings.

        Returns:
            ConversionConfig with live values from the settings cache

        """
        settings = get_settings()
        cache = get_runtime_settings()

        return cls(
            timeout_seconds=await cache.get_int("document_conversion.timeout_seconds"),
            overwrite_existing=await cache.get_bool("document_conversion.overwrite_existing"),
            temp_dir=settings.document_conversion_temp_dir,
        )
