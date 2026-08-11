"""Document conversion service type definitions."""

from enum import Enum


class ConversionState(str, Enum):
    """Enumeration of possible document conversion states."""

    SUCCESS = ("success",)
    FAILED = ("failed",)
    SKIPPED = ("skipped",)
