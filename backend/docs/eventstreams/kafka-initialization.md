# Kafka initialization and recovery provider

This provider owns finite initialization and recovery operations. It does not
provide public operational routes, worker status wiring, cache storage, workflow
parameters, placement, or general replay.

## First activation and partition growth

Before selecting a partition boundary, persist the first verified complete,
non-empty topic partition set in `KafkaSourceConfiguration.initial_partition_ids`.
The full-topic observation comes from the transport metadata interface, never
from consumer assignment. Capture runs under the source lifecycle lock and
returns the saved winner after commit. Later metadata does not expand the set.
Verified cluster/topic identifiers remain subject to incarnation checks.

For a new position row, a saved-set member uses `first_activation` and the
`read_committed` visible end. A nonmember uses `added_partition` and retained
beginning, which may be nonzero. This also applies to additions discovered while
first activation is incomplete or after a pause/outage. Broker bounds are read
outside transactions; kind and boundary are saved together under the existing
unique source/partition key, with membership checked under the lifecycle lock.
An existing winning row is reused rather than moved to a newer bound.

Initial seek, commit, verification, and durable confirmation must finish before
that partition receives READY. A saved incomplete boundary outside retention
becomes a recovery gap. Valid current group commits govern resumption. An
established partition with a missing/invalid checkpoint is never reclassified as
a newly added partition.

`source.initialized_at` is written once, after all members of the saved first set
have confirmed initial commits. An added partition neither completes nor resets
that timestamp. Previously ready partitions remain independently eligible while
an added partition initializes. Source-level status presentation belongs to #972.
Administrative recovery does not falsely confirm an original boundary that was
never committed; original first-activation completion can therefore remain
unproven even when a particular partition has an explicit confirmed recovery.

## Historical compatibility and migration

Migration `91f4c2e8a6bd` adds nullable `initialization_kind` with the permitted
`first_activation` and `added_partition` values. New initialization always writes
a non-null kind. NULL explicitly represents legacy/unknown membership; it is
not an alias for either kind. Read models preserve that distinction and keep
offsets as decimal strings.

The migration does not backfill kinds, offsets, timestamps, or the original
partition set from current metadata. Existing boundaries remain real historical
choices, including boundaries that differ from today's beginning/end.

Stop/drain ingestion and recovery before upgrading. For pre-existing Kafka
sources without a saved first set, the migration advances the existing
`delivery_evidence_revision` under table locks. This uncertainty fence prevents
automatic capture even if all old position/delivery evidence is absent. It does
not establish original membership, replace the source, or change its group.
New sources begin with revision zero. The provider additionally refuses initial
capture when initialization, recovery, or retained delivery history exists.

Sources with a saved immutable set and recorded kinds reuse those choices.
An existing ambiguous position produces `initialization_history_unavailable`
and retains its original offset. Explicit administrative recovery may establish
an effective boundary for that partition without relabeling its history or
inventing the source's original set. If no position/group evidence is available
to support recovery, the provider stays blocked for controlled source replacement.
It cannot safely infer initialization policy for newly discovered partitions of
a legacy source whose original set is unknown.

Safe downgrade requires stopped ingestion/recovery and no retained non-null kind
evidence. The migration refuses to erase classified boundaries. Never remove
evidence merely to pass the guard; its source must be permanently inaccessible
and all delivery/recovery dependencies resolved first. Downgrade does not lower
the evidence revision or reconstruct missing history.

## Cache coordination and recovery

Initialization and administrative commits never consult terminal-cache hits as
checkpoint evidence. Recovery retains its durable gap, boundary, revision, and
hold until the selected Kafka commit and database confirmation are reconciled.
Permanent-content-error and duplicate-risk acknowledgement gates still apply.

Backward recovery below the effective authorized lower bound, and recovery with
an unknown original lower bound, require an injected `RecoveryCacheCoordination`
guard. The guard must establish deployment-wide close/drain and external
cache-epoch isolation for the exact source request, recovery token, revision,
and boundary. It must also prevent old readers/writers from remaining trusted.
A disabled-cache deployment must establish that condition across the deployment;
a local disabled setting or a cache miss is insufficient.

The provider checks coordination before claim reconciliation and again around
position changes/confirmation. A missing, false, or unavailable guard keeps
recovery closed and its evidence hold retained. Loss after a Kafka commit does
not clear the pending decision; retry reconciles it. Forward recovery that
preserves terminal outcomes does not require epoch rotation. This provider never
rewrites terminal outcomes to permit recovery. #990/#996 own operator/control
wiring, and #990 owns public operational API exposure and generated contracts.

## Manual validation

No tests, static checks, migration generation, or database migration execution
were run for this update. The added migration contains explicit custom
compatibility handling; review it against the SQLModel metadata before rollout.
From the repository root, start with:

```bash
make -C backend install
```

Then, from `backend/`, run the focused unit and schema cases:

```bash
uv run pytest tests/unit/eventstreams/test_kafka_initial_positions.py tests/unit/eventstreams/test_kafka_position_store.py -n 0 -o 'addopts=-ra --strict-markers --strict-config'
uv run mypy --strict src/syntara/eventstreams/adapters/kafka_*position*.py tests/unit/eventstreams/test_kafka_*position*.py tests/integration/eventstreams/test_initial_positions.py
make check-migrations
```

With a local container runtime available, run the integration cases separately:

```bash
./tools/scripts/run-with-testcontainers.sh -- uv run pytest tests/integration/eventstreams/test_initial_positions.py -n 0 -o 'addopts=-ra --strict-markers --strict-config'
```

Use the repository's formatting/lint workflow for the changed files. The added
tests exercise full-topic capture, competing writers, interruptions, additions,
retention changes, source completion, legacy ambiguity, migration guards, and
cache coordination using isolated stores/clients. They are not real-broker or
cross-process validation.
