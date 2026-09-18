# Workflow node-type permissions

## Overview

Node-type permissioning extends the ANSTRAT-1900 Rego engine with **system-scoped deny templates** per catalog node type. Users inherit **read**, **write**, and **execute** from `workflow:read`, `workflow:update`, and `execution:run` in the workflow's project until an administrator attaches an explicit **deny** built-in policy to a role.

## Adding a new node type

1. Register the type in [`node_type_catalog.json`](../../src/syntara/schemas/workflows/v2/catalog/node_type_catalog.json).
2. Built-in deny-template policies are generated at import time in [`workflow_node_type_policies.py`](../../src/syntara/authz/workflow_node_type_policies.py) — no manual Rego per type. Each template's built-in name is `{node_type}:{action}:deny` (for example `script:read:deny`).
3. Run `make -C backend test-unit` and confirm `test_node_type_permissions` policy counts include the new type (16 types × 3 actions today).
4. Wire the workflow engine / UI node registry as documented in the workflow-engine handbook.

## Enforcement surfaces

| Surface | Module |
|--------|--------|
| Policy templates | `authz/workflow_node_type_policies.py`, `authz/role_conventions.py` |
| Inheritance + deny evaluation | `authz/node_type_permissions.py` |
| API redaction / save validation | `workflows/services/workflow_service.py` |
| Advisory checks | `POST /authz/can_i` (`resource_type=workflow_node_type`), `POST /authz/can_i_node_types` |

## Design-time save rules

- **Add** or **delete** a node/trigger of type T requires both **read** and **write** on T (in addition to workflow update).
- **Read deny** redacts node bodies on GET/export. On save, unchanged read-denied nodes that remain in the definition are **restored** from the previous version so redacted stubs are never persisted; removing them requires both read and write.
- New nodes of a read-denied or write-denied type are rejected; removing either denied type is also rejected.

## Runtime execute (deferred)

Execute permission checks in the Temporal workflow engine are tracked separately from design-time delivery. See [`workflow-node-type-permissions-ac6-deferred.md`](workflow-node-type-permissions-ac6-deferred.md).
