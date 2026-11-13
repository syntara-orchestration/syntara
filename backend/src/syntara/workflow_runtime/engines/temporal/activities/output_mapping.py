"""Temporal adapters for shared workflow output serialization."""

from temporalio.exceptions import ApplicationError

from syntara.workflow_core.models import NodeOutput
from syntara.workflow_core.output_mapping import (
    OutputMappingError,
)
from syntara.workflow_core.output_mapping import (
    apply_output_mapping as _apply_output_mapping,
)


def apply_output_mapping(result: dict[str, object], output_config: dict[str, str] | None) -> dict[str, object]:
    """Apply output mapping and expose failures as non-retryable Temporal errors."""
    try:
        return _apply_output_mapping(result, output_config)
    except OutputMappingError as exc:
        raise ApplicationError(str(exc), type="OutputMappingError", non_retryable=True) from exc


def dump_output(output: NodeOutput, output_config: dict[str, str] | None) -> dict[str, object]:
    """Serialize a model output and translate mapping failures at the activity boundary."""
    try:
        return output.dump(output_config)
    except OutputMappingError as exc:
        raise ApplicationError(str(exc), type="OutputMappingError", non_retryable=True) from exc


__all__ = ["apply_output_mapping", "dump_output"]
