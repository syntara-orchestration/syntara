# **Workflow Automation — Step-Type Execution Permissions (ANSTRAT-1750)**

***Status:** Draft. Verified against design explainer [ansible/handbook \#1710](https://github.com/ansible/handbook/pull/1710) head 3a440b77 and [ANSTRAT-1750](https://redhat.atlassian.net/browse/ANSTRAT-1750) on 2026-09-27. The Jira Acceptance Criteria still describe a **runtime \`DENIED\` step** (AC-1/AC-3); the handbook MD (§10 **D-1**, §11) supersedes that with **fail-fast at launch**. This plan follows the MD. Entry criteria (Jira AC rewrite \+ design sign-off) are **not met**.*

## **Overview**

* **Feature Pod:** Automation Orchestrator  
* **Components Touched:** Automation Orchestration — backend (authz deny eligibility, launch-time workflow\_node:execute checks, WorkflowVersion.published\_by, OpenAPI/error contract, audit), frontend (syntara-ui Run/Test UX for 403 denial, run-list FAILED reason for triggered fires)  
* **Delivery Stage:** Refinement (ANSTRAT-1750 status; design PR open; feature branch feat/ANSTRAT-1750-node-permissions implements an older, broader design and must be realigned — handbook §12)  
* **Status:** Draft — test plan only; SDP not yet authored; Jira ACs diverge from design MD

## **Related information**

* Feature: [ANSTRAT-1750](https://redhat.atlassian.net/browse/ANSTRAT-1750) — Workflow Automation \- Policy and Governance (Step Type Permissioning)  
* Parent outcome: [ANSTRAT-2291](https://redhat.atlassian.net/browse/ANSTRAT-2291)  
* Design explainer: [ansible/handbook \#1710](https://github.com/ansible/handbook/pull/1710) — …/AO/ANSTRAT-1750-node-permissions-explainer.md (and older HTML Facts doc in the same PR — **superseded** by the MD for scope)  
* GA baseline: [ANSTRAT-1900](https://redhat.atlassian.net/browse/ANSTRAT-1900) — RBAC & Policy Integration  
* Policy UI (not tested here): [ANSTRAT-2282](https://redhat.atlassian.net/browse/ANSTRAT-2282) — Custom Policies UI Authoring  
* Deny-effect history: AAP-74620 (deny re-enabled for workflow\_node only)  
* Feature branch (pre-D-1 shape): feat/ANSTRAT-1750-node-permissions @ e43b5f85e — must drop runtime DENIED, kill switch, write/introduce, attributes, mcp\_tool, etc. (handbook §12)

## **Requirements**

Traceability to design MD requirements (R-1–R-12) and decisions (D-1–D-6). Every requirement below must map to at least one test case in **Tests**.

***Terminology:** handbook MD says \*step\* / \*step type\*; code uses workflow\_node and NodeType / kind. Equivalent. This plan uses \*step type\* in prose and kind in assertions.*

| Design Req | Summary | Test Scenario(s) |
| :---- | :---- | :---- |
| R-1 | Only action is workflow\_node:execute (no read/write on step types) | TS-01, TS-05 |
| R-2 | Match via conditions.resource\_labels.kind only; no per-instance UUID; no per-attribute (model/language/…) | TS-01, TS-05, TS-09 |
| R-3 | Default allow: builtin workflow\_node:execute on authenticated (users \+ service accounts) | TS-00, TS-01 |
| R-4 | Custom deny allowed only for workflow\_node (AAP-74620) | TS-05 |
| R-5 | Project-scoped (scope: project \+ assignment in project) or system-wide (scope: any) | TS-03 |
| R-6 | Interactive (Run/Test) → invoker; schedule/webhook/EDA → publisher (published\_by, fallback created\_by); fresh at each launch | TS-02, TS-04 |
| R-7 / D-1 | Fail fast at launch — no Temporal start; no runtime step check; no DENIED activity status | TS-02, TS-04, TS-08 |
| R-8 | Denial visible: step type(s), step id(s), principal, denying policy | TS-02, TS-04, TS-06 |
| Audit (stakeholder 2026-09-27/28) | Launch-time step-permission check emits one audit event per launch on deny and on allow; deny payload lists all denied nodes present in that workflow (not one event per kind) | TS-06 |
| R-9 | Authoring unaffected by execute denies (palette/canvas fully editable) | TS-07 |
| R-10 | Policies via existing policy/role APIs (UI authoring out of test scope) | TS-05 |
| R-11 | Handbook docs — out of test scope (docs-owned) | — |
| R-12 | Perf: launch-check latency, scale (users/policies/nodes), concurrent checks | TS-12 |
| D-2 | No platform kill switch / step-type enable-disable | TS-09 (negative / out-of-scope confirmation) |
| D-3 | No mcp\_tool step type in this feature | TS-09 |
| D-4 | No per-attribute matching | TS-09 |
| D-5 | Custom policy UI (ANSTRAT-2282) — not tested in this plan | — |
| Action kinds deniable | aap\_job\_template, aap\_workflow\_job\_template, agentic, approval, http\_request, internal\_activity, script | TS-01 (matrix) |
| Trigger/flow never deniable | Triggers \+ condition/converge/loop/switch/wait → policy save 422 | TS-05 |
| Launch gate order | execution:run first, then per distinct action kind workflow\_node:execute | TS-02, TS-08 |
| Whole-definition scan | Every action step in the saved version is checked — not only the branch that would run | TS-02 (TC0028) |
| No mid-run re-check | Deny added during approval/wait does not affect in-flight run; next launch sees it | TS-02 (TC0029) |

### **Jira AC mapping (after expected Jira rewrite)**

| Jira AC (current text) | Design outcome to test | Notes |
| :---- | :---- | :---- |
| AC-1 | Fail-fast refusal \+ visibility (R-7/R-8); authorized user succeeds | Rewrite required: drop “launches then DENIED” |
| AC-2 | Project A denied / Project B allowed; system-wide via scope: any | Rewrite: \* → any |
| AC-3 | Publisher vs invoker; fresh evaluation | Rewrite: triggered → FAILED record, not runtime DENIED |
| AC-4 | Policy authoring shape \+ deny eligibility | API only (UI/2282 not tested) |
| AC-5 | Designer unaffected | Aligns with R-9 |
| AC-6 | Handbook | Out of test scope |

## **Objective**

Validate that administrators can deny workflow\_node:execute for specific **action** step types (by kind label), system-wide or per project, using ordinary policies; that launch-time evaluation uses the correct principal (invoker vs publisher); that a denial **refuses the launch** (interactive **403** with no execution; triggered **FAILED** execution record never sent to Temporal); that authoring remains unrestricted by execute policies; and that triggers/flow-control kinds cannot be denied. Confirm default-allow upgrade safety, deny-eligibility lockout protection, and no regression to existing workflow execution when no deny applies.

## **Risks**

* **Source-of-truth drift** — Jira ACs, Google-doc draft, HTML Facts (F-18/F-19 runtime DENIED), and feature branch still describe runtime denial; MD (D-1) fail-fast is the intended product behavior. Testing the wrong shape wastes automation.  
* **Half-started executions** — if fail-fast is incomplete on one launch path (e.g. schedule), Temporal may start work the principal must not run.  
* **Wrong principal on triggers** — evaluating webhook/EDA caller or scheduler instead of publisher bypasses governance.  
* **Stale principal / missing \`published\_by\`** — pre-migration versions fallback to created\_by; deactivated publisher fails every fire until republish (expected) — must be clear in UX/ops.  
* **Untaken-branch false deny** — checking the whole definition means a denied kind on an untaken conditional branch still blocks launch (by design); operators may misread as a bug.  
* **Deny on \`authenticated\`** — platform-wide lockout of a step type including admins; recoverable only via policy delete / assignment revoke.  
* **US\#2 “allow here, deny everywhere else”** — not a single rule; multi-assignment operational gap.  
* **Error field names unfinished** (MD §9) — problem-details shape may still move; audit **must** emit on both allow and deny (decided 2026-09-27).  
* **Feature-branch cleanup** — leftover DENIED status, kill switch, write/introduce, palette gating can confuse E2E if not removed (§12).  
* **Scale / cold-cache authz** — launch checks under many users, teams, role assignments, and large graphs may regress R-12 if not measured.

## **Testing Approach**

* **Levels:** backend unit (pytest authz \+ launch checks), backend integration (policy CRUD \+ launch), backend E2E (interactive \+ each trigger path), frontend unit (403/FAILED messaging), frontend E2E (Playwright Run/Test \+ Runs list), ATF for cross-component/platform flows; performance/scale fixtures (TS-12).  
* **Methods:** requirement-driven P/N/E cases; **step-type coverage matrix** (all deniable kinds × happy/deny); **trigger matrix** (manual, schedule, webhook, EDA × publisher allowed/denied); principal-swap tests; project-scope isolation; deny-eligibility lockout; whole-definition vs branch coverage; upgrade/default-allow regression.

## **Testing Requirements by Delivery Stage**

| Stage | Requirement |
| :---- | :---- |
| Refinement | Test plan authored; R-1–R-12 \+ D-1–D-6 traceability; Jira ACs updated to D-1 or explicitly waived; environments identified |
| In Progress | Unit \+ integration with each PR; launch-path matrix green; feature branch aligned to MD §12 |
| Code complete | Full E2E \+ ATF; UI 403/FAILED messaging; TS-12 scale suite measured |
| Release pending | Exit criteria; upgrade/default-allow validated; no open Critical/Major |

## **Quality Focus Area Coverage**

| Quality Focus Area | Applies | Rationale | What Will Be Tested | Test Names |
| :---- | :---- | :---- | :---- | :---- |
| API | Yes | Launch refusal contract \+ policy validation are the surface | Interactive 403 body; triggered FAILED record fields; policy 422s; can\_i / who\_can | TS-02, TS-04, TS-05, TS-06 |
| UI | Yes | Operators must understand why Run/Test failed; Runs list for triggered FAILED | Run/Test error UX; Runs list reason; designer unaffected | TS-07, TS-10 |
| Data / persistence | Yes | published\_by \+ fallback; no execution on interactive 403; FAILED record on triggers | Migration, fallback, record presence/absence | TS-04, TS-08 |
| Observability | Yes | Audit required on allow and deny; FAILED reason must be queryable | Audit events (success \+ failure); structured denial fields | TS-06 |
| Security / RBAC | Yes | Core feature is authZ | Deny eligibility, admin-included denies, principal correctness, workflow-level gate still first | TS-05, TS-08 |
| Upgrade / backward-compat | Yes | Default allow must not break existing runs | Builtin policy seed; legacy versions without published\_by | TS-00, TS-04 |
| Performance / scale | Yes | R-12 \+ stakeholder scale scenarios | Launch latency vs node count; many users/teams/policies; concurrent launches; audit write overhead | TS-12 |

## **Test Environment**

* Full stack (podman-compose / deployed AAO): API, Temporal \+ worker, PostgreSQL (main \+ audit), Redis, frontend.  
* Multi-principal fixtures: admin, restricted operator, publisher user, invoker user, service account, deactivated publisher.  
* Two projects (A/B) for scope tests; ability to assign roles with/without project\_id.  
* Trigger harness: schedule fire, webhook POST, EDA event (or test doubles used by existing E2E).  
* Policy authoring via API only (policy UI / ANSTRAT-2282 not in test scope).  
* Upgrade fixture: DB with pre-feature workflow versions (no published\_by).  
* Scale fixtures for TS-12: large user/team DB, large workflow graphs, and **many projects** each with its own project-scoped step-type deny (denies per project stay few; project count is the scale axis).

## **Test Data Requirements**

### **Step-type catalog (from NodeType on devel)**

| Category | kind | Deny execute? | Happy-path fixture | Negative / alternative |
| :---- | :---- | :---- | :---- | :---- |
| Action | aap\_job\_template | Yes | Workflow with JT step completes for allowed principal | Deny → interactive 403 / triggered FAILED |
| Action | aap\_workflow\_job\_template | Yes | Same | Same |
| Action | agentic | Yes | Same | Same; not model-specific (“NO MYTHOS”) — out of scope |
| Action | approval | Yes | Approval path completes when allowed | Deny blocks launch even if approval never reached |
| Action | http\_request | Yes | Same | Same |
| Action | internal\_activity | Yes | Same | Same |
| Action | script | Yes | Same (\*shell\* in customer language \= script) | Deny; typo shell → policy 422 |
| Trigger | manual\_trigger | No | Launch via Run | Policy deny of execute → 422 at save |
| Trigger | scheduled\_trigger | No | Schedule fire | Policy deny → 422; publisher deny of \*action\* kinds → FAILED record |
| Trigger | webhook\_trigger | No | Webhook fire | Same pattern |
| Trigger | eda\_trigger | No | EDA fire | Same pattern |
| Flow | condition | No | Branching workflow | Policy deny → 422 |
| Flow | converge | No | Parallel \+ join | Policy deny → 422 |
| Flow | loop | No | Loop body with allowed action | Policy deny → 422 |
| Flow | switch | No | Switch workflow | Policy deny → 422 |
| Flow | wait | No | Wait then action | Policy deny → 422 |

### **Launch / principal fixtures**

* Workflows: linear all-action kinds; conditional with denied kind only on untaken branch; parallel with denied kind on one branch; mix of trigger \+ flow \+ one denied action.  
* Principals: invoker-allowed / invoker-denied; publisher-allowed / publisher-denied; invoker allowed but publisher denied (and reverse) for trigger tests.  
* Policies: project-scoped deny on script in Project A; system-wide scope: any deny on agentic; deny assigned to authenticated; deny on non-workflow\_node (must 422).

## **Security Testing**

* Deny-effect cannot target policy, role, role-assignment, user, or other non-allowlisted types (R-4 / AAP-74620).  
* Project admin can create project-scoped workflow\_node deny with plain policy:create (no policy:create-deny).  
* Deny on role assigned to authenticated applies to admins; recovery via policy delete / assignment revoke still works.  
* Interactive 403 does not leak cross-tenant policy/principal details.  
* Triggered FAILED record does not run activities (no side effects) for denied kinds.  
* execution:run remains required; step-type allow does not bypass workflow-level deny.  
* Service accounts resolve through authenticated default allow (R-3 / F-22 kept).

## **Backward Compatibility and Feature Flags**

* Pre-existing workflows with no step-type denies launch and complete unchanged (R-3).  
* Builtin workflow\_node:execute on authenticated seeded on upgrade; no data migration of definitions required.  
* Versions without published\_by use created\_by fallback for publisher resolution.  
* No kill switch / no new step types shipped (D-2, D-3).  
* Feature flag (if any): confirm with implementers — MD does not define one.  
* Old clients: additive error fields must not break; interactive path changes from “start then fail” (old branch) to 403 — document as intentional breaking change vs older prototype.

## **Scope**

### **In Scope**

* workflow\_node:execute deny/allow for all **action** step types (matrix).  
* Launch-time fail-fast: interactive 403 (no execution); schedule/webhook/EDA FAILED record (not sent to Temporal).  
* Principal resolution: invoker vs publisher; fresh policy evaluation; published\_by \+ created\_by fallback; deactivated publisher.  
* Project vs system scope; default allow; deny eligibility; unknown/shell/trigger/flow kind validation (422).  
* Whole-definition kind collection (including untaken branches).  
* Authoring unaffected (R-9).  
* Visibility of denial (R-8) once error contract is fixed.  
* Regression when no deny applies.  
* Performance and scale (R-12 / TS-12).

### **Out Of Scope**

* Runtime DENIED activity status, branch continuation, denied\_nodes, mid-run re-check (removed by D-1 / §10).  
* Soft error / permission\_check node (future RFE; US\#4).  
* Palette/canvas gating from execute permissions; read/write on step types; kill switch / step-type disable (D-2).  
* Per-attribute matching (model/language/method) (D-4); per-instance UUID permissions.  
* mcp\_tool step type (D-3).  
* Custom policy UI (ANSTRAT-2282) — **not tested**.  
* Handbook documentation (R-11 / AC-6) — **not tested**.  
* Dry-run “can this workflow run?” productized UX (operators may use can\_i manually).  
* External secrets, rate limiting, and other sibling features.

## **Entry Criteria**

* Design MD in handbook \#1710 reviewed; Jira AC-1/AC-2/AC-3 rewritten to match D-1 (or explicit waiver recorded) — **currently NOT met**.  
* Feature branch realigned to MD §12 (fail-fast; remove runtime DENIED / kill switch / write / attributes / mcp\_tool).  
* Audit emission on allow and deny implemented; 403 \+ FAILED field names agreed or marked provisional in tests.  
* Test environment with multi-role users, two projects, all four trigger paths, and TS-12 scale fixtures.

## **Exit Criteria**

* 100% of in-scope R/D items mapped to executed cases; all P1 passing (R-11 handbook and D-5/2282 UI explicitly out of scope).  
* Action step-type matrix: each deniable kind has happy \+ deny coverage on at least one interactive and one triggered path (triggered may share parameterization).  
* Trigger matrix: schedule, webhook, EDA each covered for publisher allowed/denied.  
* No Temporal start / no side effects when denied.  
* Authoring unaffected proven for a user with execute denies.  
* Deny-eligibility lockout suite green.  
* TS-12 scale cases measured and within agreed budgets (or documented deferral with numbers).  
* No open Critical/Major; Sev-1/2 automated.

## **Platform User-flow Tests**

* **UF1 — Deny script to junior operators (interactive):** admin creates project-scoped deny on script for junior-operator role → junior clicks Run on workflow containing script → **403**, no execution, UI lists kind \+ policy → senior with no deny runs same workflow successfully. \[P1\]  
* **UF2 — Scheduled job after publisher loses access:** publisher publishes workflow with agentic → schedule works → admin assigns system-wide deny of agentic to publisher’s group → next fire creates **FAILED** execution (not Temporal), reason names publisher \+ kind → republish by allowed user restores fires. \[P1\]  
* **UF3 — Author still designs, cannot run:** user with workflow:update but denied http\_request execute adds/edits HTTP steps freely → Run returns 403 → uses can\_i / admin to remediate. \[P1\]  
* **UF4 — Webhook/EDA same publisher semantics:** webhook and EDA fires evaluate publisher, not the external caller. \[P1\]

## **Trigger × principal matrix (what happens)**

| Launch path | Run principal | Allowed for all action kinds in definition | Denied for ≥1 action kind in definition |
| :---- | :---- | :---- | :---- |
| Run (UI/API) | Invoker | Execution starts; completes per normal engine rules | 403; no Execution row; response lists denied kinds, step ids, denying policy |
| Test (incl. single-step test) | Invoker | Same as Run | Same as Run (403) |
| scheduled\_trigger fire | Publisher (published\_by → else created\_by) | Execution starts | FAILED Execution created; not sent to Temporal; reason lists kinds, step ids, publisher, policy |
| webhook\_trigger fire | Publisher | Execution starts | FAILED record (same shape) |
| eda\_trigger fire | Publisher | Execution starts | FAILED record (same shape) |

**Combinations to exercise explicitly:**

| \# | Invoker | Publisher | Interactive Run | Triggered fire |
| :---- | :---- | :---- | :---- | :---- |
| C1 | allowed | allowed | OK | OK |
| C2 | denied | allowed | 403 | OK |
| C3 | allowed | denied | OK | FAILED |
| C4 | denied | denied | 403 | FAILED |
| C5 | n/a | deactivated | — | clear failure until republish |
| C6 | allowed | allowed; policy added after publish, before fire | OK at publish time N/A | next fire FAILED (fresh eval) |
| C7 | allowed mid-run; deny added during approval wait | — | in-flight continues; next Run 403 | — |

## **Tests**

*Legend: **P** positive, **N** negative, **E** edge/boundary. Priority: **\[P1\]** must-pass · **\[P2\]** release-pending depth · **\[P3\]** characterization.*

### **TS-00 — Regression / default allow (R-3, R-1)**

* TC0001 (P) \[P1\]: After upgrade / on clean seed, authenticated user with execution:run launches a multi-step workflow containing every action kind → completes; no step-permission errors.  
* TC0002 (P) \[P1\]: Service account publisher path: scheduled workflow with action steps completes under default allow.  
* TC0003 (P) \[P1\]: Existing workflow-level deny of execution:run still blocks launch before any step-type check.  
* TC0004 (E) \[P2\]: Custom role with no explicit workflow\_node:execute still allowed via authenticated builtin (unless deny matches).  
* TC0005 (E) \[P1\]: No workflow\_node:write / read actions appear as required permissions for authoring or launch.

### **TS-01 — Action step-type matrix (R-1, R-2, R-7)**

For **each** deniable kind K ∈ {aap\_job\_template, aap\_workflow\_job\_template, agentic, approval, http\_request, internal\_activity, script}:

* TC0100+K (P) \[P1\]: Linear workflow containing K; principal allowed → Run completes; K activity runs.  
* TC0110+K (N) \[P1\]: Deny workflow\_node:execute where kind=K assigned to invoker → Run → **403**, no execution, K listed.  
* TC0120+K (N) \[P2\]: Same deny → schedule/webhook/EDA fire → **FAILED** record, K listed, no Temporal / no side effects.

\*(Parameterize rather than explode IDs in TestLink; ensure all seven kinds appear in automation data.)\*

* TC0130 (E) \[P1\]: Workflow with **multiple** denied kinds → response/record lists **all** denied kinds (not only the first).  
* TC0131 (E) \[P2\]: Workflow with many instances of same kind → one evaluation; single deny blocks launch.  
* TC0132 (N) \[P1\]: Policy with kind: shell → **422** (unknown kind); use script for shell use case.  
* TC0133 (N) \[P2\]: Policy with unknown kind foo\_bar → **422**.

### **TS-02 — Interactive launch fail-fast (R-6, R-7, R-8)**

* TC0020 (P) \[P1\]: Run with full permissions → 2xx \+ execution COMPLETED (or normal terminal).  
* TC0021 (N) \[P1\]: Run with denied kind → **403**; assert **no** execution id created.  
* TC0022 (N) \[P1\]: Test-run / single-step test with denied kind → **403**; no execution.  
* TC0023 (P) \[P1\]: Same workflow, allowed user → succeeds (AC-1 authorized path).  
* TC0024 (E) \[P1\]: Response body includes denied step type(s), step id(s), denying policy id/name (\*fields provisional — MD §9\*).  
* TC0025 (E) \[P2\]: User has execution:run but denied step type → still 403 (step check after workflow gate).  
* TC0026 (N) \[P1\]: User lacks execution:run → existing authZ failure; step-type detail not required.  
* TC0027 (E) \[P2\]: Policy changed between page load and Run → fresh eval on Run (no cache from publish).  
* TC0028 (E) \[P1\]: Conditional workflow; denied kind only on **untaken** branch → launch still **403** (whole-definition scan).  
* TC0029 (E) \[P1\]: Execution in approval/wait; admin adds deny for upcoming kind → **in-flight continues**; subsequent Run → 403\.  
* TC0030 (E) \[P2\]: Parallel definition with denied kind on one branch → 403 before any branch runs (no partial side effects).

### **TS-03 — Project vs system scope (R-5, AC-2)**

* TC0031 (P) \[P1\]: Project-scoped deny script in Project A → Run in A → 403; identical workflow in Project B → OK.  
* TC0032 (P) \[P1\]: System-wide deny (scope: any) on agentic → 403/FAILED in every project for assignees.  
* TC0033 (N) \[P2\]: Project-scoped statement assigned **without** project → rejected or non-matching per existing resolver rules (characterize).  
* TC0034 (E) \[P2\]: Documented limitation: “allow in one project, deny everywhere else” requires per-other-project assignments — characterize multi-assignment approach (not a single-rule feature).  
* TC0035 (N) \[P1\]: System-wide is **not** authored as scope: "\*" — invalid scope → 422; valid is any.

### **TS-04 — Triggered launch & publisher principal (R-6, R-7, R-8)**

* TC0040 (P) \[P1\]: Schedule fire, publisher allowed → execution COMPLETED.  
* TC0041 (N) \[P1\]: Schedule fire, publisher denied kind → **FAILED** execution; not in Temporal; reason complete.  
* TC0042 (P) \[P1\]: Webhook fire, publisher allowed → OK.  
* TC0043 (N) \[P1\]: Webhook fire, publisher denied → FAILED record; **caller identity irrelevant**.  
* TC0044 (P) \[P1\]: EDA fire, publisher allowed → OK.  
* TC0045 (N) \[P1\]: EDA fire, publisher denied → FAILED record; caller irrelevant.  
* TC0046 (E) \[P1\]: Combination C2 (invoker denied, publisher allowed): interactive 403; schedule OK.  
* TC0047 (E) \[P1\]: Combination C3 (invoker allowed, publisher denied): interactive OK; schedule FAILED.  
* TC0048 (E) \[P1\]: Policy added after publish → next fire FAILED without republish (fresh eval).  
* TC0049 (E) \[P1\]: Version lacking published\_by → fallback created\_by used as publisher.  
* TC0050 (E) \[P1\]: Deactivated publisher → fires fail with clear reason until republish by active allowed user.  
* TC0051 (E) \[P2\]: Republish by allowed user updates published\_by → subsequent fires OK.

### **TS-05 — Policy authoring & deny eligibility (R-4, R-10, trigger/flow rules)**

* TC0060 (P) \[P1\]: Create deny policy workflow\_node \+ execute \+ kind: script via API → 201\.  
* TC0061 (P) \[P1\]: Attach to role; assign to user/group; launch behavior matches TS-02/TS-04.  
* TC0062 (N) \[P1\]: Deny effect on policy / role / role-assignment → **422**.  
* TC0063 (N) \[P1\]: Deny execute on each trigger kind → **422**.  
* TC0064 (N) \[P1\]: Deny execute on each flow-control kind → **422**.  
* TC0065 (P) \[P2\]: Project admin with policy:create at project scope authors project-scoped node deny (no special create-deny action).  
* TC0066 (E) \[P1\]: Deny assigned to authenticated → admins also blocked for that kind; admin can still delete policy / revoke assignment.  
* TC0067 (P) \[P2\]: POST /authz/can\_i and who\_can reflect execute deny for a kind (+ project).  
* TC0068 (N) \[P2\]: Allow statement without matching deny → default path; explicit allow not required for Project B when only A is denied.

### **TS-06 — Visibility, errors, audit (R-8; audit decided 2026-09-27/28)**

***Decision:** every launch-time step-permission evaluation emits **exactly one audit event per launch attempt** — on **deny (fail)** and on **allow (succeed)**. On deny, that single event lists **all denied nodes** (step ids \+ kinds) present in the workflow definition that failed the check — not one audit per kind. Interactive 403 and triggered FAILED both count as deny outcomes.*

* TC0070 (P) \[P1\]: Interactive 403 problem-details includes kinds, step ids, policy reference.  
* TC0071 (P) \[P1\]: Triggered FAILED execution reason/fields include kinds, step ids, publisher principal, policy.  
* TC0072 (P) \[P1\]: Interactive **deny** (403) → **one** audit event (principal, outcome=denied, **list of all denied nodes** in the workflow, denying policy/policies).  
* TC0073 (P) \[P1\]: Interactive **allow** (Run succeeds past step checks) → **one** audit event (principal, kinds checked, outcome=allowed).  
* TC0074 (P) \[P1\]: Triggered **deny** (FAILED record) → **one** audit event (publisher principal, outcome=denied, **full denied-node list**, policy/policies).  
* TC0075 (P) \[P1\]: Triggered **allow** (schedule/webhook/EDA starts) → **one** audit event (publisher, kinds, outcome=allowed).  
* TC0076 (E) \[P2\]: No secrets/tokens in denial error or audit payloads.  
* TC0077 (N) \[P2\]: Cross-tenant: user cannot observe another tenant’s denying policy details via error.  
* TC0078 (E) \[P1\]: Workflow with **N\>1 denied kinds/nodes** → still **exactly one** audit; payload lists every denied node present in that workflow (no per-kind fan-out; no double-emit).

### **TS-07 — Designer / authoring unaffected (R-9, AC-5)**

* TC0080 (P) \[P1\]: User denied script execute still sees script in palette; can add/edit/remove/save/publish.  
* TC0081 (P) \[P1\]: No badges/locks/warnings in designer from execute permissions (per Jira UX).  
* TC0082 (P) \[P1\]: Clone/import/template of workflow containing denied-for-user kinds still allowed (authoring).  
* TC0083 (N) \[P1\]: Execute deny alone never returns save-time 403 (NODE\_KIND\_WRITE\_DENIED must not exist post-§12 cleanup).

### **TS-08 — Launch pipeline & no engine involvement (R-7, D-1)**

* TC0090 (P) \[P1\]: On denial, Temporal workflow/activity count for that launch is zero.  
* TC0091 (P) \[P1\]: Denied script/http\_request/aap\_\* produce **no** external side effects (no shell, HTTP, AAP job).  
* TC0092 (P) \[P1\]: Engine has no runtime permission activity / no ActivityStatus.denied in shipped design.  
* TC0093 (P) \[P1\]: Gate order: missing execution:run fails without enumerating step denies; with execution:run \+ step deny → step denial error.  
* TC0094 (E) \[P2\]: Distinct-kind dedupe: 50-node workflow with 3 action kinds → ≤3 authorize calls (observable via metrics/logs if exposed).

### **TS-09 — Explicit non-goals / removed scope (D-2–D-4, D-3)**

* TC0100 (N) \[P1\]: No settings page / API to platform-disable a step type as part of ANSTRAT-1750 (D-2) — absence test / no regression to removed APIs.  
* TC0101 (N) \[P1\]: Policy matching kind: agentic \+ model: mythos is **not** supported — extra labels ignored or rejected per implementation; cannot express NO-MYTHOS without denying all agentic (D-4).  
* TC0102 (N) \[P2\]: No mcp\_tool kind on devel delivery of this feature (D-3).  
* TC0103 (N) \[P1\]: No permission\_check node in catalog.  
* TC0104 (N) \[P2\]: Per-step UUID conditions rejected / ignored (out of scope).

### **TS-10 — UI (R-8, R-9)**

*Policy authoring UI (ANSTRAT-2282) is **out of scope** for this plan. Policies are created via API in all cases.*

* TC0110 (P) \[P1\]: Run/Test shows actionable error when 403 from step-type deny (kinds visible; not a generic failure).  
* TC0111 (P) \[P1\]: Runs list/detail shows FAILED triggered executions with denial reason.  
* TC0112 (P) \[P2\]: Designer flows from TS-07 covered in Playwright.  
* TC0113 (E) \[P3\]: a11y of error alert (not color-only).

### **TS-12 — Performance & scale (R-12) \- Out of scope for the prototype**

*Targets use GA carry-forward where stated (≤50 ms standard / ≤100 ms with policy injection; 500 concurrent checks/s). Scale fixture sizes below are **proposed defaults**.*

**Latency / graph size**

* TC0130 (E) \[P2\]: Launch-time step checks add ≤50 ms (standard) / ≤100 ms (injection) vs baseline without step-type evaluation — measure in test env.  
* TC0131 (E) \[P2\]: Workflow with **N \= 50** steps (few distinct action kinds) — launch allow path stays within budget; authorize calls deduped by kind (≤ \# distinct action kinds).  
* TC0132 (E) \[P2\]: Workflow with **N \= 200** steps spanning all 7 action kinds — allow and deny paths both within budget; deny still fail-fast (no Temporal).  
* TC0133 (E) \[P2\]: Workflow with **N \= 500** steps (stress) — record p50/p95 launch-check latency; no timeout / 5xx; correctness preserved (allow vs deny).  
* TC0134 (E) \[P2\]: Large graph \+ deny on a kind present only once — 403/FAILED still fast (does not scan/execute the graph in the engine).

**Identity / DB scale**

* TC0135 (E) \[P2\]: DB seeded with **1,000 users**, **50 teams**, restricted user in one team with a step deny — Run 403 within latency budget.  
* TC0136 (E) \[P2\]: Same scale DB; allowed user (no matching deny) — Run allow within budget.  
* TC0137 (E) \[P3\]: GA-scale smoke: up to **5,000 teams** / **1,000 orgs** (if fixture feasible) — single launch check still completes; otherwise document deferral with measured ceiling.  
* TC0138 (E) \[P2\]: User belongs to **≥50 teams** with overlapping role assignments — step-permission launch check within budget.

**Projects × project-scoped policies (parameterized N)**

*Denies **per project** stay few (typically 1–2 kinds). Scale comes from **many projects**, each with its own project-scoped workflow\_node deny \+ role assignment. Run the suite at **N ∈ {50, 100, 200}**; treat **N \= 200** as the stress tier (record p50/p95; defer only if fixture cannot run).*

* TC0139 (E) \[P2\]: Parameter **N ∈ {50, 100, 200}** projects; each gets a project-scoped deny on one action kind (e.g. script) assigned to a shared restricted role — launch in a project **without** a matching deny for the invoker → allow within budget (assert at each N).  
* TC0140 (E) \[P2\]: Same parameterized fixture — launch in a project **with** a matching deny for the invoker → 403/FAILED within budget; correct kind \+ project isolation (assert at each N).  
* TC0140a (E) \[P2\]: Restricted user assigned the deny role in **N** projects (50 / 100 / 200 assignments) — effective-policy resolve \+ launch check still within budget at each N.  
* TC0141 (E) \[P2\]: Single system-wide (scope: any) deny on authenticated for one kind under large user DB — sampled principals denied everywhere; admin recovery (delete policy) still works.  
* TC0141a (E) \[P2\]: **Stress (N \= 200):** full project×deny fixture — record p50/p95 launch-check latency for allow and deny; correctness (allow vs deny by project) preserved; no timeout / 5xx.

**Concurrency**

* TC0142 (E) \[P2\]: **500 concurrent** launch authorization checks/s smoke (mixed allow/deny) — no error storm; latency distribution recorded.  
* TC0143 (E) \[P2\]: Concurrent schedule/webhook fires (e.g. 50\) with publisher denied — each gets FAILED record; no Temporal starts; no lost/dup storms beyond agreed tolerance.

**Audit overhead**

* TC0144 (E) \[P2\]: Allow-path audit write does not push launch over the 50/100 ms budget (compare audit-on vs audit-off if toggle exists; else measure absolute).  
* TC0145 (E) \[P3\]: Burst of 1,000 denied launches — audit table growth / insert latency acceptable; no dropped required fields.

**Triggered path**

* TC0146 (E) \[P2\]: Schedule fire under large-graph \+ large-user DB — allow and deny (FAILED record) latencies recorded; deny never reaches Temporal.

## **Mapping from Google-doc draft TCs → this plan**

| Draft TC | Draft intent | Disposition under MD D-1 |
| :---- | :---- | :---- |
| TC-1750-01 Interactive positive | Full permissions | Keep → TC0020 / TS-01 happy matrix |
| TC-1750-02 Interactive negative “halts at step” | Runtime DENIED | Rewrite → TC0021 fail-fast 403 (no halt-at-step) |
| TC-1750-03 Triggered positive | Publisher allowed | Keep → TC0040/42/44 |
| TC-1750-04 Triggered negative | Publisher denied | Rewrite → FAILED record, not runtime deny |
| TC-1750-05 Authoring unaffected | Designer OK | Keep → TS-07 |
| TC-1750-06 Deny triggers/flow in policy | Expect deny/reject | Keep as validation → TC0063/64 (422 at policy save — not runtime) |
| TC-1750-07 Project scope positive | Allowed outside project | Keep → TC0031 (B) |
| TC-1750-08 Project scope negative | Denied inside project | Keep → TC0031 (A), rewritten to 403/FAILED |

## **Decisions locked (2026-09-27)**

1. Test plan tracks handbook MD **D-1 fail-fast** (not runtime DENIED).  
2. **Audit:** emit on step-permission **deny** and on **allow**; **one event per launch**; deny payload lists **all denied nodes** in that workflow (TS-06 TC0072–TC0075, TC0078).  
3. Handbook (TS-11 / R-11) and ANSTRAT-2282 policy UI (TS-10) are **out of test scope**.  
4. TS-12 project scale parameterized at **N \= 50, 100, 200** (200 \= stress).

## **Remaining contradictions (Jira vs MD — not blocking the plan)**

Jira ACs still need rewrite for: runtime DENIED → fail-fast; shell → script; scope \* → any; kill switch / soft-error / per-model out of scope. Feature branch must realign to MD §12 before E2E freeze.

## **Open questions (non-blocking)**

5. Exact audit **event name / payload schema** field names — assert presence \+ outcome \+ principal \+ **denied-node list** (ids \+ kinds) until schema lands.
