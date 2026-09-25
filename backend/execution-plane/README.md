# Syntara Execution Plane

This package owns execution targets, queued work items, the Task Executor
worker, and swappable worker-manager backends. The OpenShift development path
uses a cold-start Kubernetes manager: one hardened pod is created per work
item, one JSON request is sent through `pods/exec`, one JSON response is read,
and the pod is deleted in a `finally` block.

See [Cold-start OpenShift development](../docs/execution-plane/cold-start-development.md)
for setup and verification instructions.
