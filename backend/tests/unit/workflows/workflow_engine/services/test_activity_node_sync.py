"""Tests for loop-body discovery used by activity synchronization."""

from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_node_sync import ActivityNodeSyncMixin


def test_nested_loop_complete_edge_remains_in_outer_body() -> None:
    definition = {
        "triggers": [],
        "nodes": [
            {"id": "outer", "type": NodeType.LOOP},
            {"id": "inner", "type": NodeType.LOOP},
            {"id": "inner-body", "type": "script"},
            {"id": "tail", "type": "script"},
        ],
        "edges": [
            {"from": "outer", "from_port": "iterate", "to": "inner"},
            {"from": "inner", "from_port": "iterate", "to": "inner-body"},
            {"from": "inner-body", "to": "inner"},
            {"from": "inner", "from_port": "complete", "to": "tail"},
            {"from": "tail", "to": "outer"},
        ],
    }

    assert ActivityNodeSyncMixin._extract_loop_body_activity_ids(definition) == {"inner-body", "tail"}
