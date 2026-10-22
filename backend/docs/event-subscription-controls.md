# Event subscription operational controls

Subscriptions remain projections of published workflow listeners. Operational
actions do not configure connections, select groups, edit offsets, replace frozen
execution input, or create a new execution identity.

All actions use `/workflows/{workflow_id}/event-subscriptions/{subscription_id}`
and require the current `configuration_revision` and `source_generation` in the
JSON body. Stale revisions or missing safety evidence return a sanitized 409.
Retry also conflicts while a prepared delivery has an active claim, so a wakeup
cannot be acknowledged and then lost behind that claim's eventual failure.

| Action | Authority | Behavior |
| --- | --- | --- |
| `POST /pause` | `workflow:update` | Close new admission and advance the revision; already prepared work remains recoverable. |
| `POST /resume` | `workflow:update` | Resume only the current published, available source. |
| `POST /retry` | `workflow:update` | Advance the runtime revision and wake existing prepared work without changing its identity, context or retry protection window. |
| `POST /recover` | `workflow:update` and `event_subscription:recover` | Persist a partition recovery policy for the assigned runner; return 202 pending. |
| `POST /retire` | `workflow:update` | Safely retire a source after listener removal or source replacement. |

Recovery additionally accepts `partition`, `expected_recovery_revision`, `policy`
(`retained_beginning` or `current_end`), a bounded reason code and
`acknowledge_duplicate_risk`. The existing Kafka position service selects and
persists the effective boundary. The request never accepts an assignment epoch or
arbitrary offset from the operator. Current Kafka ownership supplies the epoch.

Retirement accepts a bounded reason code. `resolve_unscheduled: true` on recovery
or retirement additionally requires `event_subscription:retire`. Both exceptional
grants are available to system admins and to project admins within their project;
ordinary workflow authority does not include them. No control requires
`execution:run`. Actor-facing Integration visibility and credential selection/use
checks remain in the existing workflow and unsaved-preflight paths.

## Convergence and fencing

Workers register a durable source participant before constructing a consumer,
under the same workflow/subscription/source locks used for admission. Consumers
reconcile PostgreSQL revisions. A successful local startup records its applied
revision; verified shutdown acknowledges the participant. Status reports pending
until all registered participants have converged, including older source
generations. A missing worker, elapsed timeout or expired delivery lease cannot
acknowledge shutdown. These rows coordinate lifecycle safety and do not assign
Kafka partitions or provide Visibility/activity storage.

List and detail responses include historical source generations, initialization and gap
metadata, queued recovery requests, and desired/applied convergence. Internal
recovery hold tokens and credentials are excluded.

Recovery executes through the current assigned runner and the existing boundary
service. Persisted recovery holds close cross-process admission and protect
retention while local fences drain tasks and previously issued commits. Interrupted
requests retain their decision and holds. Re-authorized continuation may add the
required acknowledgement or disposition authority at the current recovery revision
even before a recovery hold exists, without changing the configuration revision
or silently selecting a different policy or boundary.

## Retirement and deletion

Retirement preserves unresolved and ambiguous admissions and all retained terminal
identity. Explicit disposition can atomically mark a delivery and its pending
Execution `cancelled_by_lifecycle` only when no start attempt was authorized and no
acceptance evidence exists. Start attempt persistence and cancellation serialize
under lifecycle and delivery locks. Timed-out attempts and a Temporal not-found
response leave the work unresolved. Accepted workflows follow ordinary execution
cancellation policy.

Permanent decoding errors, pending content inspection and unpersisted content gates
remain protective after shutdown. Controls cannot clear them before the required
author-accessible activity logging exists.

Integration and runtime credential references remain bound while needed. Older
credentials in frozen admissions remain guarded in every delivery state after
republishing, for as long as that delivery evidence is retained. Empty, safely
retired sources can detach their Integration reference while retaining the canonical
Integration identity. A retired subscription can release its runtime credential
only after every source is independently releasable.

Workflow deletion requires publication to be disabled, every consumer to have
acknowledged stopping, no unresolved recovery dependency and no retained delivery
identity. The existing retention service must first establish its supported window
and verified committed progress. Deletion stays blocked when evidence cannot be
preserved; this change does not shorten retention or add cascade deletion of
delivery evidence.

## Deployment and validation

Stop existing ingestion/recovery workers before applying migration `4469722de5b7`,
then restart with registration-aware workers. Legacy workers cannot participate in
the new acknowledgements. Downgrade rejects outstanding runtime participation,
content gates, recovery decisions or retained retirement authorization evidence.

Unit tests cover operational dispatch, permission mappings and denial, revision
conflicts, participant fencing, evidence retention and atomic cancellation.
Control-to-runtime integration and downstream E2E tests remain outside M1.
