# Execution Plane: Models and API

> **Stub** — this document is a placeholder for the data model and API surface specification.

## Scope

This document will cover:

- The `execution_plane` schema: all SQLModel tables, their fields, and the relationships between them
- The public EP API (`/api/execution_plane/v1/`): endpoints, request/response shapes, and pagination conventions
- Enum value semantics (e.g. `WorkItemStatus` state machine, `TargetStatus` lifecycle)
- The OpenAPI spec location and how to regenerate it (`make -C backend api-spec-bundle-ep`)

Label fields on Cluster / ExecutionTarget, and work selectors, are specified
in [labels.md](labels.md). Matching is in the
[ExecutionTarget Reconciler](executiontarget-reconciler.md).
