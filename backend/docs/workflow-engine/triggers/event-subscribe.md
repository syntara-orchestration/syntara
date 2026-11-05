# Event Subscribe decoding contract

Event Subscribe accepts ordinary Kafka JSON and CloudEvents binary content mode
with JSON event data. Decoding is a pure operation: it returns a workflow event
envelope or a sanitized failure, without I/O, activity recording, discard,
acknowledgement, or offset commits.

## Kafka detection policy

The implementation follows the [CloudEvents 1.0.2 Kafka binding](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/bindings/kafka-protocol-binding.md),
with these application policies for ambiguous input:

- Any required attribute header (`ce_specversion`, `ce_id`, `ce_source`, or
  `ce_type`) identifies a CloudEvents candidate. An incomplete candidate fails;
  it never silently falls back to ordinary JSON. Incorrectly cased required
  headers also identify a candidate, which then fails validation.
- CloudEvents header names must use canonical lowercase `ce_` names. The
  HTTP-style `ce-` prefix is not recognized. Attribute names contain only ASCII
  lowercase letters and digits. Duplicate attributes, including duplicates with
  identical values, and null attribute values are malformed.
- Extension-only or optional-only headers do not identify a candidate and remain
  original routing headers on ordinary JSON messages. Message body shape is
  never used to detect CloudEvents.
- Media types beginning with `application/cloudevents` identify unsupported
  structured mode before JSON or binary-mode fallback, even if binary headers
  are also present. Ordinary JSON messages retain the existing content-type
  handling (`application/json` and JSON suffixes, with supported UTF-8 charset).

These candidate/fallback and casing rules are explicit application decisions for
review; the Kafka binding does not prescribe a partial-header detection policy.

## Workflow envelope

The existing version 1 envelope has these fields:

| Field | Meaning |
| --- | --- |
| `payload` | Strictly decoded JSON message value, including scalar roots and JSON `null`. |
| `cloudevents` | Typed attributes for a recognized event; `null` for ordinary JSON. |
| `original` | Original value/key bytes and ordered headers, encoded as base64. |
| `metadata` | Existing source coordinates, receipt time, and subscription identifiers. |

`cloudevents` contains required strings `specversion` (only `1.0`), `id`, `source`,
and `type`. Required values must be non-empty. Optional `subject`, `time`,
`dataschema`, and `datacontenttype` fields are `null` when absent.

- `source` is a non-empty RFC 3986 URI-reference, including relative references.
- `dataschema` is a non-empty absolute URI when supplied; it is never fetched.
- `subject` is non-empty when supplied.
- `time` is an RFC 3339 timestamp string; its offset, precision, and spelling are
  retained. Leap seconds are not supported by the timestamp validator.
- `datacontenttype` comes from the validated Kafka `content-type` header, with
  surrounding horizontal whitespace removed. No content type is invented when
  the header is absent or null; the message value must still be JSON.
- `extensions` is a map of additional attributes to UTF-8 strings. Values such
  as `"true"` and `"123"` are not guessed to be booleans or numbers. Empty
  extension strings are allowed. Control characters, Unicode noncharacters,
  invalid UTF-8, and collisions with reserved fields are rejected.

`ce_datacontenttype` is rejected: use `content-type`. `ce_data` and
`ce_extensions` are reserved and rejected. Event data belongs only in `payload`.
No key is derived from an attribute such as `partitionkey`.

The original representation preserves header order, repeated routing headers,
and null versus empty byte values. CloudEvents normalization never changes
`original` or `metadata`.

## Workflow access and validation

Without output mapping, workflow expressions can use `${trigger.payload.orderId}`
and `${trigger.cloudevents.type}`. Trigger output mapping can expose selected
values:

```yaml
outputs:
  orderId: ${result.payload.orderId}
  eventType: ${result.cloudevents.type}
```

Successor steps can then use `${trigger.orderId}` and `${trigger.eventType}`.
The trigger node ID is also a namespace for these outputs.

`input_schema` validates only `payload` with the existing safe Draft-07 checks.
It does not validate the enclosing envelope, apply defaults, or modify data.
Kafka null values remain tombstones; JSON `null` is a supported payload.

The configured value-size and header-count limits remain in effect. The complete
encoded-envelope size is checked after normalization and includes attributes,
payload, source metadata, all original bytes, and base64 expansion. These are
candidate envelope limits, not guarantees for complete Temporal start arguments.

## Failure categories

The decoder adds three sanitized result codes:

| Code | Meaning |
| --- | --- |
| `malformed_cloudevents` | Missing, duplicate, invalid, reserved, or incorrectly cased attributes. |
| `unsupported_cloudevents_version` | A non-empty specification version other than `1.0`. |
| `unsupported_cloudevents_mode` | An explicitly declared structured CloudEvents media type. |

Existing tombstone, UTF-8, JSON, content-type, registry-framing, schema, and size
failure codes remain applicable. Safety limits and content-type checks run
before attribute normalization; attribute errors precede JSON parsing. Messages
with multiple defects receive the first failure encountered, not a list.
Failure results and model representations do not include event contents.

The caller retains the raw record for correlation and durable failure recording.
A decode failure is not durable delivery evidence and provides no permission to
discard a record or advance an offset. General Kafka filtering, the consumer
loop, and durable per-message recording are separate runtime dependencies; this
decoder does not implement those capabilities.
