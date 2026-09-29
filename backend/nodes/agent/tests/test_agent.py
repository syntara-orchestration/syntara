"""Agent dispatch acknowledges the invocation and leaves completion to AO."""

import httpx
import respx
from syntara_node_agent import Node
from syntara_node_runtime.runtime import Invocation, execute

ID = "d278f948-d329-438e-b0fd-2d993a7d9c0f"
CONTEXT = {
    "agent_base_url": "https://agent.example/api/v1",
    "agent_tls_enabled": False,
    "project_id": ID,
    "created_by_user_id": ID,
    "agent_metadata": {"callback_url": "https://callback.example", "execution_id": ID},
}


@respx.mock
def test_dispatch_payload():
    route = respx.post("https://agent.example/api/v1/invocations").mock(
        return_value=httpx.Response(201, json={"id": ID})
    )
    events = []
    frame = execute(Node(), Invocation(inputs={"prompt": "hello"}, workflow_context=CONTEXT), events.append)
    import json

    payload = json.loads(route.calls[0].request.content)
    assert payload["projectId"] == ID
    assert payload["contextData"]["callback_url"] == "https://callback.example"
    assert frame["result"]["Result"]["invocation_id"] == ID
    assert events[0]["kind"] == "progress"


@respx.mock
def test_cancel():
    respx.post(f"https://agent.example/api/v1/invocations/{ID}/cancel").mock(return_value=httpx.Response(202))
    frame = execute(
        Node(),
        Invocation(operation="cancel", inputs={"invocation_id": ID}, workflow_context=CONTEXT),
        lambda _frame: None,
    )
    assert frame["result"]["Result"]["cancelled"] is True


@respx.mock
def test_uncertain_post_not_retried():
    route = respx.post("https://agent.example/api/v1/invocations").mock(side_effect=httpx.ReadTimeout("secret error"))
    frame = execute(Node(), Invocation(inputs={"prompt": "hello"}, workflow_context=CONTEXT), lambda _frame: None)
    assert route.call_count == 1
    assert frame["error"]["retryable"] is False
    assert "secret error" not in str(frame)
