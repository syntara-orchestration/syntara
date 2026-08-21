"""Unit tests for the llm_model_id E2E fixture's stale-integration cleanup."""

from unittest.mock import MagicMock
from uuid import UUID, uuid4

from orchestrator_test_sdk.e2e.fixtures import llm_model_id as _llm_model_id_fixture

# pytest blocks direct calls to fixture-decorated functions; unwrap to
# get the raw generator for unit testing.
_llm_model_id = getattr(_llm_model_id_fixture, "__wrapped__")  # noqa: B009


def _mock_integration(*, name: str, integration_id: UUID | None = None) -> MagicMock:
    integration = MagicMock()
    integration.name = name
    integration.id = integration_id or uuid4()
    return integration


class _FakeResponse:
    """Minimal stand-in for the API client response wrapper.

    MagicMock reserves `assert_*` names for its own assertion helpers,
    so we use a plain object instead.
    """

    def __init__(self, value: object) -> None:
        self._value = value

    def assert_and_get(self) -> object:
        return self._value


def _mock_nexus_api(*, existing_integrations: list[MagicMock] | None = None) -> MagicMock:
    nexus_api = MagicMock()

    list_result = MagicMock()
    list_result.resources = existing_integrations or []
    nexus_api.integrations.list.return_value = _FakeResponse(list_result)

    created = MagicMock()
    created.id = uuid4()
    nexus_api.integrations.create.return_value = _FakeResponse(created)

    model = MagicMock()
    model.id = uuid4()
    models_result = MagicMock()
    models_result.resources = [model]
    nexus_api.integrations.list_models.return_value = _FakeResponse(models_result)

    return nexus_api


class TestLlmModelIdFixtureStaleCleanup:
    """Verify llm_model_id deletes stale integrations before creating."""

    def test_deletes_stale_integration_before_create(self) -> None:
        stale_id = uuid4()
        stale = _mock_integration(name="e2e-llm-provider-master", integration_id=stale_id)
        nexus_api = _mock_nexus_api(existing_integrations=[stale])

        gen = _llm_model_id(nexus_api, str(uuid4()), "test-model", "master")
        next(gen)

        nexus_api.integrations.delete.assert_called_once_with(integration_id=stale_id)
        nexus_api.integrations.create.assert_called_once()

    def test_no_delete_when_no_stale_integration(self) -> None:
        nexus_api = _mock_nexus_api(existing_integrations=[])

        gen = _llm_model_id(nexus_api, str(uuid4()), "test-model", "master")
        next(gen)

        nexus_api.integrations.delete.assert_not_called()
        nexus_api.integrations.create.assert_called_once()

    def test_ignores_integrations_with_different_names(self) -> None:
        other = _mock_integration(name="e2e-llm-provider-gw0")
        nexus_api = _mock_nexus_api(existing_integrations=[other])

        gen = _llm_model_id(nexus_api, str(uuid4()), "test-model", "master")
        next(gen)

        nexus_api.integrations.delete.assert_not_called()

    def test_proceeds_if_stale_delete_fails(self) -> None:
        stale = _mock_integration(name="e2e-llm-provider-master")
        nexus_api = _mock_nexus_api(existing_integrations=[stale])
        nexus_api.integrations.delete.side_effect = RuntimeError("delete failed")

        gen = _llm_model_id(nexus_api, str(uuid4()), "test-model", "master")
        next(gen)

        nexus_api.integrations.delete.assert_called_once()
        nexus_api.integrations.create.assert_called_once()
