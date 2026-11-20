# Kafka Subscribe settings and connection testing

Subscribe accepts only these optional consumption controls:

| Parameter | Allowed values | Default |
| --- | --- | --- |
| `start.position` | `latest`, `earliest` | `latest` |
| `start.added_partition_position` | `earliest`, `latest` | `earliest` |
| `start.offset_gap_policy` | `fail`, `earliest`, `latest` | `earliest` |
| `group_id` | 1–512 ASCII letters, digits, `.`, `_`, or `-`; or null | Auto-generated |

The three `start` fields belong to an optional nested `start` object. Its fields
may be supplied independently. Unknown fields, arbitrary consumer properties,
null reading policies, and unsupported values are rejected, including direct API
submissions. Resource selection and authorization follow existing workflow rules.

## Publication and effective settings

Publication saves effective settings in the typed source configuration before
consumer creation. Older definitions and source rows load with the defaults
above. Draft changes affect consumption only after publication.

A source generation binds one Integration and exact topic. Its group becomes
fixed at the first successful publication, before worker activation. On a
same-source republish, an omitted or null group preserves the existing group;
a different explicit group is rejected. Group identifiers cannot be shared
across stored sources, including retired sources retained for recovery.

Changing the topic or Integration creates a replacement source. It uses the new
published reading settings and needs a different custom group or a generated
group. The retired source retains its positions and recovery evidence.

Reading-setting changes advance the configuration revision. Worker reconciliation
drains the old runtime and applies the new configuration. Changes affect only
position decisions that have not already been saved. Valid group progress,
saved initialization boundaries, and pending recovery policies/boundaries remain
authoritative across republish and restart.

A genuinely new source can adopt a valid existing Kafka group offset. That
offset takes precedence over `start.position`; it is never overwritten merely
because a starting preference was supplied. An established source with missing
initialization history still requires recovery. Custom groups must remain
exclusive to their Syntara source; database uniqueness cannot exclude external
applications from joining a Kafka group.

`fail` holds only the partition with an offset gap, without choosing or committing
a replacement position. Healthy partitions continue. A later published policy
can resolve that gap if no recovery decision was previously saved. `earliest`
selects retained beginning; `latest` selects the read-committed visible end.
Source-identity, lifecycle, dependency, drain, and assignment safeguards still
apply to every reset.

## Connection testing

Kafka Subscribe exposes one workflow-scoped helper endpoint:

```text
POST /api/v1/workflows/{workflow_id}/event_subscriptions/test
```

The workflow builder's **Test connection** button sends unsaved Integration,
runtime credential and topic parameters to this endpoint. It checks connectivity
and topic metadata without publishing the workflow, starting an Execution,
joining a consumer group or committing offsets. Topic-read and consumer-group
permissions remain unverified by this non-consuming test.

The endpoint uses existing workflow permissions, with `workflow:update` required
at the route. Resource validation checks access to the Integration and runtime
credential. It does not introduce subscription-specific RBAC permissions or fall back to the
Integration's management credential.

Subscription configuration and activation use the existing workflow APIs.
There are no separate subscription list, detail, pause, resume, retry, manual
recovery or retirement endpoints. Publishing, unpublishing and listener changes
continue through the workflow lifecycle.

Publishing a subscription with a legacy pause flag clears that flag and advances
its configuration revision. Stop event workers before upgrading. The upgrade
also clears legacy pause flags and advances the configuration revision for
desired, non-retired subscriptions matching their workflow's current enabled
publication. These subscriptions resume under normal worker checks after the
upgrade. Unpublish a workflow before upgrading if it must remain stopped.
Disabled, retired and unpublished subscriptions remain unchanged.

The worker retains subscription placement leases, partition recovery fences and
bounded local draining. Matching records commit only after verified Temporal
acceptance and normal Execution persistence. Offset gaps follow the published
policy under source and assignment checks; omitted settings preserve earliest
recovery. Invalid records emit best-effort platform OTEL audit events and complete
locally under the normal offset-safety checks. Activity logs are deferred, and
audit delivery is not commit evidence or a prerequisite for an otherwise safe skip.

## Compatibility and downgrade

These settings extend existing JSONB configuration; no new table, column, or
Alembic migration is required. This does not make a binary downgrade safe:
older releases reject the new definition and source-configuration fields.

Before downgrading, stop event workers and settle pending initialization/recovery
using a compatible release. All retained workflow definitions and source JSON
must be made compatible through a reviewed data migration before an older
release reads them. Preserve source identities, group IDs, initial partition
sets, position records, and Execution/Temporal recovery evidence. Never rename a
group or delete recovery evidence to make downgrade validation succeed.

Database restore remains a separate platform recovery operation. Do not resume
consumption with Kafka progress ahead of restored evidence until PostgreSQL,
Kafka, and Temporal have been reconciled.

See [worker operations](kafka-worker-operations.md) and
[record processing](kafka-record-runner.md) for runtime behavior.
