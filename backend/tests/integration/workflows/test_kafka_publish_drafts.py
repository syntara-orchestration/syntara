"""Persist unfinished Publish drafts while retaining strict publish validation."""

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient

WORKFLOWS_URL = "/api/v1/workflows"


@pytest.mark.parametrize("payload_text", ["", '{"result":'])
async def test_incomplete_publish_draft_save_reopen_update_and_publish_gate(
    jwt_client: AsyncClient, test_project_id: UUID, payload_text: str
) -> None:
    definition: dict[str, Any] = {
        "schema_version": "2.0.0",
        "name": "unfinished-publish",
        "triggers": [{"id": "manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "publish",
                "type": "kafka_publish",
                "parameters": {"integration_id": "", "credential_id": "", "topic": ""},
                "metadata": {"__kafkaPublishPayloadDraft": payload_text},
            }
        ],
        "edges": [{"from": "manual", "to": "publish"}],
    }
    response = await jwt_client.post(
        WORKFLOWS_URL,
        json={
            "name": f"unfinished-publish-{test_project_id.hex[:8]}-{len(payload_text)}",
            "project_id": str(test_project_id),
            "workflow_definition": definition,
        },
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    workflow_id = saved["id"]
    assert saved["has_validation_issues"]
    assert not saved["validation_result"]["is_valid"]
    fields = {
        finding["field_path"] for finding in saved["validation_result"]["findings"] if finding["node_id"] == "publish"
    }
    assert {"parameters.integration_id", "parameters.credential_id", "parameters.topic", "parameters.payload"} <= fields

    reopened = await jwt_client.get(f"{WORKFLOWS_URL}/{workflow_id}")
    assert reopened.status_code == 200
    assert reopened.json()["version"]["workflow_definition"]["nodes"] == definition["nodes"]

    definition["nodes"][0]["metadata"]["__kafkaPublishPayloadDraft"] = '{"updated":'
    updated = await jwt_client.patch(f"{WORKFLOWS_URL}/{workflow_id}", json={"workflow_definition": definition})
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"]["workflow_definition"]["nodes"] == definition["nodes"]
    assert not updated.json()["validation_result"]["is_valid"]
    version = updated.json()["current_version"]
    published = await jwt_client.post(f"{WORKFLOWS_URL}/{workflow_id}/versions/{version}/publish", json={})
    assert published.status_code == 409, published.text
    assert not published.json()["validation_result"]["is_valid"]
    assert "updated" not in published.text
