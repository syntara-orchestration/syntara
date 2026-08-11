"""Registry for managing document converters by MIME type.

This module provides the ConverterRegistry class that manages the mapping
between MIME types and their corresponding document converters.
"""

import threading

from syntara.files.document_conversion.converters import (
    DocumentConverter,
    MarkdownConverter,
    MSWordConverter,
    PDFConverter,
    TextConverter,
)


class ConverterRegistry:
    """Registry for mapping MIME types to document converters.

    Manages converter instances and provides lookup functionality to find
    the appropriate converter for a given file type.
    """

    def __init__(self) -> None:
        """Initialize empty converter registry.

        Example:
            registry = ConverterRegistry()
            registry.register(MSWordConverter())
            converter = registry.get_converter("application/pdf")

        """
        self._converters: list[DocumentConverter] = []
        self._mime_type_cache: dict[str, DocumentConverter | None] = {}
        self._lock = threading.Lock()

        self.register(PDFConverter())
        self.register(MSWordConverter())
        self.register(MarkdownConverter())
        self.register(TextConverter())

    def register(self, converter: DocumentConverter) -> None:
        """Register a converter with the registry.

        Args:
            converter: DocumentConverter instance to register

        Example:
            registry = ConverterRegistry()
            registry.register(MSWordConverter())
            registry.register(MarkdownConverter())

        """
        with self._lock:
            self._converters.append(converter)
            # Clear cache when new converters are registered
            self._mime_type_cache.clear()

    def get_converter(self, mime_type: str) -> DocumentConverter | None:
        """Get converter that supports the specified MIME type.

        Args:
            mime_type: MIME type to find converter for

        Returns:
            DocumentConverter instance if found, None otherwise

        Example:
            registry = ConverterRegistry()
            registry.register(MSWordConverter())

            pdf_converter = registry.get_converter("application/pdf")
            assert pdf_converter is not None

            unsupported = registry.get_converter("image/jpeg")
            assert unsupported is None

        """
        with self._lock:
            # Check cache first
            if mime_type in self._mime_type_cache:
                return self._mime_type_cache[mime_type]

            # Search for supporting converter
            for converter in self._converters:
                if converter.supports_mime_type(mime_type):
                    self._mime_type_cache[mime_type] = converter
                    return converter

            # No converter found
            self._mime_type_cache[mime_type] = None
            return None

    def is_supported(self, mime_type: str) -> bool:
        """Check if the MIME type is supported by any registered converter.

        Args:
            mime_type: MIME type to check

        Returns:
            True if at least one converter supports this MIME type

        Example:
            registry = ConverterRegistry()
            registry.register(MSWordConverter())

            assert registry.is_supported("application/pdf") is True
            assert registry.is_supported("image/jpeg") is False

        """
        return self.get_converter(mime_type) is not None


# ===================================================
# Generator for dependency injection
# ---------------------------------------------------
_converter_registry: ConverterRegistry = ConverterRegistry()


def get_converter_registry() -> ConverterRegistry:
    """Create a ConverterRegistry for dependency injection.

    Returns:
        ConverterRegistry for dependency injection

    Example:
        from syntara.files.document_conversion.registry import (
            get_converter_registry,
        )

        registry: ConverterRegistry = get_converter_registry()
        converter = registry.get_converter("application/pdf")
        if converter:
            result = await converter.convert(input_path, output_path)

    """
    return _converter_registry


# ===================================================
