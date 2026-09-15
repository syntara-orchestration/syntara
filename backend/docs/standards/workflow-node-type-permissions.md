# Workflow node-type permissions

## Overview

Node-type permissioning extends the ANSTRAT-1900 Rego engine with **system-scoped deny templates** per catalog node type. Users inherit **read**, **write**, and **execute** from `workflow:read`, `workflow:update`, and `execution:run` in the workflow's project until an administrator attaches an explicit **deny** built-in policy to a role.

## Adding a new node type

1. Register the type in [`node_type_catalog.json`](../../src/syntara/schemas/workflows/v2/catalog/node_type_catalog.json).
2. Built-in deny-template policies are generated at import time in [`workflow_node_type_policies.py`](../../src/syntara/authz/workflow_node_type_policies.py) — no manual Rego per type.
3. Run `make -C backend test-unit` and confirm `test_node_type_permissions` policy counts include the new type (16 types × 3 actions today).
4. Wire the workflow engine / UI node registry as documented in the workflow-engine handbook.

## Enforcement surfaces

| Surface | Module |
|--------|--------|
| Policy templates | `authz/workflow_node_type_policies.py`, `authz/role_conventions.py` |
| Inheritance + deny evaluation | `authz/node_type_permissions.py` |
| API redaction / save validation | `workflows/services/workflow_service.py` |
| Advisory checks | `POST /authz/can_i` (`resource_type=workflow_node_type`), `POST /authz/can_i_node_types` |

## Runtime execute (deferred)

Execute permission checks in the Temporal workflow engine are tracked separately from design-time delivery. See [`workflow-node-type-permissions-ac6-deferred.md`](workflow-node-type-permissions-ac6-deferred.md).
