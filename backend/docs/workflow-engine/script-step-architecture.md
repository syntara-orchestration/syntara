# Script Step Execution Architecture and Security Boundary

- **Status:** Proposed for architecture and Product Security review
- **Review disposition:** Not submitted; Product Security intake route and required approvers are not available in this workspace. This document is not an approval.
- **Last evidence review:** 2026-11-14
- **Scope:** AO Script node → Execution Plane (EP) → OpenShift/Kubernetes workload → SDK container ABI → script subprocess.

This document records the proposed production execution contract, evidence from the checked-in implementation and adjacent repositories, the outstanding decisions, and the scenarios that AAP-98866/AAP-98867 should verify. It does not authorize an implementation or claim that the design has been accepted by Product Security.

## 1. Decision summary

The recommended baseline is **one cold-start Kubernetes Job and one SDK Execute invocation per EP work-item attempt**. The SDK server's ability to handle concurrent requests is a runtime capability. It does not mean that one Job is shared across multiple AO node executions in the current EP lifecycle.

| ID | Proposed decision | Evidence / rationale | Decision owner and state |
|---|---|---|---|
| D1 | One EP attempt owns one deterministic Job, one worker Pod, and at most one Execute submission. Do not reuse the Pod across work items. | EP cold-start design creates a Job with one completion and `backoffLimit: 0`; transport submits Execute once. It fences claim generations and requires reconciliation after an ambiguous submission. | EP architecture + AAP-98873 integration owner. **Proposed; approval pending.** |
| D2 | The SDK workload server may serve concurrent calls, but the selected cold-start lifecycle uses one invocation per Pod. EP dispatch concurrency is a separate control. | Step-types PR #8 and current script runtime admit multiple concurrent Execute handlers; EP PR #107 bounds concurrent dispatches. Neither requires a shared warm Pod. | SDK architecture AAP-95467 + EP. **Proposed; confirm explicitly.** |
| D3 | AO uses the EP-provided EP Client to call EP. AO supplies a trusted, digest-pinned image and resolved step revision; EP selects the registered target, provisions the isolated Job, and owns the workload-to-OpenShift transport. A workflow cannot choose an arbitrary image or target namespace. | EP `work.execute` accepts image and selectors; AO must constrain those values before submitting. The EP Client is the supported AO-to-EP calling surface; its exact API, authentication, retry, and version contract must be recorded in AAP-98873. | AO/EP integration AAP-98873, coordinated with AAP-97389. **Proposed; client contract/version pending.** |
| D4 | Script `environment` is ordinary, caller-controlled input, never a secret-delivery mechanism. Script steps do not declare workload credentials in their current manifests. No credential value is exposed to arbitrary Script code in this design. | Current script manifests expose `code`, `environment`, and output bounds; they do not declare a credential recipe. | Script step owner + Product Security. **Proposed; security review pending.** |
| D5 | For credential-capable plugins, the SDK bidirectional callback is the workload credential contract. EP must resolve a declared recipe for the current attempt and return it only on the authenticated SDK stream. This does not make credentials available to Script unless a separate Script design is approved. | SDK ADR 0011 defines invocation-scoped callbacks and mTLS; current EP workload protocol says bound credentials are still unavailable. | EP + SDK architecture AAP-95467 + AAP-97389. **Contract direction documented; end-to-end resolver not proven.** |
| D6 | A submitted script is not automatically replayed after a timeout or uncertain result. Script side effects make exactly-once behavior impossible to infer from transport status. | EP records `reconciliation_required` after uncertain submission; its cold-start notes explicitly say Job ownership does not create exactly-once execution. | EP + AO retry owners. **Proposed; confirm AO mapping and user-visible state.** |

## 2. Call chain and ownership

```mermaid
sequenceDiagram
    autonumber
    participant U as Workflow / caller
    participant T as Temporal
    participant A as AO worker activity
    participant EC as EP Client (AO dependency)
    participant C as AO credential authority
    participant E as EP API + Work Store
    participant W as EP worker / K8s manager
    participant K as Customer OpenShift API
    participant P as Isolated Job Pod
    participant S as Script subprocess

    U->>T: Start workflow containing Script node
    T->>A: Schedule Script activity
    A->>A: Validate node config; map language to configured plugin image + revision
    A->>EC: Submit work.execute (image digest, selectors, inputs, timeout, credential refs)
    EC->>E: Call EP supported API/command surface
    E-->>EC: Accepted WorkItem reference
    EC-->>A: Return submission result
    E->>E: Validate and persist WorkItem; select active ExecutionTarget
    E->>W: Claim one attempt (fenced claim generation)
    W->>C: credential.resolve (OpenShift Cluster credential reference)
    C-->>W: Short-lived cluster API credential
    W->>K: Create per-attempt NetworkPolicy and Job
    K-->>W: Job UID and owned Pod
    W->>K: Open authenticated port-forward to owned Pod
    W->>P: SDK Health; verify ABI and exact step revision
    W->>P: One bidirectional SDK Execute stream
    opt Plugin requests a declared workload credential
        P-->>W: SDK credential_request (logical recipe name)
        Note over W,C: EP workload resolver currently returns unavailable for bound workload credentials
    end
    P->>S: Spawn Python or Bash child process
    S-->>P: Exit status, stdout, stderr (bounded)
    P-->>W: One SDK terminal Result or Failure
    W->>E: Persist result and completion outbox before cleanup
    W->>K: Delete owned Job (foreground), then per-attempt policy
    E-->>A: work.execute.completed callback
    A->>T: Map business output/error to activity result
    T-->>U: Workflow execution state and node output
```

### Component and data ownership

| Component | Owns | Must not own / receive |
|---|---|---|
| AO workflow engine | User-facing node configuration; workflow and Temporal activity identity; trusted mapping from `language` to allowed image digest, revision, and target selectors; AO retry policy; projecting EP result to the Script node output. | OpenShift API token in a workload; user-supplied image/namespace authority; EP Kubernetes Job lifecycle. |
| EP Client library used by AO | EP owns and publishes the supported client contract/release; AO uses the client to make supported calls to EP. Exact method names, auth, retry behavior, and version compatibility belong to AAP-98873/client documentation. | Workflow policy, target selection, OpenShift Cluster credentials, or Job lifecycle. Do not duplicate EP command/API semantics in AO. |
| EP API and Work Store | WorkItem state, target selection, attempt/claim generation, timeout and cancellation state, result persistence, completion notification, cleanup status. | AO database or Temporal history access. EP is a separate service and must not connect directly to either store. |
| EP worker / Kubernetes manager | Cluster API client; namespaced Job/NetworkPolicy lifecycle; workload transport; SDK stream; credential resolution adapter for declared workload recipes; reconciliation and diagnostics. | Arbitrary workload code execution in the manager process; unbounded image choice or cross-namespace access. |
| EP scheduler, target reconciler, and resource monitor | Claim/lease fencing, active target selection, target health, and dispatch admission. Cluster API health checks resolve the Cluster credential through AO. | Scheduling work to disabled/draining/unhealthy targets or using workload recipe credentials as Cluster credentials. |
| EP credential resolver and completion notifier | Short-lived `credential.resolve` callback to AO for the Cluster API credential; durable `work.execute.completed` delivery/acknowledgement for terminal or uncertain outcomes. | Persisting resolved secret values or dropping the outcome when AO is temporarily unavailable. |
| Customer OpenShift cluster | Namespace, admission, scheduling, quotas/limits, registry pulls, NetworkPolicy enforcement, Job/Pod execution and deletion. | Long-lived workload credentials injected into every Pod by default. |
| Script image / SDK runtime | Input validation; one request's child process; bounded capture; cancellation and terminal SDK result. | AO/EP control-plane credentials or OpenShift API token. |
| Python/Bash process | Executes supplied code with its configured environment and filesystem/network permissions of the containing Pod. | A separate security principal from the SDK server; current implementation does not establish that boundary. |

### Evidence snapshot and drift

Current Syntara `devel` evidence is commit `e721ffaa0dc6bb780bc6542bd61294014911f3e7`. Its `execute_script_activity` runs arbitrary user-supplied code in the Temporal worker process without additional sandboxing and explicitly says Script is not recommended for production. This is the current AO behavior, not an AO→EP integration. A prior workspace feature branch (`feat/ANSTRAT-2523-direct-openshift-script`, commit `8ec9c163f07589f1a99d310d341aab42c4bb111a`) attempted a direct worker-to-OpenShift path; that path also is not the target EP architecture. Neither implementation is evidence that AO submits the proposed EP `work.execute` call.

EP evidence was read from `devel` commit `7c50410ac8a61478fe54ba6bfb245cb9018f1474`; step-types from `devel` commit `f3c43bf1fd2c310b2008dd75f09bbdcbe72477b6`; SDK from `devel` commit `448de6d8f7ad6cba2d5250c31cd82a1dd57f9812`. References:

- [EP cold-start Job details](https://github.com/syntara-orchestration/syntara-execution-plane/blob/7c50410ac8a61478fe54ba6bfb245cb9018f1474/docs/kubernetes-jobs-followup.md)
- [EP SDK workload protocol](https://github.com/syntara-orchestration/syntara-execution-plane/blob/7c50410ac8a61478fe54ba6bfb245cb9018f1474/docs/workload-protocol.md)
- [EP OpenShift/Kubernetes installation and security notes](https://github.com/syntara-orchestration/syntara-execution-plane/blob/7c50410ac8a61478fe54ba6bfb245cb9018f1474/README.md)
- [Step-types PR #8: concurrent SDK server and script implementation](https://github.com/syntara-orchestration/syntara-step-types/pull/8)
- [SDK container runtime and OCI contract](https://github.com/syntara-orchestration/syntara-plugin-sdk/blob/448de6d8f7ad6cba2d5250c31cd82a1dd57f9812/docs/runtime-and-oci.md)
- [SDK ADR 0011: invocation-scoped credential callbacks](https://github.com/syntara-orchestration/syntara-plugin-sdk/blob/448de6d8f7ad6cba2d5250c31cd82a1dd57f9812/.sdlc/adrs/0011-credential-callback.md)
- [Current Syntara `devel` Script activity and its security warning](https://github.com/syntara-orchestration/syntara/blob/e721ffaa0dc6bb780bc6542bd61294014911f3e7/backend/src/syntara/workflow_runtime/engines/temporal/activities/script_activity.py)
- [Prior direct OpenShift feature-branch Script activity](https://github.com/syntara-orchestration/syntara/blob/8ec9c163f07589f1a99d310d341aab42c4bb111a/backend/src/syntara/workflows/workflow_engine/activities/script_activity.py)

**Call-chain validation gap:** Syntara `devel` does not submit this SDK `work.execute` contract from the Script activity. The AO integration with the EP-provided Client and a shared-cluster AO→EP→Script end-to-end trace were not present in the evidence. AAP-98873 must link the client package/version, the AO integration commit/PR, and a trace proving the path before this document can be marked “verified.”

## 3. Invocation, image, and result contract

### Selected lifecycle proposal

1. AO validates Script input and routes `language=python|bash` to the corresponding configured plugin and immutable image digest. AO supplies the compiled step revision, not a legacy fixture identity such as `script.v1`.
2. AO uses the EP-provided EP Client to submit one `work.execute` command with workflow-run identity, step revision, non-secret inputs, runtime context, credential bindings (only if the selected plugin declares them), timeout, and allowed selectors.
3. EP persists a logical WorkItem, assigns one attempt/claim generation, selects an active `Cluster` and `ExecutionTarget`, and launches one cold-start Job with one completion, `parallelism=1`, and `backoffLimit=0`.
4. The EP worker verifies Job/Pod ownership, waits for readiness, negotiates SDK Health, checks the exact advertised revision, and submits one Execute stream.
5. The SDK container runs one Script invocation. Its Python/Bash child process is not a new Pod and shares the container's OS identity and Pod security context.
6. EP persists terminal outcome before deleting the Job. It reports result and cleanup state separately. Finished Jobs have a one-hour TTL backstop; that TTL is not the primary cleanup mechanism.

No warm pool or reused multi-work-item server is selected here. If a warm lifecycle is later proposed, AAP-97389 and SDK architecture AAP-95467 must own its resource return/quarantine, concurrency, credential revocation, and upgrade semantics; this document does not design a competing SDK lifecycle.

### What the three statements mean together

| Statement | Layer | Reconciliation |
|---|---|---|
| EP cold-start Job document | EP resource lifecycle | One Job/Pod per attempt, deterministic attempt identity, no Job retry, explicit cleanup and recovery. |
| Step-types PR #8 says the server supports concurrent Execute calls | SDK server/runtime capacity | The server can admit concurrent handlers (script runtime currently allows up to eight Execute calls while reserving gRPC threads for Health/Cancel). This is useful for other deployment models and does not mean EP shares one Pod in the cold-start path. |
| Initiative says “one invocation” | EP-to-workload invocation contract | For the selected design, one attempt submits Execute at most once. It is not an exactly-once guarantee: a lost response after submission leaves the side effect and result uncertain. |

These statements are compatible only if “one invocation” means one SDK Execute submission for one EP attempt. Architecture owners must confirm that interpretation in AAP-98873 and AAP-95467 before implementation freezes it.

### SDK request/result boundary

The SDK `syntara.container/v1alpha1` Execute stream starts with one request containing invocation ID, workflow-run ID, exact step revision, JSON input, non-secret runtime context, and timeout. The workload can send progress and declared credential requests; it terminates with one `Result` or `Failure`. Credentials are not in `inputs_json` or `runtime_context_json`.

For the Script plugins, the current manifests define:

- Python input: `code`, optional `environment`, optional `max_output_bytes`; Python output: `return_code`, `stdout`, `stderr`, optional `stdout_json`.
- Bash input: `code`, optional `environment`, optional `max_output_bytes`; Bash output: `return_code`, `stdout`, `stderr`.
- Unknown input keys are rejected. `environment` values are plain strings and must be treated as potentially sensitive user data, but they are not protected secrets.
- AO maps the SDK business result to the frozen Script output schema. SDK transport wrapper fields (`statusCode`, `statusMessage`, `errorResult`) are not Script business output fields.

**Contract/version gate:** SDK ADR 0011 changes the `v1alpha1` stream in place and states that old peers are incompatible. EP, AO client, and workload images must use a reviewed compatible SDK release. A version/installation answer is not implied by this document; see AAP-98864/AAP-98871 below.

## 4. Trust boundaries and credential flows

| Data class | Source → destination | Design boundary |
|---|---|---|
| OpenShift connection credential | AO credential authority → EP cluster-credential resolver → EP worker Kubernetes API client | This credential authorizes EP to manage resources in the customer cluster. Resolve only when needed; keep out of WorkItem inputs, Pod env/spec, workload callback, and logs. Use TLS-verified Kubernetes API access. Target-cluster RBAC should be namespaced and least privilege. |
| Workload credential | AO credential reference/authority → EP's per-attempt resolver → SDK credential callback response → requesting plugin | Different from the OpenShift credential. Bind only a declared CredentialRecipe to the selected step; resolve on demand and return only on the authenticated per-invocation stream. The SDK requires authenticated, confidential transport (mTLS in production). Never persist values in WorkItem payload/results, Temporal history, Pod spec/env/files, output, error, or logs. Current EP code accepts opaque bindings but its documented resolver still reports bound credentials unavailable; credential delivery is **not yet proven**. |
| Script inputs | AO → EP WorkItem → SDK Execute → child process | `code` and `environment` are ordinary untrusted input. They may be persisted under the platform's normal workflow/EP data protections and may appear in debug tooling; avoid secrets. Enforce payload bounds and redact from logs. |
| Script output | Child process stdout/stderr/exit code → SDK result → EP Work Store → AO activity/Temporal result | Treat output as untrusted and potentially secret-bearing. Bound, sanitize, and avoid logging the content. Only the business output contract is projected to workflow consumers. Retention and access controls follow AO/EP result stores; Product Security must confirm. |
| EP/AO control-plane secrets | Deployment secret stores → AO/EP service processes | Includes AO↔EP auth/JWT signing/verification, callback tokens, database encryption key/URL, EP server TLS, and EP outbound client mTLS material. Use deployment-managed Secret mounts/secret references. Never copy these into workload Pods. |

### Isolation claim and limitation

The intended isolation boundary is the per-attempt OpenShift Pod plus namespace admission, runtime security context, and enforced network policy. EP currently builds the workload with a non-root UID, `RuntimeDefault` seccomp, no service-account token, no privilege escalation, dropped Linux capabilities, read-only root filesystem, a 64 MiB memory-backed `/tmp`, and CPU/memory requests and limits. Script execution is a child process inside that Pod. The child shares the SDK process's UID and container filesystem/network namespace; it is **not** a separate OS security principal or a general-purpose sandbox. These controls reduce privilege but do not prove resistance to kernel/runtime escapes or same-UID process inspection. Product Security must accept this threat boundary or require stronger isolation before release.

The per-attempt NetworkPolicy denies ingress and allows DNS plus configured egress CIDRs, with forbidden ranges excluded. Customer CNI enforcement must be verified. AO calls EP ingress over HTTPS with a service JWT; deployment-configured mTLS may harden that link. EP calls AO's credential-resolution and completion callbacks over HTTPS with deployment-configured mTLS. EP calls the target Kubernetes API over TLS using a short-lived resolved Cluster credential. The EP worker then opens an authenticated Kubernetes API port-forward to the workload; the SDK gRPC channel itself must use mTLS in production. Port-forward behavior and NetworkPolicy enforcement must be validated together on the supported OpenShift configuration. Do not claim direct Pod-IP reachability or a laptop-to-cluster proxy path as production behavior.

## 5. Customer-provided cluster prerequisites

The customer/operator installation must provide and validate all of the following before enabling Script execution:

1. A supported OpenShift/Kubernetes API endpoint reachable from the EP worker, with trusted CA validation and a credential reference resolved by the approved control-plane credential service.
2. An explicitly selected namespace represented by an active EP `ExecutionTarget`, with namespace ownership and deletion/drain behavior defined.
3. EP dispatcher identity and scoped RBAC. Current EP manifests grant namespaced Job create/get/delete; Pod list and `pods/portforward`; NetworkPolicy create/get/list/patch/delete; and cluster-level namespace `get` for health checks. Do not add Pod create, Pod logs, or Secret reads without a separately reviewed need. Confirm this exact role against the EP release and customer policy.
4. Admission and quotas that permit bounded Jobs/Pods and NetworkPolicies, the required Pod security settings, and the workload image. Configure customer ResourceQuota/LimitRange so EP's requests/limits fit. EP's current Job asks for `100m` CPU/`128Mi` memory, limits `1` CPU/`512Mi`, and caps memory-backed `/tmp` at `64Mi`; the customer must confirm these are suitable or own a reviewed override.
5. A trusted registry path for the selected image digest and pull authorization in the target namespace. AO must supply a release-approved immutable digest; no workflow-authored tag/image may be passed through. Pull-secret ownership/rotation and Konflux/SBOM/signature policy must be documented by packaging/lifecycle AAP-97389.
6. A CNI that enforces NetworkPolicy, tested with the EP port-forward and SDK mTLS path. Allow only required DNS and explicitly approved workload egress CIDRs. The customer owns approval of destinations and external firewall/proxy requirements; EP does not make arbitrary egress safe.
7. Node and namespace policies that enforce non-root execution, default seccomp, no token mount, no privilege escalation, no capabilities, and read-only root filesystem. Any exception is a Product Security decision.
8. Capacity for concurrent dispatches and admission limits. EP dispatch concurrency is separately bounded (EP PR #107 default is eight). Script workload server admission currently allows eight Execute handlers, but the cold-start proposal uses one invocation per Pod; cluster-level resource quotas remain the effective aggregate bound.

Installation details, supported OpenShift versions, exact image-pull mechanism, and the customer operator/EP placement model remain owned by the installation/version stakeholders and AAP-97389. Do not present local ROSA/step-tests settings as universal customer prerequisites.

## 6. Bounds, retry, timeout, cancellation, and cleanup

### Bounds

| Resource | Current implementation evidence | Architecture requirement / gap |
|---|---|---|
| Per-stream output | Script runtime default is 276,480 bytes (270 KiB) per stream; configurable up to 1 MiB per stream. It drains excess bytes and appends a truncation notice. | Freeze default and whether max is customer-configurable. Ensure stderr truncation notice itself remains within the SDK 1 MiB serialized-result cap. |
| Serialized SDK result | Script runtime serializes the result and fails if it exceeds 1 MiB. | EP WorkItem/API and AO/Temporal payload limits must agree; validate the full serialized path, including error/partial output. EP's durable result size behavior needs explicit limit evidence. |
| Script memory | Pod cgroup limit is 512 MiB currently; Python/Bash launchers attempt process address-space limits derived from cgroup. | Pod cgroup is authoritative; document CPU, ephemeral storage, process/PID, file-size, and execution-time constraints. RLIMIT_AS is not a complete sandbox. |
| Environment | Values are length-bounded at 32,768 characters per variable in script runtime; input schema currently accepts string values. | Need an aggregate environment byte/count limit and total Execute request limit before production. |
| Concurrent execution | Script runtime permits eight simultaneous server Execute handlers; EP worker dispatch is separately bounded. | In selected one-Pod-per-invocation lifecycle, size cluster quotas from EP aggregate dispatch ceiling. Product sizing not yet approved. |

Output truncation must be an explicit successful-result policy or a failure policy. Current runtime truncates stream capture but fails if the final serialized output still exceeds 1 MiB. AAP-98866/AAP-98867 should assert exact status, `output_truncated` semantics (if added), and no unbounded memory growth.

### Retry and uncertain outcomes

- **Before Execute submission:** EP may safely retry infrastructure work only after it confirms that no Execute was submitted and no script side effect could have begun. Reuse the same WorkItem but a new fenced claim generation; never attach to an unrelated Job with a matching label.
- **After submission, terminal result received:** persist result and completion notification before cleanup. AO may apply the explicit workflow retry policy only when failure classification permits it; arbitrary Script side effects mean retries are at-least-once and must not be described as exactly-once.
- **After submission, terminal result missing / worker crash / lost channel:** mark outcome uncertain or reconciliation-required. Do not launch a replacement Job automatically and do not fall back to in-process execution. Reconcile owned Job, claim generation, WorkItem, and result persistence; if no result can be recovered, expose an explicit unknown outcome requiring caller policy.
- **Nonzero exit:** return business failure with bounded output; default non-retryable for arbitrary scripts. Any retry requires opt-in and acknowledgement of duplicate side effects.
- **Busy / pre-execution dependency failure:** may be retryable only when EP can prove Execute was not submitted.

### Timeout and cancellation

The invocation timeout is carried in the SDK request and includes execution streaming; EP's work contract currently excludes cleanup from `timeout_seconds`. The Pod active deadline includes startup, invocation, and termination grace. Keep distinct deadlines for scheduling/startup, script execution, cancellation grace, and resource cleanup. The total AO activity timeout must cover those bounds and EP completion notification slack.

On explicit cancellation, AO signals EP; EP marks the attempt cancellation-requested, sends SDK Cancel, waits a bounded grace period, then closes its dedicated channel and deletes the owned Job. Deleting the Job is the final stop mechanism if the child ignores cooperative cancellation. SDK/script cancellation terminates the child process group using TERM then KILL. Record whether cancellation was acknowledged and whether Execute had been submitted. Do not report “cancelled before start” after a possible side effect.

Timeout after Execute submission is potentially an uncertain side effect, even if the SDK reports `TIMEOUT` as retryable. AO's Script policy must not automatically replay arbitrary code unless the user explicitly accepts at-least-once behavior.

### Cleanup and reconciliation

EP persists terminal result before deleting the exclusively owned Job using foreground propagation. It then removes the matching per-attempt NetworkPolicy. The one-hour Job TTL is a backstop; it does not clean NetworkPolicies. EP records cleanup status separately and has a reconciler to remove orphan policies only after confirming the Job and matching Pods are absent. Cleanup failure must not overwrite a committed execution result, but must be visible, retryable operational work, and page/escalate after its delivery SLO.

On ambiguous resource ownership, leave resources intact and report deferred cleanup. Never delete by an unverified label alone. Cleanup must be idempotent by work-item ID, claim generation, Job UID, and policy owner labels. Customer namespace retention or finalizer behavior can delay deletion and must appear in diagnostics.

## 7. Failure walkthroughs and verification matrix

| Scenario | Expected behavior | Test evidence required / ownership |
|---|---|---|
| Normal execution | AO submits one digest-pinned invocation; EP selects target, launches Job, verifies owner/revision, streams Execute, persists output, notifies AO, then cleans Job/policy. | AAP-98866/AAP-98867 full AO→EP→OpenShift E2E; assert one Job, one Execute, one completion, exact business output, cleanup complete. |
| Failure before submission (bad image pull, RBAC denied, Job admission failure, target unavailable) | No script code ran; classify dependency/provisioning failure. Retry only after confirming no Execute submission and clean/fence attempt state. | Inject image-pull/RBAC/admission failures; assert no duplicate Execute and safe cleanup. EP + AO owners. |
| Uncertain outcome after submission (worker crash or channel loss before terminal result) | No automatic second Job. Persist/reconcile attempt as unknown/reconciliation-required; notify AO with explicit unknown outcome or remain pending per agreed contract. | Kill EP worker at boundary after Execute submit; prove no duplicate side effects; assert recovery/operator diagnostics. EP owner. |
| Timeout | Stop script by SDK cancel, then Pod/Job deletion after grace. Timeout is not proof that external side effects did not occur; do not replay by default. | Short deadline plus subprocess and descendant; assert process termination, final classification, and no retry. AAP-98866/AAP-98867. |
| Cancellation | Propagate AO→EP→SDK Cancel; enforce grace and Job deletion; distinguish cancellation-before-submission from cancellation-after-submission. | Cancel before and during execution; assert terminal state, child exit, resource cleanup, no false “not started”. |
| Output overflow | Drain excess while retaining bounded buffers; truncate or fail according to frozen rule; enforce serialized output limit at SDK and EP/AO persistence boundaries. Never log complete content. | Flood stdout and stderr concurrently above limits; assert bounded RSS, cap/marker/failure contract, and no oversized Temporal payload. |
| Cleanup failure | Keep committed result; set cleanup failed/deferred and retain safe ownership metadata; retry cleanup via reconciler; alert if beyond SLO. | Deny Job/policy deletion or make API unavailable; assert result remains stable, retry is idempotent, no unsafe cross-delete. |
| Upgrade with active execution | Existing Job remains pinned to old image digest and compatible SDK; new attempts use new digest. Drain or wait; do not mutate image/protocol underneath an active Execute. Old image stays available for recovery. | Upgrade EP/AO/image while a Script is active; assert old attempt completion/cancel behavior and new attempt revision; verify mixed-version policy. |

### Diagnostics

Every event should be correlated by AO workflow/execution ID, EP WorkItem ID, claim generation, target ID, Job UID/name, image digest, and SDK revision. Report lifecycle timestamps and state transitions: accepted, assigned, Job created, Pod ready, Health accepted, Execute submitted, terminal result received, result persisted, completion notified, cleanup status. Include Kubernetes events/reason codes and bounded sanitized API errors. Do not log code, environment values, credential references where sensitive, credential values, stdout/stderr, or raw SDK credential frames. Provide operator-visible reconciliation and cleanup status, not only transient worker logs.

## 8. Dependencies, open questions, and decisions still required

### Cross-referenced work

| Work item | Boundary / dependency | Required before implementation is considered ready |
|---|---|---|
| [AAP-98873 integration design](https://redhat.atlassian.net/browse/AAP-98873) | EP Client dependency and AO↔EP command, callback, auth, result mapping, image/revision ownership | Record the client package/version and API contract; link the AO implementation PR and a verified call trace. |
| [ANSTRAT-1803 execution work](https://redhat.atlassian.net/browse/ANSTRAT-1803) | Product execution feature | Keep this document aligned with epic scope and rollout. |
| [ANSTRAT-2422 published SDK contracts](https://redhat.atlassian.net/browse/ANSTRAT-2422) | Versioned SDK ABI, manifests, credential callback contract | Pin compatible version and migration/compatibility rule. |
| [AAP-95467 SDK architecture](https://redhat.atlassian.net/browse/AAP-95467) | SDK ABI, invocation/server lifecycle | Approve one-invocation-per-Job interpretation and compatibility gate. |
| [AAP-97389 packaging/lifecycle](https://redhat.atlassian.net/browse/AAP-97389) | Image publication, signatures/digests, installation and lifecycle | Specify trusted image distribution/pull credentials and active-job upgrade behavior. |
| [AAP-98866](https://redhat.atlassian.net/browse/AAP-98866), [AAP-98867](https://redhat.atlassian.net/browse/AAP-98867) | Failure/timeout/output/cleanup implementation tests | Implement the walkthroughs in §7 against the accepted contract. |

### Epic/operator questions that remain open

The task identifies two open operator/version questions as [AAP-98864](https://redhat.atlassian.net/browse/AAP-98864) and [AAP-98871](https://redhat.atlassian.net/browse/AAP-98871). Their issue text was not accessible from this workspace, so this document deliberately does not paraphrase or answer them. Keep both open and copy their exact wording, named owner, decision, and evidence into this table when the Jira records are available. Omitting either question must not be treated as a decision.

| Tracker | Question | Owner | Decision/evidence | Implementation impact while open |
|---|---|---|---|---|
| AAP-98864 | Source wording unavailable here; retain the full question in Jira. | TBD | No decision recorded. | Blocks selecting customer-facing install/version prerequisites that depend on this answer. |
| AAP-98871 | Source wording unavailable here; retain the full question in Jira. | TBD | No decision recorded. | Blocks freezing workload/SDK compatibility and upgrade behavior that depend on this answer. |

### Other unresolved items

| Open item | Owner | Impact / release disposition |
|---|---|---|
| Confirm the invocation statement means one Execute per EP attempt; distinguish runtime server concurrency from Pod reuse. | EP + SDK architecture AAP-95467 | **Release-blocking for lifecycle and retry semantics.** |
| Confirm AO's use of the EP-provided Client, including package/version, API, authentication/retry behavior, image/revision mapping, callback, and result projection; current Syntara devel still runs Script in the Temporal worker. | AO + EP AAP-98873, coordinated with AAP-97389 | **Release-blocking for end-to-end acceptance.** |
| Implement and validate EP's per-attempt workload credential resolver; current docs mark bound workload credentials unavailable. Confirm Script itself does not expose credentials. | EP + AO credential owner + Product Security | **Release-blocking if Script or any selected plugin requires workload credentials.** |
| Approve SDK version and compatibility rollout; ADR 0011 is an in-place `v1alpha1` breaking change. | SDK + EP + packaging AAP-97389 | **Release-blocking for mixed-version deployment.** |
| Confirm the exact customer OpenShift versions, RBAC artifact, CNI support, egress policy, image pull auth and quotas. | Operator/install owner + customer admin | **Release-blocking for supported production installation.** |
| Freeze aggregate request/environment/result bounds and AO/Temporal payload handling, including output retention and redaction. | AO + EP + SDK | **Release-blocking until bounded behavior is tested.** |
| Confirm supported cancellation grace, Job TTL, cleanup SLO, and operator escalation for orphaned resources. | EP + operator | **Release-blocking for unattended operation.** |
| Confirm active-execution upgrade/drain policy and rollback image availability. | Packaging/lifecycle AAP-97389 + EP operator | **Release-blocking for supported upgrades.** |
| Confirm Product Security intake method, reviewer(s), severity rubric, and process for recording required actions. | Story owner / Product Security liaison | **Review pending; no approval claim.** |

## 9. Product Security review record

**Requested through applicable process:** No. The workspace exposes repository security-reporting guidance but not the Product Security architecture-review intake, required fields, or reviewer assignment. A repository security-vulnerability reporting channel is not assumed to be the correct design-review process. The task explicitly requires confirming the process; until the owner supplies/locates it, this is a concrete review package, not a submitted review.

**Proposed request:** “Please review `Script Step Execution Architecture and Security Boundary` for the threat boundary around user-supplied Python/Bash code, EP-to-customer-cluster RBAC and port-forward/mTLS, credential separation/callback, network egress, image trust, output/secret leakage, retry and uncertain outcomes, cancellation, cleanup, and upgrades. Please classify findings by severity and delivery impact, identify required mitigations, and state which actions block release. The document is proposed; no design decision or implementation is being represented as approved.”

| Review record | State |
|---|---|
| Intake route / tracking ID | Unknown; awaiting Product Security process confirmation |
| Date submitted / reviewer | Not submitted / none assigned |
| Disposition | Pending; no approval implied |
| Required actions | None recorded yet; must be tracked with severity and release-blocking disposition after review |
