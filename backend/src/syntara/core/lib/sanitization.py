"""Shared string sanitization utilities."""

from __future__ import annotations

import re

_CONTROL_CHAR_TABLE = str.maketrans("", "", "".join(chr(c) for c in (*range(0x20), 0x7F)))
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")

# Patterns that allow specific whitespace characters through.
# Used by credential field validation where tabs and newlines are acceptable.
# Single-line: allow horizontal tab (0x09) only.
CONTROL_CHAR_SINGLELINE_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
# Multiline: allow horizontal tab (0x09), line feed (0x0a), carriage return (0x0d).
CONTROL_CHAR_MULTILINE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_control_chars(value: str) -> str:
    """Remove ASCII control characters (0x00-0x1F, 0x7F) from a string."""
    return value.translate(_CONTROL_CHAR_TABLE)


def has_control_chars(value: str) -> bool:
    """Return True if the string contains any ASCII control characters."""
    return _CONTROL_CHAR_RE.search(value) is not None


_NAMED_ESCAPES: dict[int, str] = {
    0x09: "\\t",
    0x0A: "\\n",
    0x0D: "\\r",
}


def escape_control_chars(value: str) -> str:
    r"""Replace ASCII control characters with their Unicode escape representation.

    For example, a newline becomes ``\n``, a null byte becomes ``\x00``.
    This preserves information for logging and diagnostics rather than
    silently discarding characters.
    """

    def _replace(m: re.Match[str]) -> str:
        cp = ord(m.group())
        return _NAMED_ESCAPES.get(cp, f"\\x{cp:02x}")

    return _CONTROL_CHAR_RE.sub(_replace, value)
