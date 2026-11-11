# Event Subscribe decoding contract

Event Subscribe accepts ordinary Kafka JSON and CloudEvents binary and structured
JSON content modes with JSON event data. Decoding is a pure operation: it returns a workflow event
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
- `application/cloudevents+json` identifies structured JSON mode before binary
  header detection, including when `ce_` headers are also present. Other media
  types beginning with `application/cloudevents` remain unsupported; this includes
  batches and Avro envelopes. Ordinary JSON retains its existing content-type
  handling (`application/json` and JSON suffixes, with supported UTF-8 charset).

These candidate/fallback and casing rules are explicit application decisions for
review; the Kafka binding does not prescribe a partial-header detection policy.

## Structured JSON mode

The structured binding follows the [CloudEvents JSON event format](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/formats/json-format.md).
The Kafka value must be one JSON object containing required `specversion`, `id`,
`source`, and `type` attributes. The transport `content-type` selects the envelope
format; only the envelope's `datacontenttype` describes event data.

```json
{
  "specversion": "1.0",
  "id": "order-123",
  "source": "/orders",
  "type": "order.created",
  "datacontenttype": "application/json",
  "attempt": 123,
  "data": {"orderId": 123}
}
```

This becomes `payload: {"orderId": 123}` and normalized `cloudevents` attributes,
including `extensions.attempt: "123"`. It uses the same attribute validation and
representation as the equivalent binary event. The entire original structured
value, Kafka key, and all headers remain in `original`.

- Envelope attributes are authoritative. Transport `ce_` headers are preserved
  but never merged into or used to override structured attributes.
- All JSON data roots are supported. A string containing JSON text remains a
  string and is never parsed a second time.
- Absent `data` and explicit `data: null` both produce `payload: null`; original
  bytes retain the distinction. A Kafka null value remains a tombstone.
- Null attributes are unset: null required attributes fail, null optional and
  extension attributes are omitted from normalization.
- Top-level extensions normalize strings without inference, Booleans as `"true"`
  or `"false"`, and signed 32-bit integers as decimal strings. Object, array,
  fractional-number and out-of-range integer attributes are malformed.
- Absent/null `datacontenttype` permits JSON data and remains `null` in the shared
  model. Explicit content types reuse supported JSON media-type/charset checks.
- Non-JSON data encodings and `data_base64` are unsupported. An envelope with
  both `data` and `data_base64` is malformed, even when either is null.
- Strict UTF-8, duplicate-member, finite-number and nesting safeguards apply to
  the entire document before normalization. Schema validation applies only to the
  extracted data, and the final size check includes normalized attributes.

Mode equivalence concerns `payload` and normalized attributes; original wire bytes
and source metadata are not expected to be identical across different records.

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
- In binary mode, `datacontenttype` comes from Kafka's validated `content-type`
  header, with surrounding horizontal whitespace removed. In structured mode it
  comes from the envelope attribute. Absence/null remains `null` in the shared
  model; supported event data must still be JSON.
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

The decoder provides these sanitized CloudEvents result codes:

| Code | Meaning |
| --- | --- |
| `malformed_cloudevents` | Missing, duplicate, invalid, reserved, or incorrectly cased attributes. |
| `unsupported_cloudevents_version` | A non-empty specification version other than `1.0`. |
| `unsupported_cloudevents_mode` | An unsupported CloudEvents event format, including batches. |
| `unsupported_cloudevents_data` | Base64 event data or unsupported data media type/charset. |

Existing tombstone, UTF-8, JSON, content-type, registry-framing, schema, and size
failure codes remain applicable. Safety limits and content-type checks run
before normalization. Binary attribute errors precede data parsing; structured
JSON parsing precedes envelope attribute validation. Messages
with multiple defects receive the first failure encountered, not a list.
Failure results and model representations do not include event contents.

The caller retains the raw record for correlation and durable failure recording.
A decode failure is not durable delivery evidence and provides no permission to
discard a record or advance an offset. The current processing service persists
safe unresolved error evidence and holds permanent content failures with
`activity_log_unavailable` until the author-accessible activity-recording path
exists. This protects the affected partition, including after restart; adding
structured decoding does not remove that hold. General filtering and durable
activity recording remain separate integration dependencies.
