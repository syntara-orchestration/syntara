# Execution Plane service-isolation decisions to revisit

Updated 6 October 2026 for EP PR #1 and AO PR #728. These decisions describe
the first isolated release. This file is a mirror; the EP repository copy is
canonical and should be updated first.

Canonical source: [EP `docs/service-isolation-revisit-decisions.md`](https://github.com/syntara-orchestration/syntara-execution-plane/blob/migration/ANSTRAT-1803/docs/service-isolation-revisit-decisions.md).

## Confirmed first-release choices

| Decision | First release | Revisit trigger |
| --- | --- | --- |
| PostgreSQL topology | Reuse the existing PostgreSQL server, with a separate EP database and EP-owned runtime/migration roles. AO and EP runtime credentials cannot connect to the other service database. | EP needs an independent availability window, resource isolation, backup/restore target, compliance boundary, or recovery from server-level failure. |
| Client scope | AO is the only configured EP client. Keep client identity and project scope in the service contract. | Before onboarding another client; define client registration, grant administration, quotas, and audit ownership. |
| AO submission outage | Retry using the same request ID for a bounded period. AO persists the first encrypted invocation and reuses that exact payload, image, and limits on Temporal retries. Do not fall back to in-process execution after an ambiguous submit. | Operational data shows retry volume, queue age, or outage duration needs a different policy. |
| Integration convergence | Save AO integration state and display `pending` while its revisioned outbox converges in EP. Only expose a target after EP reports it ready. | Before production users depend on the flow; confirm retry controls and user-facing failure recovery. |
| Completion path | EP persists a completion outbox and sends an authenticated callback to AO. AO durably deduplicates it and bridges it to Temporal; AO can reconcile missed callbacks against EP. EP has no Temporal connection. | Validate callbacks across the real service network; make polling primary if inbound callback routing is disallowed. |
| Workload scope | Script nodes only in the first release. AO chooses the image and versioned invocation. | Before enabling each additional node type, review its credential, output, resource, and protocol needs. |
| Worker selection and throughput | One EP worker replica processes one WorkItem at a time. Selection remains the first active project-eligible default target. | Before increasing replicas or enabling more clients; first wire a real capacity reservation and ranked placement path. |
| Persisted invocation protection | EP encrypts WorkItem payloads with its configured AES-256 key. Forward migration encrypts existing rows; the same key must be available to API, worker, and migration processes. | Define key rotation, backup/restore, and retention procedures before production data depends on this key. Results and callback diagnostics have separate retention/redaction needs. |

## Logical job, worker, and Kubernetes resources

The WorkItem and its execution-attempt lifecycle are independent of any
worker Pod. `WorkerManager.dispatch(work_item)` owns obtaining a worker and
invoking it. In this iteration, a cold-start manager creates one
`batch/v1` Job for one claim-generation attempt, then releases its exclusively
owned resources. Job and Pod names/UIDs are backend allocation details; they do
not define WorkItem completion, failure, or cancellation.

The Job uses one completion, one parallel Pod, `backoffLimit: 0`, a bounded
deadline, and a TTL cleanup backstop. Result persistence precedes Job cleanup;
resource cleanup status is recorded separately. A warm-worker backend may
attach to an existing worker without changing the WorkItem contract. It must
return or quarantine a shared worker when one WorkItem ends; it must not delete
a shared Pod as a side effect of logical completion or cancellation.

Revisit the cold-start resource choice if Job observation, TTL behavior, target
RBAC, or resource cleanup proves unsuitable. Kubernetes Jobs do not provide
exactly-once process execution. The current SDK runtime accepts one invocation
and then exits; warm reuse requires a protocol/runtime change for readiness,
per-invocation state, cancellation, and safe cleanup.

## gRPC, output, and uncertain outcomes

gRPC is the only application channel between EP and the node runtime. The
versioned SDK protocol carries inputs, progress, errors, results, and returned
stdout/stderr fields. No workload input Secret, Pod-log result retrieval,
`exec`, or stdin/stdout control path is part of this contract. Management
credentials and service TLS Secrets are separate from user credential
injection. Do not define a credential mount convention before ANSTRAT-2422.

The initial transport is an authenticated Kubernetes API port-forward carrying
the gRPC stream to a loopback client. It is a bootstrap choice, not a claim
that direct pod networking or gRPC mTLS has been solved. Revisit direct
networking/mTLS after testing the chosen CNI and deployment topology.

EP only requeues failures for which it has positive evidence that Execute was
not submitted. If the gRPC outcome is ambiguous after that boundary, EP keeps
the WorkItem in `reconciliation_required` and never automatically allocates a
second worker for that attempt. EP emits the state to AO through its completion
outbox, so AO fails the activity with `WorkloadOutcomeUnknownError` instead of
waiting indefinitely. The EP WorkItem remains visible for operator
investigation; callback delivery does not claim that execution stopped. The SDK
has no result replay/status API. If EP loses the terminal frame before
committing it, Job completion cannot recover the business result or prove
replayed side effects safe; operators must investigate and any retry must use a
new request identity. Revisit stronger recovery only with a durable
result-delivery/replay extension in the node protocol/runtime.

Cancellation requests cooperative gRPC `Cancel`. EP reports `cancelled` only
after the invocation is confirmed stopped. For an exclusively owned cold-start
Job, foreground Job deletion is the forced-termination fallback. If a terminal
result is received during the race, completion wins. A reused worker requires
a return/quarantine decision and cannot inherit unconditional Pod deletion.

## Additional revisit items

- Move the digest-pinned script image from the maintainer-owned public Quay
  namespace to an organization-owned publishing pipeline.
- The node protocol is vendored from step-types commit
  `f2ef663b9d7ae55b2ebcf4a421ece356cb7e6026`; keep generated files reproducible
  and review the protocol against the SDK before changing the pinned runtime.
- Keep NetworkPolicy creation and cleanup in the cold-start backend. Validate
  the target CNI, actual allowed/forbidden traffic, and the API port-forward path
  together. The aged orphan-policy reconciler only removes policy after the
  associated Job and Pods are absent.
- Define result/outbox retention and diagnostic redaction. Payload encryption
  does not automatically encrypt terminal outputs or make arbitrary script
  output free of sensitive data.
- Before increasing allowed egress, review AO, EP, Temporal, database, and
  cluster-management destinations. The initial egress allowlist is operator
  configuration, not a per-user policy.

The earlier integration and callback decisions remain in force: AO owns the
user integration and Temporal state; EP owns its execution copy and work state;
callbacks and revisioned integration updates are durable, authenticated service
contracts.
