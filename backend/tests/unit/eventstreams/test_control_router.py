"""Operational routes reuse workflow permissions and reject configuration injection."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from syntara.eventstreams.models.controls import SubscriptionControlResponse
from syntara.eventstreams.router import _recover, _update, get_control_service, router


@pytest.fixture
def control_client():
    service = AsyncMock()
    response = SubscriptionControlResponse(
        subscription_id=uuid4(), source_id=uuid4(), configuration_revision=2, source_generation=1, convergence="pending"
    )
    service.action.return_value = service.recover.return_value = service.retire.return_value = response
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_control_service] = lambda: service
    app.dependency_overrides[_update] = lambda: None
    app.dependency_overrides[_recover] = lambda: None
    return TestClient(app), service


@pytest.mark.parametrize("action", ["pause", "resume", "retry", "recover", "retire"])
def test_controls_dispatch_strict_revision_checked_requests(control_client, action):
    client, service = control_client
    workflow, subscription = uuid4(), uuid4()
    body = {"configuration_revision": 1, "source_generation": 1}
    if action in {"recover", "retire"}:
        body["reason"] = "operator_correction"
    if action == "recover":
        body.update(partition=0, policy="current_end", expected_recovery_revision=0)
    response = client.post(f"/workflows/{workflow}/event_subscriptions/{subscription}/{action}", json=body)
    assert response.status_code == (202 if action == "recover" else 200)
    target = service.action if action in {"pause", "resume", "retry"} else getattr(service, action)
    assert target.call_args.args[:2] == (workflow, subscription)
    assert target.call_args.args[2].configuration_revision == 1
    if action in {"pause", "resume", "retry"}:
        assert target.call_args.args[3] == action


@pytest.mark.parametrize(
    "field",
    [
        "password",
        "group_id",
        "offset",
        "execution_id",
        "input_data",
        "selected_account_id",
        "assignment_epoch",
        "cache_epoch",
        "cache_coordination",
        "allow_unscheduled_disposition",
    ],
)
@pytest.mark.parametrize("action", ["pause", "resume", "retry", "recover", "retire"])
def test_control_bodies_cannot_inject_runtime_configuration(control_client, field, action):
    client, service = control_client
    response = client.post(
        f"/workflows/{uuid4()}/event_subscriptions/{uuid4()}/{action}",
        json={
            "configuration_revision": 1,
            "source_generation": 1,
            field: "injected",
            **({"reason": "operator_correction"} if action in {"recover", "retire"} else {}),
            **(
                {"partition": 0, "policy": "current_end", "expected_recovery_revision": 0}
                if action == "recover"
                else {}
            ),
        },
    )
    assert response.status_code == 422
    service.action.assert_not_called()
    service.recover.assert_not_called()
    service.retire.assert_not_called()


def test_workflow_authority_reuse_and_exceptional_project_scope():
    assert (_update.resource_type, _update.action, _update.resource_id_param) == ("workflow", "update", "workflow_id")
    assert (_recover.resource_type, _recover.action, _recover.resource_id_param) == (
        "event_subscription",
        "recover",
        "workflow_id",
    )
    assert hasattr(_recover.resource_model, "project_id")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("configuration_revision", 0),
        ("configuration_revision", True),
        ("configuration_revision", "1"),
        ("source_generation", -1),
        ("source_generation", 2**31),
        ("configuration_revision", 2**63),
    ],
)
def test_invalid_revision_bounds_are_rejected(control_client, field, value):
    client, service = control_client
    assert (
        client.post(
            f"/workflows/{uuid4()}/event_subscriptions/{uuid4()}/pause",
            json={
                "configuration_revision": 1,
                "source_generation": 1,
                field: value,
            },
        ).status_code
        == 422
    )
    service.action.assert_not_called()
