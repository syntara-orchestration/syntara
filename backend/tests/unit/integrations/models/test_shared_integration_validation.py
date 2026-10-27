"""Public v1 and internal creation models enforce the same discovery rules."""

import pytest
from pydantic import ValidationError

from syntara.integrations.models.integration import IntegrationCreate as InternalCreate
from syntara.integrations.models.legacy_integration import IntegrationCreate as PublicCreate


@pytest.mark.parametrize("model", [InternalCreate, PublicCreate])
@pytest.mark.parametrize(
    ("integration_type", "configuration_type", "selection", "error"),
    [
        ("llm_provider", "mcp_server", {}, "does not match"),
        (
            "llm_provider",
            "llm_provider",
            {"discovered_tools": [{"name": "tool"}]},
            "discovered_tools is only supported for mcp_server",
        ),
        (
            "mcp_server",
            "mcp_server",
            {"discovered_tools": [{"name": "tool"}, {"name": "tool"}]},
            "duplicate tool names",
        ),
        (
            "mcp_server",
            "mcp_server",
            {"discovered_models": [{"model_id": "model", "name": "Model"}]},
            "discovered_models is only supported for llm_provider",
        ),
        (
            "llm_provider",
            "llm_provider",
            {"discovered_models": [{"model_id": "model", "name": "A"}, {"model_id": "model", "name": "B"}]},
            "duplicate model IDs",
        ),
        (
            "llm_provider",
            "llm_provider",
            {
                "discovered_models": [
                    {"model_id": "a", "name": "A", "is_default": True},
                    {"model_id": "b", "name": "B", "is_default": True},
                ]
            },
            "multiple default models",
        ),
    ],
)
def test_shared_discovery_rules(
    model: type[InternalCreate] | type[PublicCreate],
    integration_type: str,
    configuration_type: str,
    selection: dict[str, object],
    error: str,
) -> None:
    configuration = (
        {"integration_type": "mcp_server", "base_url": "https://example.com"}
        if configuration_type == "mcp_server"
        else {"integration_type": "llm_provider", "provider_hint": "openai"}
    )
    with pytest.raises(ValidationError, match=error):
        model.model_validate(
            {"name": "Integration", "integration_type": integration_type, "configuration": configuration, **selection}
        )
