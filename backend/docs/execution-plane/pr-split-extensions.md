# Extensions introduced by the Execution Plane repository split

This document separates capabilities inherited from the execution-plane feature
snapshot from the code needed to make AO and EP independent services.

## Split-specific extensions

| Extension | What the split adds |
| --- | --- |
| Standalone EP HTTP service | A separately started API with its own settings, lifespan, health checks, auth, and versioned work/target/binding routes. AO and EP no longer share a Python process or database session. |
| Service identity and project authorization | AO sends short-lived scoped tokens; EP validates issuer, audience, client identity, project grants, and operation scopes. |
| AO REST facade | AO retains its user-facing endpoints and project authorization, then proxies permitted operations to EP over HTTP rather than importing EP registries. |
| Durable, idempotent dispatch | AO persists the first encrypted request before submit, retries with a stable request ID, and reuses the frozen payload/image. EP scopes idempotency by client/project/request and rejects a conflicting payload. |
| Versioned AO-to-node invocation | AO constructs `{invocation, image, output_config}` with workflow/run/activity context, runtime settings, timeout, and output cap. Script is the only dispatched type in release one. |
| Payload-at-rest encryption | EP encrypts persisted invocation payloads and migrates existing WorkItem payloads with an EP-owned key. This extends management-credential encryption to script inputs. |
| Independent completion callback | EP commits result and completion outbox state, then calls AO. AO persists/deduplicates callback inbox events and bridges them to the original Temporal activity; EP has no Temporal task token or Temporal connection. |
| Independent database and migration ownership | EP runs its own migration chain and runtime/migrator roles in an EP database on the existing PostgreSQL server. AO no longer connects to EP tables. |
| Claim fencing and unknown-outcome handling | EP renews leases and fences WorkItem updates by owner/generation. It retries only failures known to be before Execute; uncertain gRPC outcomes become `reconciliation_required`, are delivered through the callback outbox, and fail the AO activity explicitly instead of leaving it waiting or starting a duplicate execution. |
| Independent resource-cleanup state | Backend Job name/UID and cleanup state are stored separately from WorkItem result. The EP worker persists a received result before cleanup, and a reconciler removes old NetworkPolicies only after Jobs and Pods disappear. |
| Cold-start Kubernetes Job wrapper | A single-attempt Job is an internal provisioning resource for one attempt; the WorkItem contract remains independent of Pod lifecycle so a later manager can attach to a warm worker. |
| Per-attempt NetworkPolicy | EP installs a policy before the Job, denies ingress, allows DNS and configured CIDRs, and records cleanup independently. Target CNI enforcement still needs live validation. |
| Standalone deployable artifact | EP is a standalone Python package and image with API, worker, and migration processes. AO compose/build helpers use the separate EP checkout. |

## Functionality moved from the feature branch

The feature branch already contains the gRPC node protocol, the
`vanilla_k8s` worker manager, typed Kubernetes placement, hardened workload
Pods, and node result mapping. Those capabilities are being moved into the
standalone repository; they are not service-split inventions. In particular,
the source tree already has the [node protocol and port-forward transport](https://github.com/syntara-orchestration/syntara/blob/f5d290abfab300a41c482ba3dfe4bc974b85e8be/backend/execution-plane/src/execution_plane/node_protocol/client.py)
and the [Vanilla Kubernetes backend](https://github.com/syntara-orchestration/syntara/tree/f5d290abfab300a41c482ba3dfe4bc974b85e8be/backend/execution-plane/src/execution_plane/worker_manager/vanilla_k8s).

The split changes ownership and transport between services: AO-to-EP is HTTP,
while EP-to-node remains gRPC. The initial deployment keeps one PostgreSQL
server but separates the EP database and roles. It configures AO as the first
client and enables script execution only.

## Validation status

These changes have not yet been validated as a combined AO + EP deployment on
a live CNI-enforcing cluster. A successful HTTP unit test or mocked
Kubernetes test does not establish callback routing, real gRPC port-forward,
NetworkPolicy enforcement, migration safety, or crash recovery across both
services. The combined test matrix is recorded in the migration plan and
remains release evidence to collect.
