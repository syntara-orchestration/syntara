# Step-level execute permissions — E2E test scenarios

Requirements-discovery suite. Product feature is **not** implemented yet; E2E cases are skipped until it lands.

**E2E module:** [`backend/tests/e2e/workflows/test_workflow_step_execute_permissions.py`](../tests/e2e/workflows/test_workflow_step_execute_permissions.py)

## Design locks (grill)

| Topic | Decision |
|-------|----------|
| Authz model | **B — runtime check:** before each step runs, evaluate `workflow_node:execute` for the **run principal** (roles/policies). No launch-time deny list signed into Temporal. |
| Divergence | Existing documentation still describes a launch-time denied-set (model A). Follow model B until docs are updated. |
| Default | Authenticated principals may execute every step kind unless a deny matches. |
| Full workflow launch | Step execute deny does **not** block launch (`workflow:execute` only). |
| Principal | Interactive Run / Run step → **invoker**. Schedule / webhook / EDA → **publisher**. |
| On deny (default) | Activity status **`DENIED`** (not failed/skipped). That branch hard-stops; parallel branches continue. Execution `COMPLETED` if another path succeeded, else `COMPLETED_WITH_ERRORS`. |
| `continue_on_failure` | When **true**, downstream on that branch **may** run after `DENIED`. When false/absent, hard-stop. |
| Run step | If the **target** step is denied for the invoker → **refuse** the request (no Temporal start, no mocked predecessors). |
| Out of scope | Soft-fail / catchable fallback, kill-switch settings page (defer), designer hide/lock for execute deny. |

Terminology: prose and comments say **step**. Authz resource type id remains `workflow_node` (engine constant).

## Grill accept / deny

| ID | Theme | Status |
|----|--------|--------|
| E1 | Default allow; label deny; project deny; isolation from `workflow:execute` | accept |
| E2 | Invoker vs publisher principal | accept |
| E3 | Sign launch-time deny list | **deny** (model B) |
| E4 | `DENIED` branch / parallel / execution status | accept |
| P0a–e | Runtime check, webhook/EDA/retry, principal plumbing, API surface, Run step refuse | accept |
| P1a–f | Join, loop, extremes, default allow, registry, CoF × DENIED | accept |
| Soft-fail / designer locks / admin permission UI | deny |
| Kill switch (AC-4) | defer |
| E2E-first for all accepted scenarios | accept |
| This scenarios doc | accept |

## E2E case map

| # | Test (method) | Scenario IDs | Expected |
|---|----------------|--------------|----------|
| 1 | `test_default_allow_runs_script_step` | E1, P1d | Authenticated user runs a script step successfully |
| 2 | `test_label_deny_marks_matching_step_denied` | E1, P0a, E4 | Deny `kind=script`+`language=python` → that step `DENIED`; activity never ran |
| 3 | `test_label_deny_does_not_block_other_kinds` | E1 | Same deny → HTTP (or bash) step still completes |
| 4 | `test_project_scoped_deny` | E1, AC-2 | Denied in project A; allowed in project B |
| 5 | `test_full_run_still_launches_when_step_denied` | E1 isolation, AC-1 | Launch succeeds; denial appears at the step |
| 6 | `test_manual_run_uses_invoker_policies` | E2, P0c | Junior invoker hits deny even if publisher would be allowed |
| 7 | `test_scheduled_run_uses_publisher_policies` | E2, P0b | Schedule evaluates publisher |
| 8 | `test_webhook_run_uses_publisher_policies` | P0b | Webhook evaluates publisher |
| 9 | `test_eda_run_uses_publisher_policies` | P0b | EDA evaluates publisher |
| 10 | `test_retry_keeps_original_run_principal` | P0b | Retry uses same principal as first run |
| 11 | `test_parallel_branch_unaffected_by_sibling_deny` | E4 | One branch `DENIED`, other completes; exec `COMPLETED`; denied steps listed |
| 12 | `test_sole_path_denied_completed_with_errors` | E4, P1c | Only path denied → `COMPLETED_WITH_ERRORS` |
| 13 | `test_join_after_denied_branch` | P1a | Join behavior when one inbound was `DENIED` |
| 14 | `test_loop_body_step_denied` | P1b | Denied step inside loop does not run the real activity |
| 15 | `test_all_steps_allowed` | P1c | Multi-step graph completes |
| 16 | `test_continue_on_failure_false_hard_stops_branch` | P1f, E4 | No CoF → no downstream after `DENIED` |
| 17 | `test_continue_on_failure_true_allows_downstream` | P1f | CoF true → downstream may run after `DENIED` |
| 18 | `test_run_step_allowed_target_succeeds` | P0e | Run step with allowed target works |
| 19 | `test_run_step_denied_target_refuses_without_mocks` | P0e | Denied target → permission error; no execution; mocks not run |
| 20 | `test_denied_status_visible_on_activity_api` | P0d | Activity list/detail shows `DENIED` + reason/policy |
| 21 | `test_resource_actions_lists_step_execute` | P1e | Registry / resource_actions includes step execute action |

## Out of scope (do not add here)

- Soft-fail / `permission_check` flow-control / catchable on-error fallback  
- Platform kill-switch Settings page (AC-4) — track separately  
- Designer palette hide / lock icons for execute deny  
- Launch-time signed deny-list tests (model A / E3)

## Implementation notes for later

- Prefer existing E2E fixtures: `workflow_factory`, `local_user_factory` / `create_user`, project roles, `api_for`, publish + schedule helpers.  
- Policy statements: `effect=deny`, `actions=["workflow_node:execute"]`, `conditions.resource_labels` for kind/language, project or system scope.  
- Until the feature ships, the E2E module is `@pytest.mark.skip` at module level with reason `step execute permissions not implemented`.
