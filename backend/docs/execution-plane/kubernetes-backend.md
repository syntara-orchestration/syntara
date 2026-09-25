# Execution Plane: Kubernetes Backend Integration

The `vanilla_k8s` backend implements the cold-start execution model. It extends
the existing `ExecutionTarget` and `WorkItem` lifecycle rather than introducing
parallel cluster-registration or execution tables.

## Pod lifecycle

1. The worker claims the oldest pending `WorkItem` with `FOR UPDATE SKIP LOCKED`.
2. `target_selector` labels are matched against enabled, active
   `ExecutionTarget` records.
3. The item is bound to the target and moved to `dispatched`.
4. A pod named `ep-<work-item-id>` is created in the target namespace.
5. Once running, the configured command is opened with `pods/exec`. The task's
   `input` object is written as one JSONL record and one JSON object is read.
6. The pod is deleted on success, failure, cancellation, or timeout.
7. The terminal result is committed before the optional Temporal callback.

The container's original process must remain running while the exec session is
created. Images intended for this backend should keep stdin open and expose a
one-shot command such as `python -m syntara.http_executor` or
`/usr/local/bin/script-executor --once`.

## Security defaults

Worker pods run without an API token, privilege escalation, Linux capabilities,
or a writable root filesystem. They request 25 millicores and 64 MiB and are
limited to one CPU and 512 MiB. Only `/tmp` is writable through a bounded
`emptyDir`.

The external `execution-plane-executor` ServiceAccount is allowed only to
create, inspect, exec into, obtain logs for, and delete pods in
`ep-dev-workers`. Its short-lived token is stored below `backend/.secrets/`,
mounted into the EP container, and referenced from the database by path. Token
values are never stored in Git or PostgreSQL.

## Work-item payload

```json
{
  "target_selector": {
    "environment": "development",
    "execution-mode": "cold-start",
    "platform": "openshift"
  },
  "task_definition": {
    "image": "quay.io/ahetheri/http-executor:amd64",
    "pod_command": ["/bin/sh", "-c", "sleep infinity"],
    "command": ["python", "-m", "syntara.http_executor"],
    "input": {
      "url": "https://api.github.com",
      "method": "GET"
    },
    "timeout_seconds": 120,
    "image_pull_policy": "Always"
  }
}
```

The dispatcher treats `input` and the worker response as opaque JSON. A
successful response is persisted in a stable envelope containing `request_id`,
`status`, `result`, `worker_pod`, and `worker_namespace`.

`pod_command` is optional for images whose entrypoint stays alive without an
attached stdin stream. The current HTTP image exits when it receives EOF, so
the pod uses a sleep command while Kubernetes exec runs the actual executor.

## Failure handling

- Target lookup or validation failures transition the item to `failed`.
- Image-pull and pod terminal failures are reported before exec.
- Exec output is capped at 2 MiB and must contain a JSON object on one line.
- Pod deletion is best-effort and logged; namespace TTL/reaper policy can be
  added as a second safety net for process or host failure.
- `result` is committed before Temporal completion. Terminal items with a null
  `signaled_at` are replayed at worker startup, which is the branch's completion
  outbox mechanism.
