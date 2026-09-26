"""Contract compatibility test: EP ScriptOutput vs Syntara ScriptOutput.

EP's execution_plane.models.script_output.ScriptOutput is the source of truth
for the script activity result shape. Syntara's copy in workflow_definition.py
must stay field-for-field identical so that the Temporal activity result written
by the EP worker deserialises correctly into the Syntara model.

This test will be deleted when AAP-93073 is complete — at that point Syntara's
ScriptOutput will be generated from the EP OpenAPI spec and manual sync is no
longer required.

Tracking: https://redhat.atlassian.net/browse/AAP-93073
"""

import typing

import pytest
from execution_plane.models.script_output import ScriptOutput as EPScriptOutput

from syntara.workflows.workflow_engine.models.workflow_definition import ScriptOutput as SyntaraScriptOutput


def _ep_fields() -> dict[str, type]:
    return typing.get_type_hints(EPScriptOutput)


def _syntara_fields() -> dict[str, type | None]:
    return {name: info.annotation for name, info in SyntaraScriptOutput.model_fields.items()}


class TestScriptOutputContract:
    """EP ScriptOutput and Syntara ScriptOutput must have identical field names and types."""

    def test_field_names_match(self) -> None:
        ep = set(_ep_fields())
        syntara = set(_syntara_fields())
        assert ep == syntara, (
            f"ScriptOutput field mismatch between EP and Syntara.\n"
            f"EP only: {ep - syntara}\n"
            f"Syntara only: {syntara - ep}\n"
            f"See AAP-93073 to resolve this permanently."
        )

    @pytest.mark.parametrize("field_name", list(_ep_fields()))
    def test_field_types_match(self, field_name: str) -> None:
        ep_type = _ep_fields()[field_name]
        syntara_type = _syntara_fields()[field_name]
        assert ep_type == syntara_type, (
            f"Field '{field_name}' type mismatch: EP={ep_type!r}, Syntara={syntara_type!r}.\n"
            f"See AAP-93073 to resolve this permanently."
        )
