"""Project-name patterns for role assignments that cover several projects.

A pattern is a project name in which ``*`` matches any run of characters
(including none), for example ``pay*`` matches ``payments`` and ``payroll``.
Matching is case-sensitive and always against the project's current name.

Pattern assignments are deny-only: the resolver expands them into
project-scoped deny statements for every project whose name matches and
never emits allow statements from them.
"""

import re

from syntara.core.constants import FieldLimits

__all__ = [
    "PROJECT_PATTERN_WILDCARD",
    "project_pattern_matches",
    "project_pattern_to_like",
    "validate_project_pattern",
]

PROJECT_PATTERN_WILDCARD = "*"
LIKE_ESCAPE_CHAR = "\\"

_ALLOWED_CHARS = re.compile(r"^[a-zA-Z0-9:_*-]+$")


def validate_project_pattern(pattern: str) -> str | None:
    """Return a user-facing error message for an invalid pattern, or None when valid."""
    if len(pattern) > FieldLimits.NAME_MAX_LENGTH:
        return f"project_pattern must be at most {FieldLimits.NAME_MAX_LENGTH} characters"
    if not _ALLOWED_CHARS.match(pattern):
        return "project_pattern may only contain letters, digits, ':', '_', '-' and the wildcard '*'"
    if PROJECT_PATTERN_WILDCARD not in pattern:
        return "project_pattern must contain '*'; use project_id for a single project"
    if not pattern.strip(PROJECT_PATTERN_WILDCARD):
        return (
            "project_pattern '*' matches every project; omit project_id and "
            "project_pattern for a system-wide assignment"
        )
    return None


def project_pattern_to_like(pattern: str) -> str:
    """Translate a pattern into a SQL ``LIKE`` expression escaped with a backslash.

    ``_`` and ``%`` are LIKE wildcards but literal characters in a pattern,
    so they (and the escape character itself) are escaped before ``*`` is
    turned into ``%``.
    """
    escaped = (
        pattern.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", f"{LIKE_ESCAPE_CHAR}%")
        .replace("_", f"{LIKE_ESCAPE_CHAR}_")
    )
    return escaped.replace(PROJECT_PATTERN_WILDCARD, "%")


def project_pattern_matches(pattern: str, project_name: str) -> bool:
    """Return True when *project_name* matches *pattern* (same semantics as the SQL query)."""
    regex = ".*".join(re.escape(part) for part in pattern.split(PROJECT_PATTERN_WILDCARD))
    return re.fullmatch(regex, project_name, flags=re.DOTALL) is not None
