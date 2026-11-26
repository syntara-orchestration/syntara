# Kafka Subscribe builder

The builder offers Kafka Subscribe in **Add step → Triggers**. Select a visible,
enabled Kafka Integration, an explicitly selected Kafka runtime credential, one
exact topic, and an optional payload JSON Schema. The schema controls validate
the message payload. Publishing activates the subscription; later changes take effect on the next publish.

Kafka credentials authenticate to the broker. Workflow execution identity is
provided by the platform. The UI does not offer an execution-account selector,
webhook authorization, group-ID editing, offset overrides, tuning, or
CloudEvents controls. The Integration's management credential is never used as a
fallback for a missing runtime credential.

Save/reopen uses flat `event_subscribe_trigger` parameters: `integration_id`,
`credential_id`, `topic`, optional `input_schema`, and optional `filter`. Leaving the schema blank
omits it instead of inserting an empty schema or a default.

Editing the same Kafka source preserves backend-configured `start` and `group_id`
values, including partial reading settings and an explicit null group. Changing
the topic or Integration preserves `start` but resets a saved `group_id` to null,
requesting an auto-generated group for the replacement source. Credential-only
changes preserve the group. The form does not expose these controls or add them
when omitted. Clearing the payload schema still removes `input_schema`;
unrelated consumer properties are not copied from the previous trigger.

## Optional CEL filter

Use **Filter expression (CEL)** to author one complete boolean CEL expression. The editor
preserves every non-empty expression exactly, including spaces, line breaks,
parentheses and explicit condition composition. The limit is 16,384 characters.
Removing the filter, clearing it, or entering only whitespace serializes `filter: null`;
no filter accepts every otherwise valid message. Changes affect the active
subscription on the next publication. Saved workflow version views show the
expression read-only. Save/reopen, unrelated trigger edits and import/export use
the same unchanged source text.

The help icon beside **Filter expression (CEL)** gives a brief introduction, one example,
and a documentation link. The step panel uses the same Kafka Subscribe documentation key.
Clear the expression to remove the filter; the editor stays visible and retains focus.

### Input fields and CEL reference

The only root variable is `input`, bound directly to the supplied message object.
A boolean `true` passes the message; `false` filters it out. Combine conditions
explicitly with `&&`, `||`, `!`, and parentheses; the UI adds no implicit conditions.
Supported comparisons include `==`, `!=`, `<`, `<=`, `>`, `>=`, and `in`.
String methods include `contains()`, `startsWith()`, `endsWith()`, and `matches()`.

- `input.key` and each header value have `kind` (`text`, `binary`, or `null`),
  `base64`, and `text` when UTF-8 decoding succeeds.
- `input.headers` uses case-sensitive names. Duplicate header values are lists in
  occurrence order. An absent header is different from a present null value.
- `input.metadata` includes `transport`, `topic`, `partition`, string `offset`,
  `timestamp_ms`, and `timestamp_type`. Timestamps may be null.
- `input.payload.state` is `decoded`, `not_decoded`, or `decode_error`. Decoded JSON
  is in `input.payload.value`, which may be null. Check the state and value before
  reading its properties.
- After successful CloudEvents decoding, `input.cloudevents` contains normalized
  attributes for Kafka binary and structured JSON modes, such as `type`, `source`,
  and `extensions.priority`. It is null before decoding, on decode failure, and
  for ordinary JSON. Guard attribute access with `input.cloudevents != null`;
  event data remains under `input.payload.value`. The sample tester binds the
  supplied JSON directly and does not perform CloudEvents decoding.

Use `has()` or `in` to check presence. A present null still needs a null check;
check value types before applying type-specific operations. Missing map keys
produce No match, while incompatible types can produce Evaluation error.
`matches()` uses RE2 search semantics: anchor with `^` and `$` for whole-string
matching. Backreferences and lookarounds are unsupported.

Each line below is a separate expression. Compose your complete condition explicitly:

```cel
input.key.kind == "text" && input.key.text.startsWith("order-")
"region" in input.headers && input.headers["region"].exists(h, h.kind == "text" && h.text == "eu")
input.metadata.topic == "orders" && input.metadata.partition == 0
input.payload.state == "decoded" && input.payload.value != null && has(input.payload.value.status) && input.payload.value.status == "ready"
input.key.kind == "text" && input.key.text.matches("^order-[0-9]+$")
```

### Sample testing

Expand **Test filter expression** to edit sample JSON in the syntax-highlighted JSON code editor, then choose **Test filter**.
Collapsing the tester preserves the sample. **Test filter** submits the current unsaved expression and editable sample JSON to
`POST /api/v1/filtering/test` through the typed filtering client. No saved workflow,
Integration, topic or credential selection is needed. The sample is bound directly
as `input`: the endpoint does not decode Kafka messages, validate payload schemas,
consume messages or trigger workflows. One matching sample does not establish
that every message will evaluate successfully. This action is separate from
**Test runtime access**.

Testing distinguishes **Match**, **No match**, **Evaluation error**, configuration
errors (plain-language compiler messages and line/column when provided), and compact inline request failures
retried with **Test filter**. The help icon beside **Test filter** explains its scope and limitations. Invalid JSON is rejected before submission. Editing either input
discards results, including pending responses. Server validation still runs on
Save, Verify, and publication; a successful sample cannot bypass it. CEL workflow findings identify `parameters.filter.expression`, appear beside the relevant trigger filter, and retain the expression for correction. Correcting the expression hides its previous field finding; rerun Save or Verify to refresh workflow findings. Existing draft-save and publication behavior is unchanged.

The mock API uses canned fixtures rather than a CEL engine: `true` matches;
`false` and `input.missing` do not match. Missing map keys produce no match in the
backend evaluator. With the Kafka-shaped sample, `input` returns an evaluation
error (`filter_non_boolean`) because the input object is not boolean. `input.`
returns a configuration error; unsupported mock fixtures return an evaluation
error placeholder. Use the real backend for arbitrary CEL evaluation.
Component tests cover all outcomes, JSON and
length validation, safe errors, retry, stale responses and accessibility. The
focused `e2e/kafka-subscribe-filter.spec.ts` covers unsaved testing, exact
save/reopen preservation, unrelated edits and removal against the mock API.

## Backend dependency and requirement differences

This frontend follows the existing backend contract, as agreed during implementation.
The Kafka Integration, Subscribe schema, and preflight implementation are included in this branch.
The existing backend accepts credential type **Kafka** and SASL_SSL.

Two intentional differences from the requested UI requirements:

- `credential_id` is required by this backend, including the preflight contract.
  The UI therefore requires a runtime credential for preflight and activation instead of offering a
  security-mode-dependent omission. Drafts may omit it while the workflow is being designed.
- Transport is inferred from the Integration. `transport: kafka` is not serialized
  because the backend forbids extra fields.

The workflow and Integration TypeScript contracts are generated from the current
backend schemas, not edited by hand. Regenerate all contracts with `make gen-contracts`,
or regenerate only these two contracts with:

```sh
npm --prefix frontend/packages/syntara-contracts run gen:kafka-prerequisites
```

The script uses the current checkout's backend schemas and the installed OpenAPI
generator, then formats the two outputs.

## Runtime access check

Save a new workflow before testing; the endpoint requires an existing workflow ID
and `workflow:update` permission. **Test runtime access** submits current unsaved
fields to `POST /workflows/{workflow_id}/event_subscriptions/test`. It does not
consume messages, start a workflow, or provide a message preview.

Integration validation is shown separately. The preflight response displays
connection and topic-metadata verification, failures, and unverified permissions.
Topic READ and consumer-group access remain unverified even after connectivity
succeeds. Raw broker errors are not rendered. Editing configuration discards old
results, including pending results for an earlier configuration.

## Default reading behavior

The platform generates a separate group for each source when no custom group is
supplied. The form does not expose the optional backend consumption controls;
their defaults are:

- Partitions in the saved first-activation set start with new messages at their
  saved visible-end boundary. Each boundary is selected when that partition
  initializes, rather than when Publish is clicked, and is reused after a setup
  interruption.
- Partitions added outside that saved set start at their earliest retained message,
  including messages produced before discovery. This also applies if discovery
  happens while first activation is still incomplete. The earliest retained offset
  can be greater than zero.
- Initialized partitions resume from valid committed group offsets on restart,
  re-enable, or republish. Missing or invalid established checkpoints recover from
  retained beginning under the normal source, assignment, and drain safeguards.

The backend API supports `start.position`, `start.added_partition_position`,
`start.offset_gap_policy`, and an optional `group_id`. Initial and added-partition
positions accept `earliest` or `latest`; gap policy also accepts `fail`, which
holds only the affected partition. Valid group progress and previously saved
position decisions take precedence over new settings. The group is fixed at
the first successful publication. See the
[backend settings contract](../backend/event-subscription-controls.md).

Auto-commit is disabled. Matching records commit after verified Temporal
acceptance and normal Execution persistence, without waiting for workflow
completion. Filter skips and audited invalid-content skips complete locally
under the offset-safety checks; logging alone never authorizes a commit.

## Validation

Component/helper tests use isolated API clients and cover serialization, reopening,
optional schema omission, literal IDs, exact topics, selection, permissions,
read-only views, preflight outcomes, keyboard operation, and axe accessibility.
The mock API includes Kafka resources and a non-consuming preflight response.
A running Kafka broker and a complete Kafka-to-workflow E2E journey are not
acceptance prerequisites for this frontend story.

## Implementation verification

- Run `npm run check` and `TZ=UTC npm test` from `frontend/` for static analysis,
  UI tests, coverage, and mock API contract checks.
- Six focused CEL browser scenarios cover outcomes, keyboard/accessibility,
  rejected saves, Verify field feedback, compact failure/retry, exact persistence, unrelated edits, removal, stale responses,
  and a browser export/import round trip.
- Frontend `npm run check` and production build pass. Existing repository lint
  warnings remain; the Kafka files introduce no warnings.
- Browser verification against the isolated mock API covered creating the trigger,
  preflight, saving, reloading, reopening, and keyboard navigation. Integration,
  runtime credential, topic, and optional schema omission were preserved.
- Live Kafka/runtime verification requires a running deployment with Kafka configured.

## Drafts and review corrections

Create and Update can retain an incomplete Kafka trigger. Missing fields are
omitted from draft parameters instead of being replaced with empty strings or
placeholder IDs. Backend advisory saves retain these drafts with readiness
findings; preflight, publish and runtime validation still require the complete
contract. Supplied references must remain literal, visible, enabled and usable;
an unavailable Integration or incompatible saved credential blocks form submission
and runtime preflight until corrected or cleared.

After selecting an Integration, the compact runtime credential row shows a
warning and **Set up connection** until a credential is selected. The picker opens
on demand, then collapses to the credential name and **Change**. **Cancel** closes
the picker without changing the saved selection. Keyboard selection returns focus
to **Change**. Changing the Integration clears the credential. A runtime credential
is still required. Published versions show a read-only credential summary; this
does not imply verified broker access.

The Integration and runtime credential selectors support search and clearing.
Credential creation is available when permitted. Loading supporting credential
types is not displayed as an empty result. Selector and bootstrap-server errors
are programmatically associated with their controls. The builder does not display
a persistent Integration health line. Read-only credential summaries use AAP-style
warning and check icons for missing and configured credentials; configured does
not mean runtime access has been verified. Sanitized preflight error codes are displayed
for diagnosis.

Initial resource loading keeps the form controls and credential status row in
place. Loading placeholders do not appear as validation errors or incomplete
preflight guidance. Runtime access testing stays disabled until lookups finish;
unavailable resources and lookup failures still produce actionable feedback.

The delayed-response layout regression can be run with:

```bash
npm --prefix frontend/packages/syntara-ui run e2e -- e2e/kafka-subscribe-loading.spec.ts
```

Delivery defaults are available under **Message delivery behavior**; preflight
scope is available in contextual help. Trigger output references use the Kafka
envelope: `trigger.payload.order_id` reads an `order_id` payload property, while
`trigger.metadata`, `trigger.original` and `trigger.envelope_version` remain
top-level envelope fields. Payload schema properties are never flattened onto
`trigger`.
