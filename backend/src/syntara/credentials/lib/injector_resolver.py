"""InjectorResolver — resolves {{field_id}} templates in credential type injectors.

Transforms injector templates into resolved configuration by substituting
template placeholders with decrypted credential field values. Used by the
workflow engine to inject credentials into activity execution contexts.
"""

import re
from dataclasses import dataclass, field
from typing import Any

TEMPLATE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


@dataclass(frozen=True)
class ResolvedInjectors:
    """Result of resolving injector templates with decrypted field values."""

    extra_vars: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    file: dict[str, str] = field(default_factory=dict)


def _resolve_value(value: Any, decrypted_inputs: dict[str, Any]) -> Any:  # noqa: ANN401
    """Resolve a single value — substitute {{field_id}} templates.

    If the value is a string containing {{field_id}} placeholders, each is
    replaced with the corresponding decrypted input value (or empty string
    if the field is not present).

    Non-string values are returned as-is.
    """
    if not isinstance(value, str):
        return value

    def replacer(match: re.Match[str]) -> str:
        field_id = match.group(1)
        resolved = decrypted_inputs.get(field_id, "")
        return str(resolved) if resolved is not None else ""

    return TEMPLATE_PATTERN.sub(replacer, value)


def _resolve_section(section: dict[str, Any], decrypted_inputs: dict[str, Any]) -> dict[str, Any]:
    """Resolve all template values in a single injector section."""
    return {key: _resolve_value(value, decrypted_inputs) for key, value in section.items()}


class InjectorResolver:
    """Resolves credential type injector templates with decrypted field values."""

    @staticmethod
    def resolve(injectors: dict[str, Any], decrypted_inputs: dict[str, Any]) -> ResolvedInjectors:
        """Resolve injector templates into structured configuration.

        Args:
            injectors: Injector definition from CredentialType (extra_vars, env, file sections).
            decrypted_inputs: Decrypted field values from SecretService.

        Returns:
            ResolvedInjectors with all {{field_id}} placeholders replaced.

        """
        return ResolvedInjectors(
            extra_vars=_resolve_section(injectors.get("extra_vars", {}), decrypted_inputs),
            env=_resolve_section(injectors.get("env", {}), decrypted_inputs),
            file=_resolve_section(injectors.get("file", {}), decrypted_inputs),
        )
