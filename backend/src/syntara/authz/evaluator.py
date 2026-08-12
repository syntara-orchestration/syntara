"""Authorization policy evaluator backed by regopy."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Protocol

import structlog

from syntara.authz import _rego_runtime

logger = structlog.stdlib.get_logger(__name__)

_RESULT_FIELDS = frozenset({"allow", "deny", "matched_policy", "denial_reason", "denied_by", "allowed_projects"})

_NOT_CONDITION_KEYS: dict[str, tuple[str, str]] = {
    "user_labels_not": ("user", "labels"),
    "resource_labels_not": ("resource", "labels"),
}


def _has_not_conditions(policies: list[dict[str, Any]]) -> bool:
    """Check whether any policy uses a ``*_not`` condition key."""
    return any(not_key in (policy.get("conditions") or {}) for policy in policies for not_key in _NOT_CONDITION_KEYS)


def _resolve_not_conditions(authz_input: dict[str, Any]) -> dict[str, Any]:
    """Pre-evaluate ``*_not`` conditions in Python to work around regopy limitations.

    regopy's ``every`` block has a bug where ``not x == y`` always evaluates
    to ``true``, breaking negative label conditions.  This function checks
    each ``*_not`` condition against the actual input and either removes it
    (condition passes — no label matches) or marks the policy as unmatchable
    (condition fails — a label matches the excluded value).
    """
    policies = authz_input.get("effective_policies")
    if not policies or not _has_not_conditions(policies):
        return authz_input

    result = copy.deepcopy(authz_input)

    for policy in result["effective_policies"]:
        conditions = policy.get("conditions")
        if not conditions:
            continue

        for not_key, (input_section, label_field) in _NOT_CONDITION_KEYS.items():
            not_labels = conditions.pop(not_key, None)
            if not not_labels:
                continue

            actual_labels = result.get(input_section, {}).get(label_field, {})
            if any(actual_labels.get(k) == v for k, v in not_labels.items()):
                conditions["__not_condition_failed__"] = {"__impossible__": "__never__"}

    return result


_HEALTHCHECK_INPUT: dict[str, Any] = {
    "user": {"id": "healthcheck", "labels": {}, "metadata": {}},
    "action": "read",
    "resource": {"type": "healthcheck", "id": "", "project": "", "labels": {}, "metadata": {}},
    "groups": [],
    "effective_policies": [],
}


class AuthzEvaluator(Protocol):
    """Shared evaluator contract for authorization decisions."""

    def start(self) -> None:
        """Initialize any resources needed before the evaluator can run."""

    async def stop(self) -> None:
        """Release any evaluator resources during shutdown."""

    async def health(self) -> bool:
        """Return whether the evaluator is ready to answer queries."""

    def evaluate(self, authz_input: dict[str, Any]) -> dict[str, Any]:
        """Evaluate an authorization input document."""


def get_default_policy_path() -> Path:
    """Return the default bundled Rego policy path."""
    return Path(__file__).with_name("rego") / "authz.rego"


def evaluate_policy_input(authz_input: dict[str, Any], *, policy_path: Path | None = None) -> dict[str, Any]:
    """Evaluate a single authorization input with a temporary interpreter.

    This helper is used by tests so they exercise the same regopy-based
    normalization path as the runtime evaluator without requiring FastAPI app
    state or a long-lived interpreter instance.
    """
    module_path = policy_path or get_default_policy_path()
    resolved_input = _resolve_not_conditions(authz_input)
    raw = _rego_runtime.evaluate_once(module_path.name, module_path.read_text(encoding="utf-8"), resolved_input)
    return _normalize_raw(raw)


class RegoEvaluator:
    """In-process authorization evaluator using regopy."""

    def __init__(self, policy_path: Path | None = None) -> None:
        """Configure the evaluator with the authz policy path."""
        self._policy_path = policy_path or get_default_policy_path()

    def start(self) -> None:
        """Load the Rego policy into the isolated runtime module."""
        path = self._policy_path
        _rego_runtime.init(path.name, path.read_text(encoding="utf-8"))
        logger.info("Authorization evaluator started", policy_path=str(path))

    async def stop(self) -> None:
        """Release the interpreter during shutdown."""
        _rego_runtime.shutdown()
        logger.info("Authorization evaluator stopped")

    async def health(self) -> bool:
        """Check the evaluator can answer a trivial decision query."""
        if not _rego_runtime.is_ready():
            return False
        try:
            self.evaluate(_HEALTHCHECK_INPUT)
        except Exception:
            logger.exception("Authorization evaluator healthcheck failed")
            return False
        return True

    def evaluate(self, authz_input: dict[str, Any]) -> dict[str, Any]:
        """Evaluate an authorization input against the loaded policy."""
        if not _rego_runtime.is_ready():
            msg = "Authorization evaluator not started"
            raise RuntimeError(msg)
        resolved_input = _resolve_not_conditions(authz_input)
        raw = _rego_runtime.evaluate(resolved_input)
        return _normalize_raw(raw)


def _normalize_raw(raw_result: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw Rego result dict into the public authz result shape."""
    matched_policies = sorted(raw_result.get("_matched_policies", []))
    denied_policies = sorted(raw_result.get("_denied_by_policies", []))

    normalized = {key: raw_result.get(key) for key in _RESULT_FIELDS if key in raw_result}
    if not normalized.get("matched_policy") and matched_policies:
        normalized["matched_policy"] = matched_policies[0]
    if not normalized.get("denied_by") and denied_policies:
        normalized["denied_by"] = denied_policies[0]
    return normalized
