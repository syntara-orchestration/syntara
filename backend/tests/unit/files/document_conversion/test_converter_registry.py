"""Test for ConverterRegistry functionality."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from syntara.files.document_conversion.registry.converter_registry import (
    ConverterRegistry,
    get_converter_registry,
)


class TestConverterRegistryBasicOperations:
    """Test basic registry operations."""

    def test_get_converter_returns_supporting_converter(self) -> None:
        """Test get_converter returns a converter that supports the MIME type."""
        registry = ConverterRegistry()

        result = registry.get_converter("application/pdf")
        assert result is not None
        assert result.supports_mime_type("application/pdf") is True

        result = registry.get_converter("text/plain")
        assert result is not None
        assert result.supports_mime_type("text/plain") is True

    def test_get_converter_returns_none_for_unsupported_type(self) -> None:
        """Test get_converter returns None for unsupported MIME types."""
        registry = ConverterRegistry()

        result = registry.get_converter("image/jpeg")
        assert result is None

    def test_is_supported_returns_correct_boolean(self) -> None:
        """Test is_supported correctly identifies supported and unsupported MIME types."""
        registry = ConverterRegistry()

        assert registry.is_supported("application/pdf") is True
        assert registry.is_supported("text/plain") is True
        assert registry.is_supported("text/markdown") is True
        assert registry.is_supported("image/jpeg") is False
        assert registry.is_supported("video/mp4") is False


class TestConverterRegistryCaching:
    """Test caching behavior in ConverterRegistry."""

    def test_repeated_lookups_work_consistently(self) -> None:
        """Test that repeated lookups return consistent results."""
        registry = ConverterRegistry()

        # First lookup
        result1 = registry.get_converter("application/pdf")
        assert result1 is not None

        # Second lookup should return same result
        result2 = registry.get_converter("application/pdf")
        assert result2 is not None
        assert isinstance(result1, type(result2))

        # Unsupported type should consistently return None
        result3 = registry.get_converter("image/jpeg")
        assert result3 is None
        result4 = registry.get_converter("image/jpeg")
        assert result4 is None


class TestConverterRegistryThreadSafety:
    """Test thread safety of ConverterRegistry operations."""

    def test_concurrent_lookups_are_thread_safe(self) -> None:
        """Test that concurrent converter lookups are handled safely."""
        registry = ConverterRegistry()

        def lookup_converter(mime_type: str) -> bool:
            converter = registry.get_converter(mime_type)
            return converter is not None

        # Perform concurrent lookups with known supported types
        mime_types = ["application/pdf", "text/plain", "text/markdown"] * 20
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(lookup_converter, mt) for mt in mime_types]
            results = [f.result() for f in futures]

        # All supported types should return True
        assert all(results)
        assert len(results) == 60


class TestConverterRegistryMimeTypeHandling:
    """Test MIME type specific handling in ConverterRegistry."""

    def test_case_sensitive_mime_type_matching(self) -> None:
        """Test that MIME type matching is case-sensitive."""
        registry = ConverterRegistry()

        # Exact match should work
        assert registry.get_converter("application/pdf") is not None

        # Case variations should not match
        assert registry.get_converter("Application/PDF") is None
        assert registry.get_converter("APPLICATION/PDF") is None
        assert registry.get_converter("application/PDF") is None

    def test_document_conversion_mime_types_handling(self) -> None:
        """Test handling of common document conversion MIME types."""
        registry = ConverterRegistry()

        document_types = [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "text/plain",
            "text/markdown",
        ]

        # All document types should be supported
        for mime_type in document_types:
            assert registry.is_supported(mime_type) is True
            assert registry.get_converter(mime_type) is not None

        # Non-document types should not be supported
        assert registry.is_supported("image/jpeg") is False
        assert registry.is_supported("audio/mp3") is False


class TestConverterRegistryDependencyInjection:
    """Test dependency injection functionality."""

    @pytest.mark.asyncio
    async def test_get_converter_registry_yields_registry_instance(self) -> None:
        """Test that get_converter_registry yields a ConverterRegistry instance."""
        registry = get_converter_registry()

        assert isinstance(registry, ConverterRegistry)

        # Should be able to use the registry
        assert hasattr(registry, "register")
        assert hasattr(registry, "get_converter")
        assert hasattr(registry, "is_supported")

    @pytest.mark.asyncio
    async def test_get_converter_registry_returns_same_instance(self) -> None:
        """Test that get_converter_registry returns the same singleton instance."""
        registry1 = get_converter_registry()

        registry2 = get_converter_registry()

        # Should be the same instance
        assert registry1 is registry2


class TestConverterRegistryDefaultBehavior:
    """Test default behavior with pre-registered converters."""

    def test_default_registry_supports_common_formats(self) -> None:
        """Test that default registry supports expected document conversion formats."""
        registry = ConverterRegistry()

        # Common formats that should be supported
        supported_formats = [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "text/plain",
            "text/markdown",
        ]

        for format_type in supported_formats:
            assert registry.is_supported(format_type) is True, f"Format {format_type} should be supported"

        # Formats that should not be supported
        unsupported_formats = ["image/jpeg", "audio/mp3", "video/mp4", "application/zip"]

        for format_type in unsupported_formats:
            assert registry.is_supported(format_type) is False, f"Format {format_type} should not be supported"
