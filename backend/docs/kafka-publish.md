# Kafka Publish workflow action

Add **Kafka Publish** from the workflow builder's Add step panel. Choose a Kafka
integration, select the runtime Kafka credential when the connection uses SASL,
and enter an existing, fixed topic. Publish runs in the normal workflow worker;
that worker must be able to reach the integration's brokers.

The payload editor accepts any JSON value, including arrays, strings, numbers,
booleans and `null`. A full-value template such as `${trigger.payload}` preserves
the referenced value's type. A JSON-looking string stays a string. Missing
template references fail before publishing. The message is resolved once and
remains unchanged across automatic action retries.

An example node in a v2 workflow definition:

```json
{
  "id": "publish_result",
  "name": "Publish outcome",
  "type": "kafka_publish",
  "parameters": {
    "integration_id": "11111111-1111-4111-8111-111111111111",
    "credential_id": "22222222-2222-4222-8222-222222222222",
    "topic": "automation.outcomes",
    "payload": {"outcome": "${previous_step.outcome}"},
    "key": {"encoding": "utf-8", "value": "order-123"},
    "headers": [
      {"name": "correlation-id", "value": {"encoding": "utf-8", "value": "request-123"}},
      {"name": "binary-context", "value": {"encoding": "base64", "value": "AAEC"}},
      {"name": "optional-context", "value": null}
    ]
  },
  "settings": {
    "timeout": 30,
    "retry_policy": {"max_retries": 3}
  }
}
```

## Message contract

One invocation sends one Kafka record. An array is one record, not a batch. The
value is compact UTF-8 JSON with stable object ordering. An explicit JSON `null`
is the four-byte value `null`, not a Kafka tombstone. A payload is required.

Keys and non-null header values use explicit `utf-8` or `base64` encoding/value
objects. Base64 decoding is strict. An omitted/null key is a Kafka null key;
an empty encoded value is empty bytes. Headers are an ordered list and preserve
duplicate names, null values and empty bytes. Omitted headers mean no user
headers. A template may supply the complete list in this same representation.
Subscribe's `value_base64` header representation needs an explicit mapping.

Topic, integration and credential references are fixed in the workflow version.
Partition selection and Kafka timestamps use the client/broker defaults. There
is no partition selector, timestamp override or arbitrary producer-options input.

## Delivery, retries and cancellation

The producer always uses `acks=all` and native idempotence. Success means Kafka
acknowledged the message, not that a downstream consumer processed it. Producer
idempotence protects internal retransmission of the same send; another action
attempt or workflow rerun can publish another copy. Consumers that require
business deduplication must use their own stable business identifier.

Publish inherits the existing action retry controls. Defaults allow three
retries after the initial send attempt, with 1, 2 and 4 second delays. Setting
`max_retries=0` disables additional action attempts, while native producer
retransmission remains enabled. Each attempt defaults to 30 seconds. One
180-second invocation deadline also bounds snapshot preparation, queueing,
attempts and retry delays; not every configured attempt is guaranteed to fit.

Temporary transport, metadata/leader and in-sync-replica failures may retry.
Invalid inputs, confirmed missing topics, oversized messages, authentication or
authorization failures, revoked resources and changed connection settings fail
without another send. Unclassified errors are terminal and sanitized.

Failures use the ordinary activity error/output mechanism. `error_code` is a
stable category such as `kafka_invalid_message`, `kafka_message_too_large`,
`kafka_arguments_too_large`, `kafka_invalid_reference`, `kafka_topic_not_found`,
`kafka_authentication_failed`, `kafka_authorization_failed`,
`kafka_connection_failed`, `kafka_metadata_unavailable`,
`kafka_capacity_unavailable`, `kafka_timeout`,
`kafka_connection_settings_changed`, `kafka_producer_failed` or
`kafka_unexpected_error`.

`delivery_status=not_sent` is used only when no attempt could have queued a
record. `unconfirmed` means delivery may have happened or cannot be ruled out.
An earlier uncertain attempt is not erased by a later pre-send failure. After
worker loss, retries conservatively retain uncertainty without a delivery ledger.
Errors omit message/key/header values, credentials and raw broker exception text.
Kafka SDK diagnostics are sanitized at application log sinks, including when
debug logging is enabled, because protocol dumps can contain record bytes.

Cancellation uses existing workflow/activity states and stops new action work
once observed. A queued send may still complete after cancellation or timeout.
Cancellation cannot undo an acknowledged record; late acknowledgment does not
resume downstream execution.

## Success output

```json
{"topic":"automation.outcomes","partition":2,"offset":"98321","timestamp_ms":1793354400000}
```

Offsets are decimal strings to preserve precision in JavaScript. Unavailable
offsets/timestamps become `null`; acknowledged sends are not retried to obtain
metadata. Output mappings and normal continuation/failure policies apply.

## Connection and credential changes

Invocation preparation resolves the selected credential and connection settings
once, using existing credential encryption/scrubbing in Temporal history. It
never falls back to the integration's management credential. SSL or explicitly
opted-in PLAINTEXT connections can omit a runtime credential under the shared
Kafka connection rules.

Saving a workflow checks Integration visibility and runtime credential
compatibility. Preparation reads the revision and credential within one database
snapshot so concurrent rotation cannot associate a secret with the wrong
producer revision. Preparation also heartbeats for cancellation and receives the
original invocation deadline on every retry, including after queueing.

Automatic send retries keep that secret version. A later invocation resolves
the latest version. Before another action send, Publish checks current resource
availability, project scope and connection settings. Deleted, disabled or
inaccessible resources stop further sends; edited connection settings do not
redirect an in-progress retry to new brokers. Display-name edits do not fail an
invocation. Authentication rejection of an older secret is terminal.

## Limits and worker lifecycle

| Limit or producer setting | Value |
| --- | --- |
| Conservative uncompressed Kafka record estimate | 1,048,576 bytes, inclusive; includes value, decoded key, headers and record/batch overhead |
| Complete encoded Temporal arguments | 1,887,436 bytes, using the existing converter and credential-codec framing |
| Header entries | 128, counting duplicates and null-valued entries |
| Active/starting/retiring producer instances per worker | Worker `max_concurrent_activities` (N; default 50) |
| Unresolved sends per worker | N, including sends whose callers stopped waiting |
| Retained Kafka record data | N × 1 MiB; this is not a total process RAM limit |
| Unused producer expiry | 300 seconds; no pending sends |
| Producer request timeout | 10,000 ms |
| Batch target / internal retry backoff | 16,384 bytes / 100 ms |
| Compression / intentional linger | None / 0 ms |

Kafka and Temporal limits are checked independently before their respective
scheduling/sending boundaries. Messages are not split or truncated. The broker
or topic can impose a lower limit; its size rejection is terminal. The 1 MiB
application limit is independent of the SDP's under-1-MB performance condition.

Producers are lazily reused within one worker/event loop. Pending delivery
tasks and retiring producers remain counted until they actually settle. When
capacity is full, new work waits within its deadline and may fail with
`kafka_capacity_unavailable`.

With the unchanged `aiokafka` client, an idempotent pending send and public
`stop()` can outlive caller deadlines during an outage. Shutdown stops admission
and bounds waiting without cancelling the managed cleanup. A message may arrive
later, and resources may remain allocated until broker recovery or worker
process exit. No per-producer reclamation deadline is promised, and one action
timeout does not restart the shared worker.

## Kafka prerequisites

Administrators provision topics. To prevent the unchanged producer from
implicitly recreating a deleted/missing topic, require either:

- Broker `auto.create.topics.enable=false`.
- Effective Kafka authorization that prevents the selected runtime identity from
  creating that topic through either cluster-level or topic-level `CREATE`,
  considering broad grants and superuser privileges.

A connection test or a non-creating metadata preflight does not certify these
Kafka-side protections. Syntara does not modify broker configuration or ACLs.
Existing workflow, integration and credential permission policies apply; no
Publish-specific routes, permissions, durable tables or Redis delivery cache
are introduced. Existing backup/restore procedures apply and cannot rewind
external Kafka messages.

The performance team validates the existing under-50-ms p95 target with
`acks=all` for messages under 1 MB. Functional tests and these operating defaults
do not constitute that benchmark.

## Backend validation

The ordinary integration suite starts a disposable KRaft broker through
testcontainers. It checks exact JSON/key/header bytes, confirmed missing topics,
disabled implicit topic creation, and lower broker message limits. Temporal
integration scenarios exercise automatic retries, `max_retries=0`, terminal
authorization failures, frozen inputs and downstream execution. The opt-in
`test_kafka_publish_live.py` additionally exercises the root Compose SASL/TLS
fixture (`SYNTARA_KAFKA_PUBLISH_LIVE=1`).
