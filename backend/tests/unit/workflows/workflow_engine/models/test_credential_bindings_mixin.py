"""Tests for shared credential bindings across node parameter models."""

from collections.abc import Callable
from typing import Any

import pytest

from syntara.workflows.workflow_engine.models.workflow_definition import (
    AAPJobTemplateExecutorParameters,
    AAPWorkflowJobTemplateExecutorParameters,
    AgenticExecutorParameters,
    APIExecutorParameters,
    ApprovalNodeParameters,
    HTTPMethod,
    ScriptExecutorParameters,
    ScriptLanguage,
)


@pytest.mark.parametrize(
    ("factory", "label"),
    [
        (
            lambda: ScriptExecutorParameters(language=ScriptLanguage.PYTHON, code="pass"),
            "script",
        ),
        (lambda: APIExecutorParameters(method=HTTPMethod.GET), "http_request"),
        (lambda: AgenticExecutorParameters(prompt="test"), "agentic"),
        (ApprovalNodeParameters, "approval"),
        (lambda: AAPJobTemplateExecutorParameters(job_template_id=1), "aap_job_template"),
        (lambda: AAPWorkflowJobTemplateExecutorParameters(workflow_job_template_id=1), "aap_workflow_job_template"),
    ],
)
def test_credential_binding_field_is_available(
    factory: Callable[[], Any],
    label: str,
) -> None:
    base = factory()
    model = type(base).model_validate(
        {
            **base.model_dump(),
            "credential_bindings": [
                {
                    "credential_recipe_id": "acme.echo.api-token",
                    "credential_ref": "00000000-0000-0000-0000-000000000001",
                }
            ],
        }
    )

    assert model.credential_bindings is not None
    assert model.credential_bindings[0].credential_recipe_id == "acme.echo.api-token"
    assert str(model.credential_bindings[0].credential_ref) == "00000000-0000-0000-0000-000000000001"
