# Node-SDK → AO sub-workflow bridge (POC)

Isolated Phase 3 experiment for [ANSTRAT-2347](https://redhat.atlassian.net/browse/ANSTRAT-2347).

Maps node-sdk `Control` / `Trigger` documents onto AO
`SubWorkflowExecutorParameters` and an AO-shaped output envelope. It does
**not** register activities, start Temporal children, or change production
dispatch.

## Run

From `backend/`:

```sh
PYTHONPATH=src:experiments .venv/bin/python -m pytest experiments/node_sdk_subworkflow_bridge -q
```

## What it proves

- A Control with `workflow-invocation` can feed AO parameters **only when**
  the caller injects `workflow_id` (UUID) and `trigger_node_id`.
- A Trigger on `subworkflow.v1` can supply AO `parameters.input_schema` from
  `spec.configuration`.
- An SDK business result can be wrapped into `SubWorkflowOutputResult` under
  step-keyed `outputs`.

## What it does not prove

- Platform-runner `syntara.workflow.invoke@1.0.0` dispatch
- Used-by / version resolution / authz
- Catalog install of Control via `InstalledIdentity`

Umbrella runbook: see `POC.md` in the node-sdk
`examples/subworkflow-composition/` workspace (sibling checkout) or
`arch-docs/anstrat-2347-node-sdk-poc.md`.
