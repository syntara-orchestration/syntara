# Containerized Agent Runtime

The container backend is an opt-in implementation of the existing workflow
agent invocation. AO waits for file conversions, prepares the invocation
context, discovers the selected MCP tools, resolves the model configuration,
and sends the prepared prompt and tool schemas to one EP workload. The workload
keeps the decision loop in its container and requests each model turn or MCP
tool call from AO over the SDK's bidirectional Execute stream. The container
does not receive database, provider, or integration credentials and does not
connect directly to AO databases, model providers, or MCP servers.

The AO command handler checks the active agent invocation and its deterministic
EP work item before resolving either operation. It loads the configured model
and AO-discovered tools from the invocation context; it does not accept an
endpoint URL or tool definition supplied by the container as authority. EP
grants only `agent.model.turn` and `agent.mcp.call` to the Agent Runtime work
item. Other workload types receive no host operations.

AO persists the workload's final answer, tool trace, and provider token usage
through the existing invocation lifecycle, then sends the existing Temporal
success or failure callback. EP's generic completion callback acknowledges
Agent Runtime work without completing the workflow activity, avoiding a race
with that invocation finalization path. A timeout or an uncertain callback
fails the invocation; the first iteration does not resume an agent loop.

## Enabling the backend

The backend is disabled by default. Before enabling it, publish the updated
`execution-plane-client` contract containing the `agent.operation` command and
host-operation grant fields, then install that release in AO. The EP worker
and Agent Runtime image also require `syntara-plugin-contracts` 0.1.0a7, which
contains the SDK callback protocol. Build and publish the `agent-runtime`
Action image from the step-types repository. Configure AO:

```text
APP_AGENT_RUNTIME_ENABLED=true
APP_AGENT_RUNTIME_IMAGE=<customer-registry>/agent-runtime@sha256:<digest>
```

The seeder registers the image under the `agent-runtime` Action and the
`syntara.agent-runtime.agent-runtime` step identity. The customer deployment
must configure the Execution Plane target and its egress policy. This workload
does not need direct network access: AO provider and MCP calls travel over the
host callback stream. Keep workload egress restricted to the cluster's normal
DNS allowance for this Action.

If AO starts with Agent Runtime enabled but without a client contract that
supports `agent.operation`, startup fails with a configuration error. This is
intentional; the workload must not start without an installed callback handler.
