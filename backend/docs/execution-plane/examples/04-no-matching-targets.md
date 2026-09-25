# Example: selectors match no ExecutionTarget

Builds on
[01-select-region-and-env.md](01-select-region-and-env.md).
The same two OpenShift Clusters and ExecutionTargets, but the workload
asks for a region none of them advertise. EP does **not** fall back to
a default target. The work fails.

- Ticket: [AAP-92721](https://redhat.atlassian.net/browse/AAP-92721)
- Feature: [ANSTRAT-1803](https://redhat.atlassian.net/browse/ANSTRAT-1803)
- Parent epic: [AAP-82060](https://redhat.atlassian.net/browse/AAP-82060)

## What this example is

EP still only sees the submitted WorkItem.

Work requires a Cluster labelled `region=ap-southeast-1`. The inventory
only has `us-east-1` and `eu-west-1`. Matching is exact AND against
each target's **effective labels**. See [labels.md](../labels.md) and
the [ExecutionTarget Reconciler](../executiontarget-reconciler.md).

Selectors are present, so [default routing](../executiontarget-reconciler.md#default-routing)
does **not** apply. Each Cluster still has a protected default
ExecutionTarget (`is_default: true`). Those defaults are not candidates
when selectors miss. There is no "pick the first Cluster's default"
rule. Falling back would make placement non-deterministic and could put
the work in the wrong region.

## Incoming workload

```json
{
  "selectors": {
    "region": "ap-southeast-1"
  },
  "payload": {
    "activity": {
      "image": "registry.redhat.io/ao/http-request:1.0.0",
      "params": {
        "url": "https://google.ca"
      }
    }
  }
}
```

| Field | Meaning for EP |
|---|---|
| `selectors.region` | Must match a Cluster (or target) label `region=ap-southeast-1`. No registered Cluster has that label. |
| `payload.activity.image` | Container image reference. Unused: the work never reaches a Worker Manager. |
| `payload.activity.params` | Unused for the same reason. |

## Registered Clusters and ExecutionTargets

Same inventory as [example 01](01-select-region-and-env.md).

```yaml
clusters:
  - name: ocp-us-east-1
    cluster_type: openshift
    endpoint: https://api.us-east-1.example.com:6443
    status: active
    enabled: true
    labels:
      region: us-east-1

  - name: ocp-eu-west-1
    cluster_type: openshift
    endpoint: https://api.eu-west-1.example.com:6443
    status: active
    enabled: true
    labels:
      region: eu-west-1
```

```yaml
# Illustrative keys only. Names such as endpoint, namespace, and labels
# are for readability and are not the final field design.
execution_targets:
  - name: ep-default
    cluster: ocp-us-east-1
    namespace: ao-execution
    backend_type: k8s
    is_default: true
    status: active
    enabled: true
    labels: {}

  - name: ns-production
    cluster: ocp-us-east-1
    namespace: production
    backend_type: k8s
    is_default: false
    status: active
    enabled: true
    labels:
      env: production

  - name: ep-default
    cluster: ocp-eu-west-1
    namespace: ao-execution
    backend_type: k8s
    is_default: true
    status: active
    enabled: true
    labels: {}
```

Effective labels (Cluster ∪ ExecutionTarget):

| Target | Effective labels | Matches `{region: ap-southeast-1}`? |
|---|---|---|
| `ocp-us-east-1` / `ep-default` | `{region: us-east-1}` | no (wrong `region`) |
| `ocp-us-east-1` / `ns-production` | `{region: us-east-1, env: production}` | no (wrong `region`) |
| `ocp-eu-west-1` / `ep-default` | `{region: eu-west-1}` | no (wrong `region`) |

Every target is `SELECTOR_MISMATCH`. Extra labels (`env`) do not help.
`is_default` is not consulted.

## What EP does

1. **Reconcile.** Selectors are non-empty, so default routing is
   skipped. No ExecutionTarget satisfies `region=ap-southeast-1`.
   Outcome: `NO_MATCHING_TARGETS`, eligible set `{}`.
2. **Fail.** The Work Scheduler reads `outcome` and the ineligibility
   reasons. None is `CAPACITY_EXHAUSTED` (scaling would not create that
   region). The scheduler **fails** the work as unschedulable. It does
   not dispatch to a Worker Manager. It does not pick `ep-default` on
   `ocp-us-east-1` or `ocp-eu-west-1`.

```text
WorkItem
  selectors.region=ap-southeast-1  →  no target
  payload.activity.image           →  unused
  payload.activity.params          →  unused
```

`resolve()` does not raise. No-match is an outcome, not an exception.
The scheduler turns that outcome into the error.

This is the same rule as a miss on `env` in example 01: required
selectors that no target carries leave the work unschedulable. That is
intended.

## Out of scope here

| Omitted | Why |
|---|---|
| Empty selectors / default routing | [Example 00](00-one-workload-default-target.md) |
| Selectors that match | [Example 01](01-select-region-and-env.md) |
| Volume mount | [Example 02](02-volume-mount.md) |
| OpenShell sandbox policy | [Example 03](03-openshell-sandbox-policy.md) |
| Re-queue on `CAPACITY_EXHAUSTED` | Resource Monitor ([AAP-92724](https://redhat.atlassian.net/browse/AAP-92724)); not this miss |
| Retry with empty selectors after claim failure | Work Scheduler ([AAP-92722](https://redhat.atlassian.net/browse/AAP-92722)) |
| AO workflow / node / Execution Profile rows | Not visible to EP |
