"""Shared script execution result contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScriptOutput:
    """Result shape produced by the EP worker for a script execution.

    This is the source of truth for the script activity result contract.
    The corresponding Syntara model (ScriptOutput in workflow_definition.py)
    must stay field-for-field identical. A compatibility test in
    backend/tests/unit/workflows/activities/ep/test_script_output_contract.py
    enforces this.

    When the EP OpenAPI spec declares typed result schemas and Syntara
    generates Python contracts from them (see the tracking issue referenced
    in the compatibility test), this dataclass will be replaced by the
    generated type and the manual sync requirement goes away.
    """

    return_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    stdout_json: Any = None
