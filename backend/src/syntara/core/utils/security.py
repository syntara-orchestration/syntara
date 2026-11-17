"""Security validation utilities for user-provided content.

This module contains validation functions for securing user-provided content
like CSS overrides against common attack vectors (XSS, data exfiltration, etc.).
"""

import re

# CSS Unicode escape pattern: \XX or \XXXXXX (1-6 hex digits, optional trailing space)
# Used to normalize CSS before security validation to prevent bypasses via \75rl( etc.
_CSS_UNICODE_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})\s?")

# CSS identity escape pattern: \ followed by any non-hex-digit, non-newline character
# Resolves to that character (backslash dropped). Prevents bypasses via u\rl(, @\import, etc.
_CSS_IDENTITY_ESCAPE = re.compile(r"\\([^0-9a-fA-F\r\n])")

# CSS comment pattern: /* ... */ (DOTALL to match across newlines)
# Prevents bypasses via behavior/**/: url(x.htc), url/**/(http://evil.com), etc.
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# Maximum valid Unicode codepoint (U+10FFFF per CSS and Unicode specs)
_MAX_UNICODE_CODEPOINT = 0x10FFFF


def normalize_css(css: str) -> str:
    r"""Normalize CSS to prevent security check bypasses.

    Performs three normalization steps:
    1. Strips CSS comments (/* ... */) to prevent bypasses like behavior/**/: url(x.htc)
    2. Normalizes numeric hex escapes: \\XX or \\XXXXXX (1-6 hex digits, optional trailing space)
       Example: \75rl( → url(, \40import → @import
    3. Normalizes identity escapes: \\ followed by any non-hex-digit, non-newline character
       Example: u\rl( → url(, @\\import → @import

    This prevents bypassing security checks via comments, numeric escapes, and identity escapes.

    Follows CSS spec for escape sequences. Numeric codepoints above U+10FFFF
    are replaced with U+FFFD per CSS spec.

    Args:
        css: Raw CSS string that may contain comments and/or CSS escapes.

    Returns:
        CSS with comments stripped and all escape sequences converted to their character equivalents.

    Examples:
        >>> normalize_css(r"url\\(\\)")
        'url()'
        >>> normalize_css(r"\75rl(http://evil.com)")
        'url(http://evil.com)'
        >>> normalize_css("behavior/**/: url(x.htc)")
        'behavior: url(x.htc)'

    """

    def replace_numeric_escape(match: re.Match[str]) -> str:
        codepoint = int(match.group(1), 16)
        # CSS spec: codepoints above U+10FFFF are invalid, replaced with U+FFFD
        if codepoint > _MAX_UNICODE_CODEPOINT:
            return "�"
        return chr(codepoint)

    # Strip CSS comments (/* ... */)
    css = _CSS_COMMENT.sub("", css)
    # Normalize numeric hex escapes (\75 → u)
    css = _CSS_UNICODE_ESCAPE.sub(replace_numeric_escape, css)
    # Normalize identity escapes (\r → r)
    return _CSS_IDENTITY_ESCAPE.sub(r"\1", css)


def validate_css_security(css: str) -> None:
    """Validate CSS for security vulnerabilities.

    Rejects patterns that enable data exfiltration or code execution:
    - url() - can exfiltrate data via background-image, @font-face, etc.
    - @import - can load external stylesheets
    - Attribute selectors - can exfiltrate form values character by character
    - expression() - old IE code execution vector
    - behavior: - old IE code execution vector

    Args:
        css: CSS string to validate (will be normalized before checking).

    Raises:
        ValueError: If the CSS contains dangerous patterns.

    Examples:
        >>> validate_css_security("color: red;")  # OK
        >>> validate_css_security("background: url(http://evil.com);")
        Traceback (most recent call last):
        ...
        ValueError: CSS override cannot contain url() - it enables data exfiltration

    """
    # Normalize CSS before validation to prevent bypasses
    normalized = normalize_css(css)
    normalized_lower = normalized.lower()

    # Reject url() - can exfiltrate data via background-image, etc.
    if "url(" in normalized_lower:
        msg = "CSS override cannot contain url() - it enables data exfiltration"
        raise ValueError(msg)

    # Reject @import - can load external stylesheets
    if "@import" in normalized_lower:
        msg = "CSS override cannot contain @import - it enables loading external resources"
        raise ValueError(msg)

    # Reject attribute selectors - can exfiltrate form values character by character
    # NOTE: Over-blocks legitimate bracket uses in string literals (e.g., content: "[Required]").
    # Accepted trade-off: over-blocking is safe; parsing strings would be complex and error-prone.
    if "[" in normalized and "]" in normalized:
        msg = "CSS override cannot contain attribute selectors - they enable data exfiltration"
        raise ValueError(msg)

    # Reject expression() - old IE code execution vector
    if "expression(" in normalized_lower:
        msg = "CSS override cannot contain expression() - it enables code execution"
        raise ValueError(msg)

    # Reject behavior: - old IE code execution vector
    if "behavior:" in normalized_lower:
        msg = "CSS override cannot contain behavior: - it enables code execution"
        raise ValueError(msg)
