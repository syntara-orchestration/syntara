# ANSTRAT-2372 Progress Map

This map connects the Terraform Enterprise feature tickets to the current code implementation.

## Implemented

| Ticket | Implemented scope | Evidence |
| --- | --- | --- |
| AAP-94700 | TFE integration, credential resolution, health check, TLS/SSRF controls | `backend/src/syntara/workflows/workflow_engine/activities/integration_resolution_activity.py:28`, `backend/src/syntara/workflows/workflow_engine/activities/credential_resolution_activity.py:34`, `backend/src/syntara/integrations/adapters/tfe.py:41` |
| AAP-94701 | 28 native TFE step contracts and dispatch | `backend/src/syntara/terraform/step_bindings.py:28`, `backend/src/syntara/workflows/workflow_engine/models/workflow_definition.py:142` |
| AAP-94702 | Project-scoped credentials, SSRF validation, TLS handling, and redaction | `backend/src/syntara/workflows/workflow_engine/activities/integration_resolution_activity.py:59`, `backend/src/syntara/workflows/workflow_engine/activities/credential_resolution_activity.py:77` |
| AAP-95881 | Generated contracts include TFE step types | PR 789 is merged and green |
| AAP-94694 | Workspace create/list/update/delete, state outputs, GitHub installations, and VCS linking | `backend/src/syntara/terraform/client.py:250`, `backend/src/syntara/terraform/step_bindings.py:29` |
| AAP-94695 | Variable add/list/update/delete | `backend/src/syntara/terraform/client.py:327`, `backend/src/syntara/workflows/workflow_engine/models/tfe_types.py:145` |
| AAP-94696 | Configuration-version upload | `backend/src/syntara/terraform/client.py:354` |
| AAP-94697 | Run trigger/status/apply/discard/cancel/force-cancel/list/comment | `backend/src/syntara/terraform/client.py:418`, `backend/src/syntara/workflows/workflow_engine/models/tfe_types.py:293` |
| AAP-94698 | Project CRUD, move workspace, and assign team permissions | `backend/src/syntara/terraform/client.py:517` |
| AAP-94742 | Essential TFE telemetry events | `backend/src/syntara/terraform/telemetry.py:17` |
| AAP-95477 | SDK bridge and manifest mapping for all 28 TFE node types | `backend/docs/tfe-sdk-bridge.md:27`, `backend/src/syntara/terraform/step_executor.py:55` |

## Partially implemented

| Ticket | Implemented | Remaining gap |
| --- | --- | --- |
| AAP-94700 | Per-step integration and credential selection work | Workflow-level integration/credential inheritance is not evident |
| AAP-94703 | Four workspace presets are implemented | Preset precedence, effective-value display, override preservation, and context-change handling are incomplete |
| AAP-94720 | Update Variable preserves omitted fields | Intentional empty-value distinction is missing |
| AAP-94725 | All seven run modes are supported | `auto_apply` is not independent of `plan-and-apply` |
| AAP-94731 | List Runs fetches all pages | Explicit completeness/truncation metadata is not exposed |
| AAP-95477 | SDK bridge maps all 28 node types | Production SDK execution is not enabled by default |
| ANSTRAT-2422 | SDK architecture work exists | SDP review is needed to explicitly incorporate the SDK approach |

## Missing

| Ticket | Missing scope |
| --- | --- |
| AAP-94733 | Direct TFE run diagnostics links |
| AAP-94741 | TFE-specific audit records |
| AAP-94743 | Dedicated TFE end-to-end validation |
| AAP-94744 | Security and performance readiness reviews |
| AAP-94745 | Validated operational guidance |

## Summary

The core Terraform Enterprise execution surface is implemented: 28 native step types cover workspaces, variables, configuration upload, run lifecycle, GitHub/VCS linking, and projects. Integration resolution, credential resolution, SSRF/TLS controls, error redaction, timeouts, and essential telemetry are in place.

Remaining work is mostly hardening and alignment:

- Workflow-level integration inheritance
- Shared preset precedence and effective-value display
- Variable update empty-value semantics
- Run diagnostics links
- List completeness metadata
- TFE-specific audit
- End-to-end validation
- Security and performance readiness
- Operational guidance
- ANSTRAT-2422 SDP review for the SDK approach
