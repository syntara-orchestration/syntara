# Execution Plane: Kubernetes Backend

> **Design in progress.** This document covers the `vanilla_k8s` backend type: how the
> EP worker schedules, monitors, and reclaims pods on a Kubernetes cluster to execute
> scripts. It also covers the near-term integrated operator approach and the path toward
> a separate EP operator.
>
> **Tense convention:** Present tense = exists today. Future tense = agreed direction not
> yet implemented. Receptor and operator-split sections are explicitly marked as future.

---

## 1. Deployment approach

### Near-term: integrated in the AO operator

In the near-term, the EP worker and the default local K8s execution cluster are both
provisioned by the existing `automation-orchestrator-operator`. This mirrors how the
syntara `worker` and `background-worker` Deployments are managed today in
`component_worker.go`.

Two things the AO operator adds:

1. **EP worker Deployment** — the `execution-plane` container image, running
   `execution-plane-worker`. Modeled after `reconcileWorker` / `buildWorkerDeployment`.
   Needs DB env vars (`APP_DATABASE_URL`), Temporal env vars, and S2S TLS volume mounts.
   No Redis. See [AAP-93321].
2. **Default local cluster resources** — a dedicated namespace (e.g. `aap-execution`),
   a ServiceAccount, and RBAC that grant the EP worker permission to create and manage
   pods in that namespace. This IS the "default local K8s cluster" that EP manages.

The EP worker runs inside the AO operator's namespace and talks to the K8s API
**in-cluster**, using the ServiceAccount the operator provisions in the execution
namespace.

### Future: split to a separate EP operator

The AO operator is a temporary host. EP is intended to be a separately deployed service
with its own operator (see `cluster-and-target-model.md §2`). The split requires:

- An `execution-plane-operator` that manages the EP worker Deployment and its default
  cluster resources independently.
- AO depends on EP (via the ep-client library) rather than managing it directly.
- The AO operator drops its EP-specific reconcile functions.

Keeping this split in mind: do not bake AO-specific assumptions (TLS CNs, checksum
annotations, `app.kubernetes.io/part-of=automation-orchestrator`) into the EP worker's
Deployment spec. Prefer EP-owned constants that the AO operator delegates to, so the
split is a removal, not a refactor.

---

## 2. What the operator provisions (the local cluster)

The operator creates these resources in the execution namespace at reconcile time:

| Resource | Purpose |
|---|---|
| `Namespace` (e.g. `aap-execution`) | Isolated space for EP-managed pods |
| `ServiceAccount` (`ep-worker`) | Identity for K8s API calls from EP worker |
| `Role` | Namespace-scoped pod permissions (see §4) |
| `RoleBinding` | Binds `ep-worker` SA to the Role |
| (Optional) `NetworkPolicy` | Restrict pod egress/ingress within the execution namespace |

The EP worker authenticates to the K8s API using the in-cluster service account token
mounted at `/var/run/secrets/kubernetes.io/serviceaccount/`. No external kubeconfig is
needed for the local cluster.

For customer-registered remote clusters, the EP worker uses API credentials stored in a
Secret (URL + token or kubeconfig) — these are configured on the `ExecutionTarget` record.

---

## 3. K8s API operations

The `WorkerManager` protocol (`worker_manager/base.py`) defines the interface. A
`VanillaK8sWorkerManager` implementation will use the following API calls.

### Cold-start execution

A cold-start job creates a pod, waits for it to complete, retrieves output, then deletes
the pod.

```
POST   /api/v1/namespaces/{exec-ns}/pods
         → create pod from WorkItem payload (image, env, mounts, secrets)

GET    /api/v1/namespaces/{exec-ns}/pods/{name}
  or   GET /api/v1/namespaces/{exec-ns}/pods?watch=true&fieldSelector=metadata.name={name}
         → watch for phase: Succeeded | Failed

GET    /api/v1/namespaces/{exec-ns}/pods/{name}/log?container={c}
         → retrieve stdout/stderr after completion

DELETE /api/v1/namespaces/{exec-ns}/pods/{name}
         → cleanup (best-effort; may be omitted in TTL-based GC)
```

Pod template fields populated from `WorkItem.payload`:

| Field | Source |
|---|---|
| `spec.containers[0].image` | ExecutionEnvironment / cold-start profile |
| `spec.containers[0].env` | Secrets + EP-injected runtime env |
| `spec.containers[0].volumeMounts` | Profile-specified mounts (cold-start only) |
| `spec.volumes` | Corresponding volume definitions (Secrets, ConfigMaps) |
| `metadata.labels` | WorkItem ID, ExecutionTarget ID — for observability and GC |
| `spec.restartPolicy` | Always `Never` for cold-start jobs |

### Warm pool

A warm pool is a pre-provisioned set of idle pods ready to accept work with low latency.
Each warm pod runs a purpose-built entrypoint that reads one work unit from stdin, executes
it, writes the result to stdout, and then **exits cleanly**. It does not loop.

**Provisioning (at Target creation / restart):**

```
POST /apis/apps/v1/namespaces/{exec-ns}/deployments
         → create Deployment with fixed image, env, mounts (Target-level, immutable)
           spec.replicas = pool_size
           spec.template.spec.restartPolicy: Always   (Deployment default)
           spec.template.spec.containers[0].stdin: true
```

`restartPolicy: Always` means Kubernetes restarts the container whenever it exits — whether
after completing work or on failure. On each restart, the container gets a fresh writable
layer from the image; any state the previous run wrote to the container filesystem is gone.
This is the isolation guarantee. Note: `emptyDir` volumes are scoped to the Pod (not the
container) and survive restarts — avoid writing cross-job state there.

The Target's status transitions: `BOOTSTRAPPING` → `ACTIVE` when `readyReplicas` reaches
the configured minimum.

**Dispatching work to a pod:**

EP picks any running pod from the Deployment that is not already claimed (tracked in EP
state), and attaches to its container. The exact mechanism is being defined by the
ANSTRAT-2422 team; they are currently exploring Extensions to expose a gRPC server for
work dispatch. The approach below is a spitball for how the core loop would work:

```
POST /api/v1/namespaces/{exec-ns}/pods/{name}/attach?stdin=true&stdout=true&stderr=true
         → streaming connection to the container's stdin/stdout
         → write work unit as payload; read result back on stdout
```

K8s allows only one `attach` session per container at a time, enforcing that a pod is
either idle (no active attach) or busy (attached, running one job).

**After work completes:**

The container exits. Kubernetes restarts it automatically (via `restartPolicy: Always`),
bringing it back to an idle state with a clean filesystem. The Deployment's `readyReplicas`
is maintained at `spec.replicas` — no EP-side pool management required.

**Deprovisioning (Target delete / deactivate):**

```
DELETE /apis/apps/v1/namespaces/{exec-ns}/deployments/{name}
```

Drain in-flight work before deleting (transition to `UNAVAILABLE`, wait for active pods
to complete or time out, then delete).

---

## 4. RBAC requirements

The EP worker's ServiceAccount needs these permissions in the execution namespace:

```yaml
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["create", "get", "list", "watch", "delete", "patch"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
  - apiGroups: [""]
    resources: ["pods/attach"]
    verbs: ["create", "get"]   # attach to warm pool pods for stdin/stdout dispatch
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["create", "get", "list", "watch", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get"]             # to read secrets for injection into pods
```

These are namespace-scoped (`Role`, not `ClusterRole`). The execution namespace is fully
controlled by EP; no cluster-wide permissions are needed for the local cluster case.

---

## 5. Worker group routing

`WorkItem` records carry label selectors that express which `ExecutionTarget` should handle
them (see `cluster-and-target-model.md §5` for the Profile → Target matching design).

At dispatch time, the EP worker:

1. Reads the `ExecutionTarget` record for the claimed `WorkItem`.
2. Constructs the K8s client for that target's endpoint (in-cluster for local; kubeconfig
   secret for remote).
3. For cold-start: creates a pod in the target's execution namespace.
4. For warm-pool: finds an idle pod in the target's Deployment and claims it.

Priority and ordering between targets is part of the matching problem documented in
`cluster-and-target-model.md §5` and is not yet defined at the implementation level.

---

## 6. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Pod eviction during execution | Watch returns `Failed` with reason `Evicted` | Retry WorkItem (up to retry limit); prefer a different node via anti-affinity |
| Node unreachable / kubelet timeout | Pod stays in `Running` past deadline | Kill pod, mark WorkItem failed; operator-level node health drives longer-term response |
| EP worker crash mid-dispatch (cold-start) | Pod orphaned with EP's claim label | Startup sweep: find pods with `ep.execution/work-item-id` labels and no active WorkItem; delete orphaned pods |
| EP worker crash mid-dispatch (warm-pool) | Attach dropped before or during payload write | The container's stdin read has a timeout. If the full payload does not arrive within N seconds of an attach, the container exits (without running any job). Kubernetes restarts it immediately (`restartPolicy: Always`), returning the pod to an idle, claimable state. The EP side detects the failed attach and calls `WorkStore.requeue_on_placement_failure()`. |
| Warm pool Deployment degraded | `readyReplicas < minReplicas` | Target transitions to `DEGRADED`; cold-start fallback if available |
| Execution namespace deleted externally | API calls return 404 | EP reconciler (or AO operator) re-provisions the namespace and RBAC |

---

## 7. Configuration

Required fields on `ExecutionTarget` for `backend_type = vanilla_k8s`:

| Field | Notes |
|---|---|
| `endpoint` | K8s API server URL. Empty or `in-cluster` for the local default cluster. |
| `labels["execution_namespace"]` | Namespace where EP creates pods. Defaults to `aap-execution` for the local cluster. |
| `pool_size` | Max concurrent jobs. NULL for cold-start (unlimited). For warm targets, also the Deployment replica count. |
| `current_jobs` | Live counter, incremented on dispatch and decremented on completion. Managed by EP; not user-configurable. |
| `labels["pool_size"]` | (Warm targets only) Deployment replica count — should match `pool_size`. |
| `labels["image"]` | (Warm targets only) Fixed container image for the pool. |
| `labels["service_account"]` | ServiceAccount for pod `spec.serviceAccountName`. Defaults to `ep-worker`. |

The `ExecutionTarget.labels` JSONB column carries K8s-specific config that does not belong
in normalized columns — it is the extension point for backend-specific settings.

