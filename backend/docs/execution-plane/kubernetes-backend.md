# Execution Plane: Kubernetes Backend Integration

> **Stub** — this document is a placeholder. Additional backend types (OpenShell, etc.) will follow the same structure in sibling documents.

## Scope

This document will cover the `vanilla_k8s` backend type: how the EP worker schedules, monitors, and reclaims pods on a Kubernetes cluster to execute scripts.

## Topics (to be filled in)

### Pod lifecycle

- Pod template construction from `WorkItem.payload` and backend config
  (`ExecutionTarget.labels` are affinity advertisements, not a pod spec —
  see [labels.md](labels.md))
- Warm pool: pre-warming pods before work arrives, reclaiming idle pods
- Pod claim: how a `WorkItem` is bound to a running pod

### Worker group routing

- How `WorkItem` selectors are matched to `ExecutionTarget` labels
  ([ExecutionTarget Reconciler](executiontarget-reconciler.md), [labels.md](labels.md))
- Priority and affinity rules

### Failure modes

- Pod eviction during execution
- Node failure / unreachable kubelet
- Timeout handling and work item retry policy

### Configuration

- Required fields on `ExecutionTarget` for `backend_type = vanilla_k8s`
- RBAC / ServiceAccount requirements in the target cluster
