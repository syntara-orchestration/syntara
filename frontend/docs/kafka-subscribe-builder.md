# Kafka Subscribe builder

The builder offers Kafka Subscribe in **Add step → Triggers**. Select a visible,
enabled Kafka Integration, an explicitly selected Kafka runtime credential, one
exact topic, and an optional payload JSON Schema. The schema controls validate
the message payload. Publishing activates the subscription; later changes take effect on the next publish.

Kafka credentials authenticate to the broker. Workflow execution identity is
provided by the platform. The UI does not offer or serialize an execution-account
selector, webhook authorization, group IDs, offset overrides, tuning, or
CloudEvents controls. The Integration's management credential is never used as a
fallback for a missing runtime credential.

Save/reopen uses flat `event_subscribe_trigger` parameters: `integration_id`,
`credential_id`, `topic`, optional `input_schema`, and optional `filter`. Leaving the schema blank
omits it instead of inserting an empty schema or a default.

## Optional CEL filter

Use **Filter expression (CEL)** to author one complete boolean CEL expression. The editor
preserves every non-empty expression exactly, including spaces, line breaks,
parentheses and explicit condition composition. The limit is 16,384 characters.
Removing the filter, clearing it, or entering only whitespace serializes `filter: null`;
no filter accepts every otherwise valid message. Changes affect the active
subscription on the next publication. Saved workflow version views show the
expression read-only. Save/reopen, unrelated trigger edits and import/export use
the same unchanged source text.

The help icon beside **Filter expression (CEL)** describes `input.key`, case-sensitive header names
whose duplicate values are ordered lists, Kafka `input.metadata`, and decoded
`input.payload.state` / `input.payload.value`. Key/header values distinguish text,
binary and null; payload values can also be null. Use presence and type/state
guards before accessing optional content. Compose conditions explicitly using
CEL operators. `matches()` uses RE2 search semantics; anchor with `^` and `$`
for whole-string matching. Backreferences and lookarounds are unsupported.
Examples wrap within the scrollable help popover. Clear the expression to remove
the filter. The editor stays visible, preserving keyboard focus.

Expand **Test filter expression** to edit sample JSON, then choose **Test filter**.
Collapsing the tester preserves the sample. **Test filter** submits the current unsaved expression and editable sample JSON to
`POST /api/v1/filtering/test` through the typed filtering client. No saved workflow,
Integration, topic or credential selection is needed. The sample is bound directly
as `input`: the endpoint does not decode Kafka messages, validate payload schemas,
consume messages or trigger workflows. One matching sample does not establish
that every message will evaluate successfully. This action is separate from
**Test runtime access**.

Testing distinguishes **Match**, **No match**, **Evaluation error**, configuration
errors (safe compiler codes and line/column when provided), and request failures
with retry. Invalid JSON is rejected before submission. Editing either input
discards results, including pending responses. Server validation still runs on
save/publication; a successful sample cannot bypass it, and rejected operations
leave the expression available for correction.

The mock API uses canned fixtures rather than a CEL engine: `true` matches,
`false` does not match, `input.` returns a configuration error, and unsupported
fixtures return an evaluation error. Component tests cover all outcomes, JSON and
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

## Fixed reading behavior

The platform manages a separate group for each subscription and fixes its reading
policies:

- Partitions in the saved first-activation set start with new messages at their
  saved visible-end boundary. Each boundary is selected when that partition
  initializes, rather than when Publish is clicked, and is reused after a setup
  interruption.
- Partitions added outside that saved set start at their earliest retained message,
  including messages produced before discovery. This also applies if discovery
  happens while first activation is still incomplete. The earliest retained offset
  can be greater than zero.
- Initialized partitions resume from valid committed group offsets on restart,
  re-enable, or republish. Missing or invalid established checkpoints block reading
  and require recovery; they never trigger an automatic reset to latest or earliest.

Auto-commit is disabled. Offsets are committed after durable workflow scheduling
or another durable resolution, without waiting for workflow completion.

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
- Four focused CEL browser scenarios cover outcomes, keyboard/accessibility,
  rejected saves, exact persistence, unrelated edits, removal, stale responses,
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

Credential setup is hidden until an Integration is selected. **Set up connection**
opens the searchable runtime credential picker. Selecting a credential shows its
configured name with **Change**; this does not imply verified broker access.
Changing the Integration clears the credential and returns to setup. Keyboard
selection returns focus to the selector input, or to **Change** when the staged
picker closes.

The Integration and runtime credential selectors support search and clearing.
Credential creation is available when permitted. Loading supporting credential
types is not displayed as an empty result. Selector and bootstrap-server errors
are programmatically associated with their controls. The builder does not display
a persistent Integration health line. Credential setup uses AAP-style warning and
check icons for missing and configured credentials; configured does not mean
runtime access has been verified. Sanitized preflight error codes are displayed
for diagnosis.

Delivery defaults are available under **Message delivery behavior**; preflight
scope is available in contextual help. Trigger output references use the Kafka
envelope: `trigger.payload.order_id` reads an `order_id` payload property, while
`trigger.metadata`, `trigger.original` and `trigger.envelope_version` remain
top-level envelope fields. Payload schema properties are never flattened onto
`trigger`.
