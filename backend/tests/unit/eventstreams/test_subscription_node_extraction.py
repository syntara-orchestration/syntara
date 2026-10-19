"""Subscribe trigger node extraction fails closed on duplicate node ids."""

from typing import Any

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.eventstreams.services.subscription_service import EventSubscriptionService


def _trigger(node_id: str, topic: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "event_subscribe_trigger",
        "parameters": {"transport": "kafka", "topic": topic},
    }


def test_extracts_each_distinct_subscribe_node() -> None:
    definition = {"triggers": [_trigger("a", "t-a"), _trigger("b", "t-b"), {"id": "m", "type": "manual_trigger"}]}

    nodes = EventSubscriptionService._extract_event_subscribe_nodes(definition)

    assert set(nodes) == {"a", "b"}
    assert nodes["a"]["topic"] == "t-a"


def test_skips_triggers_with_missing_id() -> None:
    definition = {"triggers": [{"type": "event_subscribe_trigger", "parameters": {"topic": "t"}}]}

    assert EventSubscriptionService._extract_event_subscribe_nodes(definition) == {}


def test_duplicate_subscribe_node_id_fails_closed() -> None:
    definition = {"triggers": [_trigger("dup", "t-a"), _trigger("dup", "t-b")]}

    with pytest.raises(SafeValueError, match="Duplicate Event Subscribe trigger node id"):
        EventSubscriptionService._extract_event_subscribe_nodes(definition)
