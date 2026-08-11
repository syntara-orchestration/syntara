"""Tests for workflow definition schema validation gaps (AAP-75721).

Each test sends a payload that violates the JSON schema at
``src/syntara/schemas/workflows/v2/workflow_definition.schema.json``
and asserts the server returns 422.
"""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.helpers.workflow import create_minimal_workflow_definition


def _base_payload(name: str = "schema-gap-test") -> dict[str, Any]:
    """Return a valid workflow creation payload as a starting point."""
    return {
        "name": name,
        "workflow_definition": create_minimal_workflow_definition(name=name),
    }


@pytest.mark.asyncio
async def test_fabricated_node_type(jwt_client: AsyncClient) -> None:
    """Fabricated node type violates the node oneOf constraint."""
    payload = _base_payload("fabricated-node-type")
    payload["workflow_definition"]["nodes"] = [
        {"id": "n1", "type": "totally_fake_type", "parameters": {}},
    ]

    response = await jwt_client.post("/api/v1/workflows", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_node_missing_config(jwt_client: AsyncClient) -> None:
    """Node without config violates node_base required fields."""
    payload = _base_payload("node-missing-config")
    payload["workflow_definition"]["nodes"] = [
        {"id": "n1", "type": "script"},
    ]

    response = await jwt_client.post("/api/v1/workflows", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_node_missing_id(jwt_client: AsyncClient) -> None:
    """Node without id violates node_base required fields."""
    payload = _base_payload("node-missing-id")
    payload["workflow_definition"]["nodes"] = [
        {"type": "script", "parameters": {"language": "python", "code": "x"}},
    ]

    response = await jwt_client.post("/api/v1/workflows", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_node_id_pattern(jwt_client: AsyncClient) -> None:
    """Node ID starting with digit violates pattern ^[a-zA-Z_][a-zA-Z0-9_]*$."""
    payload = _base_payload("invalid-node-id")
    payload["workflow_definition"]["nodes"] = [
        {"id": "123-starts-with-digit!", "type": "script", "parameters": {"language": "python", "code": "x"}},
    ]

    response = await jwt_client.post("/api/v1/workflows", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_extra_top_level_properties(jwt_client: AsyncClient) -> None:
    """Extra top-level fields violate additionalProperties: false."""
    payload = _base_payload("extra-top-level")
    payload["workflow_definition"]["metadata"] = {"author": "test"}
    payload["workflow_definition"]["priority"] = "high"

    response = await jwt_client.post("/api/v1/workflows", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trigger_without_id(jwt_client: AsyncClient) -> None:
    """Trigger node without id violates node_base required fields."""
    payload = _base_payload("trigger-no-id")
    payload["workflow_definition"]["triggers"] = [
        {"type": "manual_trigger", "parameters": {}},
    ]

    response = await jwt_client.post("/api/v1/workflows", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_extra_edge_properties(jwt_client: AsyncClient) -> None:
    """Extra edge fields violate edge additionalProperties: false."""
    payload = _base_payload("extra-edge-props")
    payload["workflow_definition"]["edges"] = [
        {
            "from": "trigger_manual",
            "to": "test_activity",
            "color": "red",
            "weight": 5,
        },
    ]

    response = await jwt_client.post("/api/v1/workflows", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_empty_triggers_array(jwt_client: AsyncClient) -> None:
    """Empty triggers array violates minItems: 1."""
    payload = _base_payload("empty-triggers")
    payload["workflow_definition"]["triggers"] = []

    response = await jwt_client.post("/api/v1/workflows", json=payload)

    assert response.status_code == 422
