"""Keep advisory Publish drafts separate from executable message validation."""

import json
import re
from typing import Any
from uuid import UUID

from pydantic import StrictStr, ValidationError, field_validator
from sqlmodel import SQLModel

from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.workflow_engine.models.kafka_publish import KAFKA_PUBLISH_MAX_HEADERS, KafkaPublishParameters

_TEMPLATE = re.compile(r"\$\{[^}]+\}")
_FIELD_MESSAGES = {
    "integration_id": "Select a Kafka Integration using a literal resource UUID",
    "credential_id": "Select a runtime Kafka credential using a literal resource UUID for every connection mode",
    "topic": "Enter one literal Kafka topic name (1-249 characters)",
    "payload": "Enter a valid JSON payload; explicit JSON null is supported",
    "key": "Use a null key or an explicitly encoded UTF-8/Base64 value",
    "headers": "Use ordered headers or a full-value header template, with at most 128 entries",
}


class KafkaPublishDraftBindings(SQLModel):
    """Validate supplied resource IDs even when message fields are unfinished."""

    integration_id: StrictStr | None = None
    credential_id: StrictStr | None = None

    @field_validator("integration_id", "credential_id", mode="before")
    @classmethod
    def empty_reference(cls, value: object) -> object:
        """Normalize an unselected builder resource to an omitted binding."""
        return None if value == "" else value

    @field_validator("integration_id", "credential_id")
    @classmethod
    def literal_reference(cls, value: str | None) -> str | None:
        """Omissions are drafts; supplied references must remain literal UUIDs."""
        if value is not None:
            UUID(value)
        return value


def publish_bindings(definition: dict[str, Any], *, allow_incomplete: bool = False) -> list[KafkaPublishDraftBindings]:
    """Parse bindings without exposing message contents in validation exceptions."""
    configs: list[KafkaPublishDraftBindings] = []
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return configs
    try:
        for node in nodes:
            if not isinstance(node, dict) or node.get("type") != "kafka_publish":
                continue
            parameters = node.get("parameters", {})
            if not allow_incomplete:
                KafkaPublishParameters.model_validate(parameters)
            configs.append(KafkaPublishDraftBindings.model_validate(parameters))
    except ValidationError as exc:
        field = next((error["loc"][0] for error in exc.errors(include_input=False) if error["loc"]), None)
        msg = _FIELD_MESSAGES.get(str(field), "Invalid Kafka Publish configuration")
        raise SafeValueError(msg) from None
    return configs


def _header_issues(parameters: KafkaPublishParameters) -> list[tuple[str, str]]:
    if not isinstance(parameters.headers, list):
        return []
    issues: list[tuple[str, str]] = []
    if len(parameters.headers) > KAFKA_PUBLISH_MAX_HEADERS:
        issues.append(("headers", _FIELD_MESSAGES["headers"]))
    for index, header in enumerate(parameters.headers):
        try:
            header.name.encode("utf-8")
            if header.value is not None and not _TEMPLATE.search(header.value.value):
                header.value.decode()
        except (ValueError, UnicodeError):
            issues.append((f"headers.{index}", _FIELD_MESSAGES["headers"]))
    return issues


def _parameter_issues(node: dict[str, Any]) -> list[tuple[str, str]]:
    try:
        parameters = KafkaPublishParameters.model_validate(node.get("parameters", {}))
    except ValidationError as exc:
        return [
            (
                ".".join(str(part) for part in error["loc"]),
                _FIELD_MESSAGES.get(str(error["loc"][0]) if error["loc"] else "", "Invalid Kafka Publish parameters"),
            )
            for error in exc.errors(include_input=False, include_context=False)
        ]
    issues = _header_issues(parameters)
    metadata = node.get("metadata")
    if isinstance(metadata, dict) and "__kafkaPublishPayloadDraft" in metadata:
        issues.append(("payload", _FIELD_MESSAGES["payload"]))
    try:
        json.dumps(parameters.payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        issues.append(("payload", _FIELD_MESSAGES["payload"]))
    if parameters.key is not None and not _TEMPLATE.search(parameters.key.value):
        try:
            parameters.key.decode()
        except (ValueError, UnicodeError):
            issues.append(("key.value", _FIELD_MESSAGES["key"]))
    return issues


def collect_kafka_publish_findings(definition: dict[str, Any]) -> list[ValidationFinding]:
    """Report incomplete or invalid steps for Run/Publish without echoing values."""
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [
        ValidationFinding(
            severity=ValidationSeverity.error,
            category=ValidationCategory.schema_violation,
            message=message,
            node_id=node.get("id") if isinstance(node.get("id"), str) else None,
            field_path=f"parameters.{field}" if field else "parameters",
        )
        for node in nodes
        if isinstance(node, dict) and node.get("type") == "kafka_publish"
        for field, message in _parameter_issues(node)
    ]
