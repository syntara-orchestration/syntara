"""Audit event data sanitization utilities with pluggable PII detectors."""

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

REDACTED = "[REDACTED]"

# PII Detector Interface
PIIDetector = Callable[[Any, str], Any | None]

# Compiled regex pattern for email detection - more efficient than compiling on each call
# Matches: word chars/dots/hyphens + @ + word chars/dots/hyphens + . + 2+ word chars
# Uses word boundaries and proper validation while being aggressive for security
EMAIL_PATTERN = re.compile(r"\b[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

# Regex to split on uppercase letters while preserving the uppercase letter with the following word
# Handles: camelCase, PascalCase, ALL_CAPS sequences
CAMEL_CASE_PATTERN = re.compile(r"([A-Z]+(?=[A-Z][a-z]|\b)|[A-Z][a-z]+|[a-z]+|[0-9]+)")


def redact_by_partial_key(patterns: list[str]) -> PIIDetector:  # noqa: C901
    """Create a detector that redacts values based on partial key matching with delimiter boundaries.

    This detector checks if any of the provided patterns appear in the key name
    bounded by common delimiters: underscore (_), hyphen (-), or dot (.).
    Matching is case-insensitive. This prevents trivial bypass of exact-match
    redaction while avoiding false positives from substring matching.

    Security Note: Matches patterns with delimiter boundaries like:
    - password -> user_password, api-password, config.password, _password_, password_hash
    - secret -> api_secret, client-secret, db.secret, _secret_key
    - token -> auth_token, access-token, session.token, _token_

    Does NOT match patterns within words (e.g., 'password' won't match 'passwords123').

    Supported delimiters: underscore (_), hyphen (-), dot (.)

    Args:
        patterns: List of sensitive terms to match within key names

    Returns:
        PIIDetector function that redacts values for keys containing any pattern with delimiter boundaries

    """
    patterns_lower = tuple(p.lower() for p in patterns)
    # Delimiters that act as word boundaries
    delimiters = {"_", "-", "."}

    def _matches_with_delimiter(key_lower: str, pattern: str, delim: str) -> bool:
        """Check if pattern matches with given delimiter as boundary."""
        # Determine if pattern has delimiters at start/end
        has_start_delim = pattern.startswith(delim)
        has_end_delim = pattern.endswith(delim)

        # Prefix check: pattern<delim>*
        if not has_end_delim:
            if key_lower.startswith(pattern + delim):
                return True
        elif key_lower.startswith(pattern):
            return True

        # Suffix check: *<delim>pattern
        if not has_start_delim:
            if key_lower.endswith(delim + pattern):
                return True
        elif key_lower.endswith(pattern):
            return True

        # Middle check: *<delim>pattern<delim>*
        if not has_start_delim and not has_end_delim:
            middle = delim + pattern + delim
        elif has_start_delim and not has_end_delim:
            middle = pattern + delim
        elif not has_start_delim and has_end_delim:
            middle = delim + pattern
        else:
            middle = pattern

        return middle in key_lower

    def detector(value: Any, key: str) -> Any | None:  # noqa: ANN401
        if isinstance(value, bool):
            return None

        key_lower = key.lower()

        for pattern in patterns_lower:
            # Exact match
            if key_lower == pattern:
                return REDACTED

            # Check each delimiter type for boundary matches
            for delim in delimiters:
                if _matches_with_delimiter(key_lower, pattern, delim):
                    return REDACTED

        return None

    return detector


def redact_by_camel_case_key(patterns: list[str]) -> PIIDetector:
    """Create a detector that redacts values based on camelCase key matching.

    This detector splits camelCase keys into words (at uppercase transitions) and
    checks if any word matches a sensitive pattern. This prevents bypass via camelCase
    naming conventions commonly used in external APIs (OpenAI, OIDC, etc.).

    Security Note: Matches patterns within camelCase keys like:
    - password -> userPassword, adminPassword, passwordHash
    - secret -> apiSecret, clientSecret, secretKey
    - token -> authToken, accessToken, refreshToken, tokenValue

    Handles both camelCase (starts lowercase) and PascalCase (starts uppercase).

    Does NOT match patterns within individual words (e.g., 'pass' won't match 'userPassport').

    Args:
        patterns: List of sensitive terms to match within camelCase key names

    Returns:
        PIIDetector function that redacts values for keys containing any pattern in camelCase words

    """
    patterns_lower = tuple(p.lower() for p in patterns)

    def detector(value: Any, key: str) -> Any | None:  # noqa: ANN401
        if isinstance(value, bool):
            return None

        # Split camelCase/PascalCase into words using regex
        # This handles: userPassword -> ['user', 'Password']
        #              PASSWORD -> ['PASSWORD']
        #              userPASSWORD -> ['user', 'PASSWORD']
        #              XMLParser -> ['XML', 'Parser']
        words = [word.lower() for word in CAMEL_CASE_PATTERN.findall(key)]

        # Check if any extracted word matches a pattern
        for word in words:
            if word in patterns_lower:
                return REDACTED

        return None

    return detector


def redact_email(value: Any, _: str) -> Any | None:  # noqa: ANN401
    """Detect and redact email addresses.

    Uses a pattern that catches most valid email formats while intentionally
    being more aggressive to avoid leaking PII. May redact some non-email strings
    that contain email-like patterns (e.g. "user@host.local", "config@v2.0.1").
    This over-matching is intentional for security - better to redact non-emails
    than to leak actual email addresses.
    """
    if not isinstance(value, str):
        return None

    if EMAIL_PATTERN.search(value):
        return "[EMAIL_REDACTED]"
    return None


class EventSanitizer:
    """Sanitizes event data using pluggable PII detectors."""

    def __init__(self, detectors: list[PIIDetector] | None = None, max_depth: int = 10) -> None:
        """Initialize the sanitizer with detectors and max depth."""
        self.detectors = detectors or []
        self.max_depth = max_depth

    def _apply_detectors(self, value: Any, key: str) -> Any:  # noqa: ANN401
        """Apply all detectors to a value."""
        for detector in self.detectors:
            result = detector(value, key)
            if result is not None:
                return result
        return value

    def _convert(
        self,
        obj: Any,  # noqa: ANN401
        key: str = "",
        traversal_stack: set[int] | None = None,
        ancestor_keys: tuple[str, ...] = (),
    ) -> Any:  # noqa: ANN401
        """Recursively convert and sanitize an object."""
        if traversal_stack is None:
            traversal_stack = set()

        if len(traversal_stack) >= self.max_depth:
            return "[MAX_DEPTH]"

        # Only track objects that can actually contain references.
        # Primitives (str, int, float, bool, None) are immutable and safe to reuse.
        if not isinstance(obj, (str, int, float, bool, type(None))):
            obj_id = id(obj)
            # Check if this object is already in the current traversal stack (true circular reference)
            if obj_id in traversal_stack:
                return "[CIRCULAR]"

            # Add to traversal stack before processing
            traversal_stack.add(obj_id)

            try:
                # Process the object
                return self._convert_by_type(obj, key, traversal_stack, ancestor_keys)
            finally:
                # Remove from traversal stack after processing
                traversal_stack.remove(obj_id)
        else:
            # Primitives don't need stack tracking
            return self._convert_by_type(obj, key, traversal_stack, ancestor_keys)

    def _sanitize_primitive(
        self,
        obj: Any,  # noqa: ANN401
        key: str,
        ancestor_keys: tuple[str, ...],
    ) -> Any:  # noqa: ANN401
        """Apply detectors using the leaf key and any inherited ancestor keys.

        Ancestors are populated only for mapping children named old/new (diff
        wrappers), so password_hash: {old, new} redacts leaf values without
        collapsing the wrapper or sweeping unrelated nests under keys like
        credentials. This is structural (not gated on data_type / CRUD paths).
        """
        for candidate_key in (key, *ancestor_keys):
            if not candidate_key:
                continue
            detected = self._apply_detectors(obj, candidate_key)
            if detected is not obj:
                return detected
        return obj

    def _convert_mapping(
        self,
        obj: Mapping[Any, Any],
        key: str,
        traversal_stack: set[int],
        ancestor_keys: tuple[str, ...],
    ) -> dict[str, Any]:
        """Convert a mapping, propagating parent key only into old/new wrappers."""
        result: dict[str, Any] = {}
        for raw_key, value in obj.items():
            child_key = str(raw_key)
            child_ancestors = (key, *ancestor_keys) if child_key in {"old", "new"} and key else ancestor_keys
            result[child_key] = self._convert(value, child_key, traversal_stack, child_ancestors)
        return result

    def _convert_by_type(
        self,
        obj: Any,  # noqa: ANN401
        key: str,
        traversal_stack: set[int],
        ancestor_keys: tuple[str, ...] = (),
    ) -> Any:  # noqa: ANN401
        """Convert object based on its type."""
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return self._sanitize_primitive(obj, key, ancestor_keys)

        if isinstance(obj, BaseModel):
            return self._convert(obj.model_dump(), key, traversal_stack, ancestor_keys)

        if isinstance(obj, Mapping):
            return self._convert_mapping(obj, key, traversal_stack, ancestor_keys)

        if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
            return [self._convert(item, key, traversal_stack, ancestor_keys) for item in obj]

        if isinstance(obj, (bytes, bytearray)):
            return obj.decode("utf-8", errors="replace")

        return str(obj)

    def sanitize[T: BaseModel](self, data: T) -> T:
        """Sanitize audit data and return a new instance with sanitized values.

        This method preserves the original type and returns a new instance
        rather than modifying the input in place.

        Args:
            data: The audit data model to sanitize

        Returns:
            A new instance of the same type with sanitized values

        """
        updates = {}

        for field_name, field_value in data:
            sanitized_value = self._convert(field_value, field_name)
            if sanitized_value != field_value:
                updates[field_name] = sanitized_value

        if not updates:
            return data

        return data.model_copy(update=updates)


# Fixed sanitizer with comprehensive PII detectors
# Patterns list shared between delimiter-based and camelCase detectors
CREDENTIAL_PATTERNS = [
    "password",
    "secret",
    "token",
    "key",
    "auth",
    "credential",
    "credentials",
    "session",
    "cookie",
    "jwt",
    "bearer",
    "authorization",
    "certificate",
    "cert",
    "pem",
    "oauth",
    "authentication",
]

sanitizer = EventSanitizer(
    detectors=[
        # Delimiter-based matching: snake_case, kebab-case, dot.notation
        redact_by_partial_key(CREDENTIAL_PATTERNS),
        # CamelCase matching: userPassword, apiSecret, clientSecret
        redact_by_camel_case_key(CREDENTIAL_PATTERNS),
        # Email detection
        redact_email,
    ]
)
