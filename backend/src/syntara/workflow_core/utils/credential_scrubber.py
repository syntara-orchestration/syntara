"""Credential scrubbing utility for workflow execution state.

Two layers of scrubbing:
  1. Key-name scrubbing: replaces values of known credential keys with [REDACTED].
  2. Value-based scrubbing: replaces actual decrypted secret values found in
     arbitrary string content (stdout, HTTP response bodies, etc.).
"""

import json
from collections.abc import Collection
from typing import Any

REDACTED = "[REDACTED]"

MIN_SECRET_LENGTH = 4

# Internal keys used to pass resolved credentials through workflow state
_INTERNAL_CREDENTIAL_KEYS = frozenset(
    {
        "_resolved_credentials",
        "activity_credentials",
        "_secret_values",
        "_has_credentials",
    }
)


def _build_credential_keys() -> frozenset[str]:
    """Derive scrub keys from GA credential type injector definitions.

    Automatically covers all injector extra_vars keys from preseed types,
    so new credential types don't need manual additions here.
    """
    from syntara.credentials.lib.preseed import GA_CREDENTIAL_TYPES  # noqa: PLC0415

    keys: set[str] = set(_INTERNAL_CREDENTIAL_KEYS)
    for type_def in GA_CREDENTIAL_TYPES:
        keys.update(type_def["injectors"].get("extra_vars", {}).keys())
    return frozenset(keys)


CREDENTIAL_KEYS = _build_credential_keys()


def has_credential_keys(obj: Any) -> bool:  # noqa: ANN401
    """Check if a value contains any credential keys (recursive).

    Used by the PayloadCodec to decide whether a payload needs encryption.
    """
    if isinstance(obj, dict):
        if any(k in CREDENTIAL_KEYS for k in obj):
            return True
        return any(has_credential_keys(v) for v in obj.values())
    if isinstance(obj, list):
        return any(has_credential_keys(item) for item in obj)
    return False


def ensure_resolved_credentials_dict(resolved_creds: Any) -> dict[str, Any]:  # noqa: ANN401
    """Normalize _resolved_credentials from Temporal to a dict.

    Temporal may deserialize nested JSON payloads as strings rather than dicts.
    This ensures we always have a dict for downstream credential processing.

    Returns empty dict if the input cannot be parsed.
    """
    if isinstance(resolved_creds, dict):
        return resolved_creds
    if isinstance(resolved_creds, str):
        try:
            result: dict[str, Any] = json.loads(resolved_creds)
            return result
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def scrub_credentials(data: Any) -> Any:  # noqa: ANN401
    """Strip credential-related keys from a data structure.

    Deep copies the input and replaces values of credential keys with [REDACTED].
    Non-credential data is preserved unchanged.

    Args:
        data: Dict, list, or other value to scrub.

    Returns:
        Deep copy with credential values redacted.

    """
    if data is None:
        return None

    if isinstance(data, dict):
        scrubbed = {}
        for key, value in data.items():
            if key in CREDENTIAL_KEYS:
                scrubbed[key] = REDACTED
            else:
                scrubbed[key] = scrub_credentials(value)
        return scrubbed

    if isinstance(data, list):
        return [scrub_credentials(item) for item in data]

    return data


def scrub_credential_values(data: Any, secret_values: Collection[str]) -> Any:  # noqa: ANN401
    """Replace actual credential values found in string content.

    Searches all string fields recursively for occurrences of known
    decrypted secret values and replaces them with [REDACTED].
    Skips values shorter than MIN_SECRET_LENGTH to avoid false positives.

    Args:
        data: Dict, list, string, or other value to scrub.
        secret_values: Collection of actual decrypted secret strings to search for.

    Returns:
        Deep copy with embedded secret values replaced.

    """
    if not secret_values:
        return data

    if data is None:
        return None

    if isinstance(data, str):
        result = data
        for value in sorted(secret_values, key=len, reverse=True):
            if value and len(value) >= MIN_SECRET_LENGTH and value in result:
                result = result.replace(value, REDACTED)
        return result

    if isinstance(data, dict):
        return {k: scrub_credential_values(v, secret_values) for k, v in data.items()}

    if isinstance(data, list):
        return [scrub_credential_values(item, secret_values) for item in data]

    return data
