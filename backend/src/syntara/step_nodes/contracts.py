"""SDK contracts without importing an SDK checkout or choosing a transport."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from jsonschema import Draft7Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from pydantic import ConfigDict, Field, ValidationError
from referencing import Registry
from referencing.exceptions import Unresolvable
from sqlmodel import SQLModel

if TYPE_CHECKING:
    from collections.abc import Mapping


class StepContractError(ValueError):
    """A safe contract diagnostic that never includes invocation values."""


@dataclass(frozen=True)
class StepInvocation:
    """Transient execution request; never persist this object in Temporal history."""

    node_name: str
    version: str
    image: str
    entrypoint: str
    inputs: dict[str, Any] = field(repr=False)
    credentials: dict[str, Any] = field(repr=False)
    workflow_context: dict[str, Any] = field(default_factory=dict, repr=False)
    execution_timeout_seconds: int = 300

    def payload(self) -> dict[str, Any]:
        """Return only the SDK stdin contract, separate from image selection."""
        return deepcopy(
            {"inputs": self.inputs, "credentials": self.credentials, "workflow_context": self.workflow_context}
        )


class StepResult(SQLModel):
    """The SDK StandardOutputWrapper, validated before workflow persistence."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)  # type: ignore[assignment]

    Result: Any = Field(repr=False)
    StatusCode: int = Field(ge=0, le=255)
    StatusMessage: str = Field(default="", max_length=500, repr=False)
    ErrorMessage: str = Field(default="", max_length=10000, repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> StepResult:
        """Validate without reflecting remote content in an exception."""
        try:
            return cls.model_validate(payload)
        except ValidationError:
            message = "Invalid SDK result envelope"
            raise StepContractError(message) from None


class StepTransport(Protocol):
    """Execution-plane port implemented by a container, RPC, or local adapter.

    Must honor cancellation/timeouts and must not log or persist the payload.
    No automatic retry is implied by this interface.
    """

    async def execute(self, invocation: StepInvocation) -> Mapping[str, Any]:
        """Execute once and return the raw StandardOutputWrapper."""
        ...


class ManifestCatalog:
    """Explicitly supplied descriptors; no filesystem discovery or remote imports."""

    def __init__(self, manifests: list[dict[str, Any]]) -> None:
        """Validate and snapshot the descriptors selected by worker configuration."""
        self._manifests: dict[str, dict[str, Any]] = {}
        for manifest in manifests:
            try:
                metadata = manifest["metadata"]
                spec = manifest["spec"]
                execution = spec["execution"]
                name = metadata["name"]
                if (
                    manifest.get("apiVersion") != "syntara.io/v1alpha1"
                    or manifest.get("kind") != "NodeType"
                    or spec.get("category") != "action"
                    or execution.get("type") != "container"
                    or not isinstance(spec["inputs"], dict)
                    or spec["inputs"].get("type", "object") != "object"
                    or not all(
                        isinstance(value, str) and value
                        for value in (name, metadata["version"], execution["image"], execution["entrypoint"])
                    )
                    or name in self._manifests
                    or type(spec.get("executionTimeout", 300)) is not int
                    or spec.get("executionTimeout", 300) <= 0
                ):
                    message = "Invalid or duplicate SDK descriptor"
                    raise StepContractError(message)
                Draft7Validator.check_schema(spec["inputs"])
                self._manifests[name] = deepcopy(manifest)
            except (KeyError, TypeError, ValueError, SchemaError):
                message = "Invalid SDK descriptor"
                raise StepContractError(message) from None

    def descriptor(self, name: str) -> dict[str, Any]:
        """Return a defensive copy for palette or execution integration."""
        try:
            return deepcopy(self._manifests[name])
        except KeyError:
            message = "SDK descriptor is not registered"
            raise StepContractError(message) from None

    def invocation(
        self,
        name: str,
        inputs: dict[str, Any],
        credentials: dict[str, Any],
        workflow_context: dict[str, Any] | None = None,
    ) -> StepInvocation:
        """Validate complete inputs, then split fields marked sensitive by schema."""
        manifest = self.descriptor(name)
        schema = manifest["spec"]["inputs"]
        # Validators are local-only: unresolved external refs are rejected.
        try:
            valid = Draft7Validator(schema, registry=Registry(), format_checker=FormatChecker()).is_valid(inputs)
        except (Unresolvable, SchemaError, TypeError):
            message = "SDK input schema cannot be resolved locally"
            raise StepContractError(message) from None
        if not valid:
            message = "Inputs do not match the SDK descriptor"
            raise StepContractError(message)
        plain = deepcopy(inputs)
        secrets = deepcopy(credentials)
        for key, definition in schema.get("properties", {}).items():
            sensitive = isinstance(definition, dict) and (
                definition.get("secret") is True or definition.get("is_secret") is True
            )
            if sensitive and key in plain:
                if key in secrets:
                    message = "Duplicate sensitive SDK input"
                    raise StepContractError(message)
                secrets[key] = plain.pop(key)
        execution = manifest["spec"]["execution"]
        return StepInvocation(
            node_name=name,
            version=manifest["metadata"]["version"],
            image=execution["image"],
            entrypoint=execution["entrypoint"],
            inputs=plain,
            credentials=secrets,
            workflow_context=deepcopy(workflow_context or {}),
            execution_timeout_seconds=manifest["spec"].get("executionTimeout", 300),
        )
