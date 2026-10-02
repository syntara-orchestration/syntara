# Execution Plane: Cold-Start Node Dispatch (MVP)

Status: **implemented** for the Vanilla Kubernetes backend under
[AAP-93615](https://redhat.atlassian.net/browse/AAP-93615).

This document records what the cold-start node dispatch MVP actually ships, and —
more importantly — the shortcuts it takes on purpose. Each shortcut below is
written to be turned directly into a followup Jira: it states the shortcut, why
it is acceptable for the MVP, and the shape of the work that removes it.

For the general worker-manager design (capacity, WorkWatcher, placement backoff)
see [worker-manager.md](worker-manager.md). For the service boundary shortcuts
(direct DB writes instead of an HTTP API) see [integration.md](integration.md).

---

## What shipped

The MVP runs one fresh Kubernetes pod per `WorkItem` and talks to it over gRPC:

- **`VanillaK8sWorkerManager`** (`worker_manager/vanilla_k8s/manager.py`) — loads
  the `ExecutionTarget` (with its secret), reads the invocation envelope + image
  from `work_item.payload`, creates a pod, streams the single result over gRPC,
  reaps the pod, and maps the result to a Temporal-compatible activity result.
  The manager is **node-type agnostic**; it never inspects the node kind.
- **Vendored node protocol + transport** (`node_protocol/`, `worker_manager/
  vanilla_k8s/transport.py`, `forward.py`) — a copy of the SDK node gRPC client,
  codec, and generated protobuf, plus the K8s pod lifecycle / port-forward
  transport. Vendored (copied), not taken as a package dependency — see shortcut
  6.
- **AO builds the envelope** — the Temporal activity
  (`ep_dispatch_activity.py`) selects the container image per node type and
  builds the full invocation envelope, then writes it into `work_items.payload`.
  The EP worker stays "dumb". This matches the shape used by the synchronous
  node-container path so one SDK image serves both routes.
- **Three-outcome dispatch** in `worker.py`:
  - success → `set_result(COMPLETED)` → Temporal `handle.complete()`
  - node ran but failed (`NodeExecutionError`) → `set_result(FAILED)` →
    Temporal `handle.fail()`
  - transport/capacity failure (`RetryableDispatchError`) → `WorkStore.requeue()`
    back to `PENDING` after a fixed backoff, no Temporal signal.

---

## MVP shortcuts and followups

### 1. Secrets at rest in `work_items.payload` (plaintext)

**Shortcut.** The invocation envelope — including node `inputs` — is persisted
in `work_items.payload` (JSONB) in plaintext. Script nodes carry no credentials,
so nothing sensitive is stored today.

**Why acceptable for MVP.** The only wired node type is `script`, whose
`credentials.resolved` is empty. The DB is already the trust boundary for the
Temporal task token stored alongside it.

**Followup shape.** Before any credential-bearing node type (`aap_*`, `agentic`)
uses this path, either (a) encrypt `work_items.payload` at rest, or (b) have the
EP worker resolve credential *references* at dispatch time so secrets never land
in the row. Option (b) is cleaner but requires EP to reach a secret service,
which reintroduces a Syntara coupling — decide alongside the service-boundary
work in [integration.md](integration.md). Until then, the AO activity must not
route credential-bearing node types through `_dispatch_to_te`.

### 2. Output mapping is field-selection only

**Shortcut.** `_map_result` supports simple field selection (`output_config`
keys picked out of the node's `Result` dict). Template-expression output mapping
(e.g. `"${result.stdout}"`) is not supported.

**Why acceptable for MVP.** This matches the existing script-node limitation;
template mapping needs `NamespaceResolver` from the syntara package, which the EP
must not import.

**Followup.** Tracked by
[AAP-93073](https://redhat.atlassian.net/browse/AAP-93073) — resolve output
mapping without importing syntara (e.g. a small shared expression evaluator, or
mapping applied AO-side after the result returns).

### 3. No cancellation

**Shortcut.** The gRPC contract has a `Cancel` RPC and `run_pod` accepts a
`cancelled` threading event, but the EP worker never sets it. A cancelled
`WorkItem` does not stop a running pod.

**Why acceptable for MVP.** Cold-start pods are short-lived and reaped on
completion; a leaked pod is bounded by the node timeout.

**Followup shape.** Wire `WorkItem` cancellation → set the `cancelled` event /
invoke `NodeService.Cancel`, and reap the pod on cancel. Needs a cancellation
signal path from AO/Temporal into the EP worker (a status column poll or a
second pg_notify channel).

### 4. Fixed backoff, no per-item hold-off

**Shortcut.** `WorkStore.requeue()` returns the item to `PENDING` and clears its
target; the poll loop sleeps `dispatch_retry_backoff_seconds` before requeuing.
There is no per-item attempt counter and no not-before timestamp, so a second
concurrent worker could immediately re-claim a just-requeued item.

**Why acceptable for MVP.** The worker claims serially and there is a single EP
worker in local/dev; the fixed sleep throttles a persistently unavailable
target well enough to avoid a hot loop.

**Followup shape.** This is the "Placement failure backoff" design already
sketched in [worker-manager.md](worker-manager.md#placement-failure-backoff):
add a `last_placement_failed_at` column (Alembic migration), make requeue a
single atomic UPDATE, and have `claim_one()` skip items inside the penalty
window. Also add an attempt counter to cap retries.

### 5. Cluster TLS/topology is global, not per-target

**Shortcut.** `node_k8s_verify_ssl` and `node_k8s_ca_certificate` are global
`EPSettings`, applied to every target. Only `namespace` is read per-target.
`_k8s_target()` in the manager is the single place that maps an `ExecutionTarget`
onto the connection dict.

**Why acceptable for MVP.** Local kind/minikube uses one self-signed API server;
a single global `verify_ssl=false` covers dev.

**Followup shape.** Move `namespace`, node selectors/tolerations, CA bundle, and
verify flag into a backend-specific metadata block on the `ExecutionTarget` with
a K8s/RHEL discriminator (Michael's in-flight refactor). When that lands, only
`_k8s_target()` changes.

### 6. Node protocol is vendored, not a dependency

**Shortcut.** `syntara_node_protocol` (gRPC client, codec, generated protobuf)
is copied into `execution_plane/node_protocol/` rather than depended on as a
package. Imports were rewritten `syntara_node_protocol` → `execution_plane.
node_protocol`; the generated `node_pb2.py` is left byte-for-byte unchanged
because its serialized `FileDescriptorProto` embeds the original module path.

**Why acceptable for MVP.** Avoids a cross-package dependency and a publish step
while the protocol is still churning, and keeps the EP importable without the
syntara tree.

**Followup shape.** When the protocol stabilizes, either publish
`syntara-node-protocol` as a real package and depend on it, or keep it vendored
and add a drift check (a test that diffs the vendored copy against source).
Decide with the SDK owners.

### 7. Serial, synchronous dispatch — no WorkWatcher

**Shortcut.** The poll loop claims and dispatches one item at a time; the pod
lifecycle runs in a worker thread via `asyncio.to_thread`, and the poll loop
awaits it before claiming the next item. There is no `WorkWatcher` and no
concurrent dispatch.

**Why acceptable for MVP.** Correct and simple; throughput is not an MVP goal.

**Followup shape.** Introduce concurrent dispatch (bounded `asyncio` tasks or the
`WorkWatcher` in [worker-manager.md](worker-manager.md)) once capacity claiming
(shortcut 4 / reconciler placement) is in place, so concurrency does not
oversubscribe a target.

### 8. Placement uses the first default target, not the reconciler

**Shortcut.** `claim_one()` assigns every claimed item to the first enabled,
active, default `ExecutionTarget`. `build_placement_resolver()` is constructed in
`run_worker` but only logged — its ranking is not yet consulted.

**Why acceptable for MVP.** Dev clusters register a single default target, so
ranking is a no-op.

**Followup shape.** Wire the `ExecutionTarget` reconciler's ranked candidate list
into claim/placement (the Work Scheduler loop in
[worker-manager.md](worker-manager.md)), replacing the hard-coded default-target
select in `claim_one()`.

### 9. Node container image is a mutable tag in a personal namespace, not a pipeline artifact

**Shortcut.** `node_container_images` (config `base.py`) now defaults to the public
pre-release node images Aaron published on quay.io
(`quay.io/ahetheri/syntara-node-script:migration-test` and the matching
`http-executor` / `syntara-node-aap-job` / `syntara-node-aap-workflow` refs). These
are real registry refs, so the target cluster pulls them directly — no local build
or `kind load`. But `migration-test` is a **mutable tag in a personal namespace**,
not a digest-pinned artifact from an owned CI pipeline. The dev full-stack compose
also wires the two required settings on the `temporal-worker` service (that is where
the AO dispatch activity runs) — `APP_SCRIPT_NODES_ENABLED` and
`APP_NODE_CONTAINER_IMAGES` — see the commented block in
[`podman-compose.yml`](../../../podman-compose.yml).

**Why acceptable for MVP.** The SDK node images (script, agent, http-request,
aap-job, aap-workflow) are built from a separate, not-yet-merged branch
(`feat/sdk-node-containers`, PR #701) and pushed by hand to a personal quay
namespace. That is enough to pull an image into the cluster and demo the full
cold-start path without a local build, but it is not a trustworthy supply chain,
so the publishing obligation below still stands.

**Followup shape.** (1) Land the SDK node containers work so the Containerfiles
and node runtime reach `devel`/`1803`. (2) Have CI build and push immutable,
digest-pinned node images to an **owned** registry/namespace the target clusters
can pull. (3) Replace the personal-namespace `migration-test` default with those
digest-pinned refs, with the `APP_`-prefixed setting still available for installers
shipping a custom image. `script_nodes_enabled` stays `False` by default (security
gate); only per-environment config (like the dev compose) enables it.

### 10. Script nodes have almost no environment surface — and no secrets at all

**Shortcut.** A script node's entire input model
(`ScriptExecutorParameters`, `workflow_engine/models/workflow_definition.py`) is
three fields: `language` (`bash` | `python`), `code`, and `environment`
(`dict[str, str]` of env vars). There is **no** field for secrets/credentials,
working directory, resource requests/limits, per-node timeout (that lives on the
separate `NodeSettingsNoRetry.timeout`), network/proxy config, package installs,
or interpreter/version selection beyond the two languages.

Of the environment surface that *does* exist, only plain env vars flow, and they
flow **over the gRPC invocation, not the pod spec**. `ep_dispatch_activity.
_build_invocation()` puts `environment` inside the envelope's `inputs`
(`inputs.environment`) and hard-codes `credentials.resolved = {}`; the in-container
node runtime (out-of-tree, PR #701) is what must read `inputs.environment` and
apply it. `pod_body()` deliberately wires **no** `env`, `envFrom`, secret volume,
or credential mount onto the container — only a memory `tmp` emptyDir and the
optional `agent-tls` transport cert. So: env vars are delivered but untested
end-to-end here (no in-tree runtime to apply them), and **secrets are not plumbed
for script nodes anywhere**.

**Why acceptable for MVP.** The demo goal is a single `echo` with no inputs and
no secrets. Script nodes are the only wired type and carry no credentials, so an
empty `credentials.resolved` is correct today (this is the flip side of shortcut
1 — nothing sensitive is stored because nothing sensitive is passed).

**Followup shape (a large, separate work item — likely its own epic story, not a
`node_container_images` line-item).** To make script nodes production-useful:

1. **Env vars, verified end-to-end.** Once the SDK runtime lands (shortcut 9),
   add a test that a workflow-set `environment` actually reaches the process
   (`os.environ`) in the pod. No API change — just close the untested gap.
2. **Secrets/credentials.** This is the big one. `ScriptExecutorParameters` needs
   a credential/secret reference field, and script must be routed through the
   existing workflow-time credential resolver
   (`dynamic_workflow._resolve_and_inject_credentials` →
   `resolve_workflow_credentials` activity → `_resolved_credentials`; today script
   is deliberately excluded from `_REFERENCE_BEARING_NODE_TYPES`). Then
   `_build_invocation` must populate `credentials.resolved` from that instead of
   `{}` — **and** the plaintext-`work_items.payload` problem (shortcut 1) must be
   solved first, or resolved secrets land in the DB in the clear. The node runtime
   must then materialize `credentials.resolved` inside the container (as env or
   files) with scrubbing on the way back out (the credential codec/interceptor
   machinery already exists for other node types).
3. **Resource limits / node settings.** Per-node CPU/memory (today `pod_body`
   hard-codes requests/limits) and possibly working directory — surface them on
   the node model and map them in `pod_body`. This overlaps shortcut 5's
   per-target metadata refactor.

The cleanest boundary decision to make up front: secrets travel on the gRPC
`credentials_json` channel (like other node types), **not** as Kubernetes pod env
or Secret objects — so this work is about the resolver + envelope + runtime, not
about adding `env`/`envFrom` to `pod_body`.

---

## Transport evolution: from port-forward to production

The MVP's data path is a **Kubernetes API-server port-forward** wrapped in a
loopback bridge: `transport.py` → `forward.py` → `node_protocol.client.invoke`,
with `grpc.insecure_channel` dialing a `127.0.0.1` listener whose bytes are pumped
through `connect_get_namespaced_pod_portforward`. That exists for one reason: the
EP worker runs **outside** the execution cluster (a compose container talking to
kind), and a port-forward is the only way an outside process reaches a pod — every
byte is proxied through the kube-apiserver → kubelet → pod.

This is fine for local dev and bootstrap but is **not** the production data path.
Three problems at any real scale: (a) it routes all node I/O through the
control-plane apiserver (a component sized for control traffic, with in-flight and
streaming limits, and the ongoing SPDY→WebSocket migration); (b) `pods/portforward`
is a broad grant (a socket into any pod in the namespace); (c) the channel is
`insecure` — confidentiality leans entirely on the apiserver tunnel, and the
per-call Python bridge is a throughput/reliability bottleneck that pairs with the
serial-dispatch shortcut (7).

There are two phases to plan, and they are **not** the same scope:

**Near-term (single cluster, in-between — next phase of ANSTRAT-1803).** Support
exactly **one** K8s cluster and get off the apiserver port-forward by giving the
EP worker direct pod reachability. The likely shape: **co-locate the EP worker
inside the execution cluster** (run it as a Deployment) and reach the node over a
`Service` / pod IP, or an equivalent single-cluster network shortcut. At that
point the port-forward and the loopback bridge (`forward.py`) can go away, and the
`agent-tls` secret already scaffolded in `pod_body` becomes the basis for **mTLS
gRPC straight to the pod** (replacing `insecure_channel`). This is deliberately
scoped to one cluster — no cross-cluster routing, no mesh.

**Production (multi-cluster / edge — OUT of ANSTRAT-1803 scope; file separately).**
The full answer is transport option **(B): a receptor/mesh transport** so the
control plane reaches execution clusters it has no direct route to (the AWX
precedent: work reached over the receptor mesh, never kube port-forward). This is
where the "introduce the seam against two concrete implementations" note below
finally applies — a `receptor` transport alongside the direct one. **Do not file
this under 1803**; it is a later epic. Capturing it here so the near-term
single-cluster work is not mistaken for the end state.

## Deliberately *not* abstracted (for now)

No receptor/transport indirection layer was introduced **in the MVP**. The
transport is a direct Kubernetes port-forward + gRPC call. Per the phasing above,
the seam for a second transport (receptor) belongs to the out-of-1803 production
work, introduced then against two concrete implementations — not speculatively in
the MVP. Until the near-term single-cluster work starts, adding a transport
interface would be premature.
