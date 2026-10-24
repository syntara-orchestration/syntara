# Backend E2E — Konflux skip patterns

Why these exist: see "Konflux CI Environment" in the root [`CLAUDE.md`](../../../CLAUDE.md). When an E2E test fails only in Konflux, apply the matching skip pattern rather than modifying the test logic.

**Graceful skip for backend connectivity failures**: When the Temporal worker can't reach an external URL, the execution completes with `status == FAILED` but the activity output contains no `status_code` (only an `error: "HTTP request failed: ReadTimeout"` key). Add a skip guard. If `error` is `"SSRF blocked: private IP range"`, that is an allowlist misconfiguration (`httpbin` missing from `workflowHttpRequestAllowedHosts`), not a connectivity skip — fix CI rather than skipping.

```python
if execution.status == ExecutionStatus.FAILED:
    output = _get_activity_output(execution, "api_call")
    if not output.get("status_code"):
        pytest.skip("Backend could not reach httpbin — network connectivity issue in this environment")
assert execution.status == ExecutionStatus.COMPLETED
```

**Graceful skip for transient 502**: Nginx briefly returns 502 when the backend restarts under load. Catch `UnexpectedResponseException` from `syntara_api_client.types` and skip on status 502:

```python
from syntara_api_client.types import UnexpectedResponseException

try:
    result = syntara_api.workflows.get(workflow_id=wf.id).assert_and_get()
except UnexpectedResponseException as exc:
    if exc.status_code == 502:
        pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
    raise
```
