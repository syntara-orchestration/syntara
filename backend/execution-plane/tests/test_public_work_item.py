"""Public Execution Plane responses do not reveal workflow input secrets."""

import uuid
from datetime import UTC, datetime

from execution_plane.models.work_item import WorkItem, WorkItemStatus
from execution_plane.router import _public_work_item


def test_public_work_item_redacts_http_and_script_inputs() -> None:
    item = WorkItem(
        id=uuid.uuid4(),
        work_correlation_id=uuid.uuid4(),
        status=WorkItemStatus.PENDING,
        payload={
            "execution_target_id": str(uuid.uuid4()),
            "workflow_node_type": "http_request",
            "task_definition": {"input": {"headers": {"Authorization": "Bearer private"}}},
            "input_config": {"code": "print('secret')"},
            "output_config": None,
        },
        created_at=datetime.now(UTC),
    )

    public = _public_work_item(item)

    assert public.payload == {
        "execution_target_id": item.payload["execution_target_id"],
        "workflow_node_type": "http_request",
    }
    assert "private" not in public.model_dump_json()
