# Kafka initialization and recovery

The position service owns finite Kafka initialization and automatic recovery.
It performs broker calls outside database transactions and checks assignment
and epoch before position changes.

## First activation and partition growth

Persist the first verified complete, nonempty topic partition set in
`KafkaSourceConfiguration.initial_partition_ids`. Use full-topic metadata,
not the current consumer assignment. The saved set is immutable.

A member of that set uses `first_activation` and `start.position`, defaulting to
the read-committed visible end. A later partition uses `added_partition` and
`start.added_partition_position`, defaulting to retained beginning, which can be
nonzero. Both fields accept `earliest` and `latest`. Save initialization kind and
boundary under the unique source/partition key. Competing initializers reuse
the winning row, even after a policy change.

Seek, commit, verify and persist confirmation before marking a partition ready.
Write `source.initialized_at` once every saved first-set member is confirmed.
An added partition does not reset that timestamp or other ready partitions.

## Resumption and automatic offset recovery

Valid Kafka group commits govern established partitions. Saved initial positions
finish incomplete initialization; they are not ongoing consumption checkpoints.
Missing or out-of-range established offsets use `start.offset_gap_policy`:
`earliest` (the default) selects retained beginning, `latest` selects visible end,
and `fail` leaves the affected partition unresolved without moving its position.
Healthy partitions can continue under every policy.

For a new source without established history, persist the verified first
partition set and adopt an existing group offset before confirming initialization.
Never overwrite that offset with a preferred start position. The store rechecks
that the source is not established and that the partition has no retained
Execution evidence before adopting. Missing initialization history on an
established source remains blocked rather than being treated as a new source.

The Kafka client uses `auto_offset_reset="earliest"`. Its transport observes
out-of-range fetch responses before the SDK can hide them through an automatic
reset. Affected partitions cannot return records or commit until explicit
position reconciliation seeks a verified boundary. Existing recovery records
therefore remain authoritative; an SDK fallback does not authorize progress.

Persist a recovery token, reason, boundary and revision before changing Kafka
progress. Drain conflicting local work and discard old commit candidates.
Keep the fence until the selected commit and database confirmation reconcile.
Replace an expired pending boundary only through the revision-checked automatic
recovery path.

Publication changes apply only to new decisions. A pending recovery reuses its
saved policy and boundary even if the new policy is `fail`. If retention expires
that boundary, the revision-checked replacement follows the saved policy.

An active token fences only its partition. Other partitions keep their valid
positions and can continue. Clearing one token does not clear another partition's
hold; its owner resumes only after that partition's recovery confirms.

Background metadata requests cannot create topics. A metadata refresh triggers
source-identity verification before fetch results or commits are used. A changed
topic/cluster ID requires source replacement. Suspected topic loss also stops a
source when topic IDs are unavailable and recreation cannot be disproved.

Re-reading records reuses normal Executions and retained signed Temporal runs.
There is no per-delivery reconciliation, terminal proof cache or cache epoch.
No manual boundary or duplicate-risk acknowledgement is required for the
published automatic policy. Unknown source identity and uninspected local
content still block unsafe position changes. Known invalid content is audited
through the platform OTEL path; audit delivery does not authorize a position change.

## Historical compatibility

Nullable initialization kind represents legacy unknown membership. Do not infer
the original first set from today's metadata, relabel existing choices or move
saved boundaries to make migration succeed. Existing initial positions,
recovery history and normal Executions prevent treating historical sources as new.

The delivery-ledger removal migration refuses unresolved legacy state, including
an old source uncertainty marker without its saved first set. Resolve such
history using the compatible version before upgrading. The migration preserves
Kafka positions and normal Executions.

See [worker operations](../kafka-worker-operations.md) for upgrade and restore
ordering.
