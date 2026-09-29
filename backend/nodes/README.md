# SDK workflow node containers

Five independent images implement the existing HTTP, agent, script, AAP job and
AAP workflow nodes. The temporary adapter in `syntara.workflows.node_containers`
creates a fresh pod through the configured OpenShift integration for each call.
The execution-plane team can replace that adapter without changing these images.

## Build and test

From the repository root:

```bash
make install
make -C backend/nodes install
make test-nodes
make node-images REGISTRY=quay.io/your-organization TAG=migration-test
# Build only one image:
make node-image NODE=http-request REGISTRY=quay.io/your-organization TAG=migration-test
# Docker is also supported:
make node-images CONTAINER_ENGINE=docker
```

The build context is `backend/nodes`. Each folder contains its own `Containerfile`.
`uv.lock` locks the shared runtime and every node; the SDK Python package is pinned
to `b1398927636a1442e59afac6627fcebd6f2a4647`. Only the selected node and its dependencies
are installed in each image. The script image contains both Python and Bash.
SDK OCI metadata commands do not build these executable images.

Publish explicitly after local verification:

```bash
podman login quay.io
make push-node-images REGISTRY=quay.io/your-organization TAG=migration-test
```

Record each pushed digest and use `repository@sha256:...` in deployment settings.
The manually triggered **Build SDK node images** workflow produces five OCI image
archives; it does not publish to a registry or deploy. Its SDK tests also run on
relevant pull requests. Promotion into `devel` remains part of the branch release.

| Workflow type | Folder/image suffix |
| --- | --- |
| `http_request` | `http-request` |
| `agentic` | `agent` |
| `script` | `script` |
| `aap_job_template` | `aap-job` |
| `aap_workflow_job_template` | `aap-workflow` |

### Build in OpenShift

Binary builds avoid cross-compiling when the workstation and cluster use different
architectures. Run from the repository root after logging in with `oc`:

```bash
NAMESPACE=ep-dev-workers
TAG=migration-test
tar --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
  --exclude='.mypy_cache' --exclude='.ruff_cache' --exclude='tests' \
  -czf /tmp/syntara-node-context.tar.gz -C backend/nodes .

for NODE in http-request agent script aap-job aap-workflow; do
  NAME=syntara-node-$NODE
  oc new-build --binary --strategy=docker --name="$NAME" \
    --to="$NAME:$TAG" -n "$NAMESPACE"
  oc patch buildconfig "$NAME" -n "$NAMESPACE" --type=merge \
    -p "{\"spec\":{\"strategy\":{\"dockerStrategy\":{\"dockerfilePath\":\"$NODE/Containerfile\"}}}}"
  oc start-build "$NAME" --from-archive=/tmp/syntara-node-context.tar.gz \
    --follow --wait -n "$NAMESPACE"
  oc get imagestreamtag "$NAME:$TAG" -n "$NAMESPACE" \
    -o jsonpath='{.image.dockerImageReference}{"\n"}'
done
```

The `new-build` step is needed once per name. Reuse its BuildConfig with
`start-build` for later source changes. The internal registry references returned
above can be used directly by pods in that namespace. This requires build and
image-stream permissions in addition to the dispatcher's runtime Role.

## gRPC protocol, version 1

Every image starts a gRPC server on TCP port **50051**. The protobuf service is
[`syntara.node.v1.NodeService`](_protocol/src/syntara_node_protocol/node.proto):

| RPC | Behavior |
| --- | --- |
| `Health` | Reports protocol version and readiness before admission |
| `Execute` | Accepts one request; streams progress followed by one SDK result |
| `Cancel` | Cancels the active invocation while keeping its result stream open |

The request contains an invocation ID, operation, typed limits, and separate fields
for workflow inputs, resolved credentials, context and settings. Dynamic fields use
JSON **bytes inside protobuf messages** so large integers and nulls retain their
original values. There is no JSON Lines transport on the container's stdin/stdout.
Messages are limited to 2 MiB. The server validates inputs using the SDK node's
models. Credentials never appear in RPC metadata or Kubernetes pod specifications.

Each pod accepts **one invocation**. A second `Execute` is rejected even if the
first client lost its connection. The server exits after the first invocation's
stream finishes, and the workflow adapter deletes the pod. Node failures are typed
terminal results; gRPC status codes describe transport or request failures. Logs
use stderr. Script stdout/stderr remain fields of the result.

`Execute` streams sanitized progress, including AAP audit events, followed by the
existing SDK `StandardOutputWrapper` fields and retry classification. The workflow
adapter preserves the existing output mappings and Temporal error behavior. It
never retries `Execute` after uncertain submission. Cancellation, a disconnected
client, RPC deadlines, and SIGTERM request cooperative cleanup; scripts terminate
their process groups and AAP polling attempts to cancel its remote job.

Agent `Execute` returns its existing invocation acknowledgement; AO's callback still
completes the Temporal activity. `Execute` with operation `CANCEL_EXTERNAL` asks the
agent adapter to cancel earlier AO invocations. The `Cancel` RPC instead stops the
currently running container invocation.

### Network connection and TLS

The temporary adapter uses Kubernetes **pods/portforward** to reach the gRPC port
through the authenticated, TLS-protected cluster API. The Python client forwards
HTTP/2 bytes into a real gRPC channel; no request or response data travels through
`pods/attach`, stdin or stdout. This works from the local Syntara worker and does not
require a Service, Route, public endpoint, or routable pod IP.

The default listener is `127.0.0.1:50051`, which port-forwarding can reach. For a
future execution plane with direct pod-network access, configure a non-loopback
listener and mutual TLS:

```dotenv
SYNTARA_NODE_GRPC_ADDRESS=0.0.0.0:50051
SYNTARA_NODE_GRPC_TLS_CERT=/run/grpc-tls/tls.crt
SYNTARA_NODE_GRPC_TLS_KEY=/run/grpc-tls/tls.key
SYNTARA_NODE_GRPC_TLS_CA=/run/grpc-tls/ca.pem
```

Mount the server certificate/key and trusted client CA. The client must trust the
server certificate and present its own accepted client certificate. Non-loopback
listeners reject startup without TLS. These certificates are separate from the
agent adapter's outbound AO TLS identity.

### Manual client and protobuf generation

For a pod already running in the namespace, start a tunnel in one terminal:

```bash
oc port-forward pod/POD_NAME 50051:50051 -n ep-dev-workers
```

Then call it from the repository root:

```bash
uv run --project backend --no-sync python -m syntara_node_protocol \
  --address 127.0.0.1:50051 --file backend/nodes/script/example.json
```

For a direct TLS connection, also pass `--ca`, `--cert` and `--key`. The CLI prints
progress and results for inspection; its output is not the server's wire protocol.
Keep real credentials in a protected local invocation file. The five `example.json`
files contain illustrative inputs; replace endpoint and reference placeholders.

The lightweight `_protocol` package is shared by the backend and all five images.
Generated Python clients, servers and type stubs are checked in. Regenerate them
with `make -C backend/nodes proto` after editing `node.proto`; the compiler and
stub-generator dependencies are locked in the node workspace.

## Configure the temporary OpenShift adapter

1. Create/choose an enabled, **project-scoped OpenShift integration** with an HTTPS API URL, namespace,
   optional CA and an HTTP Bearer management credential. Assign the integration to
   each workflow project. The integration owns the infrastructure management credential.
   Apply the integration URL allowlist required by your existing deployment.
2. Give that credential namespace-scoped access to `get/create/delete` pods and
   `get/create` `pods/portforward`. A sample Role is in `openshift-role.yaml`; bind it to
   the identity represented by the integration credential. No cluster-admin access
   is required. Configure image pull access on the namespace's default service account.
3. Configure the API and Temporal worker consistently, then start a new workflow:

```dotenv
APP_NODE_CONTAINER_INTEGRATION_ID=<integration-uuid>
APP_NODE_CONTAINER_ENABLED_TYPES=["http_request","agentic","script","aap_job_template","aap_workflow_job_template"]
APP_NODE_CONTAINER_IMAGES={"http_request":"quay.io/ORG/syntara-node-http-request@sha256:DIGEST","agentic":"quay.io/ORG/syntara-node-agent@sha256:DIGEST","script":"quay.io/ORG/syntara-node-script@sha256:DIGEST","aap_job_template":"quay.io/ORG/syntara-node-aap-job@sha256:DIGEST","aap_workflow_job_template":"quay.io/ORG/syntara-node-aap-workflow@sha256:DIGEST"}
APP_NODE_CONTAINER_STARTUP_SECONDS=120
APP_NODE_CONTAINER_GRACE_SECONDS=30
APP_SCRIPT_NODES_ENABLED=true
APP_NODE_CONTAINER_AGENT_BASE_URL=https://YOUR-REACHABLE-AGENT-ORCHESTRATOR/api/v1
APP_NODE_CONTAINER_AGENT_TLS_SECRET=agent-node-service-tls
```

The node type keys are the existing workflow types. Images are deployment settings;
users do not choose arbitrary images in workflow definitions. Route settings are
recorded at workflow start, preserving Temporal replay. Disabling a type affects new
workflow executions and restores its original activity path. Existing script feature
gating remains active.

When upgrading the earlier stdin-based containers, finish their active workflows
first, then update the API/worker code and all configured image digests together.
The gRPC adapter requires the new server images; old image digests cannot be reused.

For the agent image, provision `ca.pem`, `tls.crt` and `tls.key` in the configured
Secret in the execution namespace. Use an identity accepted by AO's existing service
authentication and configure its server certificate for the reachable hostname.
Only agent pods mount this Secret. `APP_S2S_TLS_ENABLED=false` supports local test
servers; remote deployments should use the existing authenticated TLS configuration.
Agent callback URLs must remain reachable from Agent Orchestrator.

All pods have resource limits, read-only roots, memory-backed temporary storage,
non-root execution, dropped capabilities and no automatically mounted Kubernetes
service-account token. OpenShift assigns their UID. Workloads never receive the
OpenShift management token, database credentials or Temporal credentials.

## Compatibility and handoff

The SDK models and executor logic were extracted from the ANSTRAT-1803 baseline.
Legacy paths remain available during migration; schema parity tests flag drift.
HTTP retains its current SSRF allowlist, metadata protection, authentication and
retry classification. As before, DNS pre-validation must be backed by deployment
egress controls. Scripts retain the EP's current output **field selection** behavior;
other synchronous nodes use workflow expression mappings in Syntara. Agent outputs
still come from the existing callback. Deferred AAP fields such as credential-name
and execution-environment resolution remain deferred.

The direct adapter owns only pod creation, readiness, gRPC calls, event forwarding and
cleanup. It does not implement scheduling, pools, target ranking or a durable work
service. Replacing `dispatch`/`run_pod` with the team's execution-plane path is the
handoff point. Preserve protocol v1, lifecycle events and the compatibility mapping.

A lost stream after submission is non-retryable because the external side effect
may have occurred. Inspect the recorded AAP job or agent invocation before rerunning.
Pods have an active deadline and are deleted in the adapter's cleanup path. If the
worker crashes or the cluster API remains unavailable, a terminated pod may remain;
operators can identify it by `syntara.io/temporary-executor=true` and remove it after
checking the associated execution. This adapter does not provide crash recovery or
exactly-once external side effects.

## Remote acceptance checks

After publishing and configuring the five digests, execute existing workflows that:

- Make an authenticated HTTP request and use its body in a downstream expression.
- Run both Python and Bash, then exercise nonzero exit, truncation and timeout.
- Launch an AAP job and workflow, verify artifacts and audit events, and cancel each.
- Dispatch an agent with model/tool/file metadata, receive its callback, and cancel it.
- Exercise a missing image, failed pod startup and a dropped gRPC connection.

Check compatible workflow results, visible partial IDs, no leaked credentials,
absence of completed pods, and the disabled-route fallback. Record cluster,
namespace, image digests and workflow execution IDs as release evidence.

For a local smoke test of **every built image** against a disposable HTTP fixture:

```bash
make smoke-node-images CONTAINER_ENGINE=docker
```

This creates its own temporary container/network and cleans them up. Every node runs
with an arbitrary UID, read-only root filesystem, dropped capabilities and a tmpfs.
It checks real container packaging and the SDK result protocol; it does not replace
the remote workflow-level acceptance checks above.

The [local OpenShift runbook](LOCAL-OPENSHIFT.md) records the development instance,
verification results and restart commands. A tested HTTP → Python → Bash workflow
is in [`examples/remote-http-python-bash.yaml`](examples/remote-http-python-bash.yaml).
