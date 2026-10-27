# Kafka Subscribe builder

The builder offers Kafka Subscribe in **Add step → Triggers**. Select a visible,
enabled Kafka Integration, an explicitly selected Kafka runtime credential, one
exact topic, and an optional payload JSON Schema. The schema controls validate
the message payload. Publishing activates the subscription.

Kafka credentials authenticate to the broker. Workflow execution identity is
provided by the platform. The UI does not offer or serialize an execution-account
selector, webhook authorization, group IDs, offset overrides, tuning, filters, or
CloudEvents controls. The Integration's management credential is never used as a
fallback for a missing runtime credential.

Save/reopen uses flat `event_subscribe_trigger` parameters: `integration_id`,
`credential_id`, `topic`, and optional `input_schema`. Leaving the schema blank
omits it instead of inserting an empty schema or a default.

## Backend dependency and requirement differences

This frontend follows the existing backend contract, as agreed during implementation.
The Kafka Integration, Subscribe schema, and preflight implementation are included in this branch.
The existing backend accepts credential type **Kafka** and SASL_SSL.

Two intentional differences from the requested UI requirements:

- `credential_id` is required by this backend, including the preflight contract.
  The UI therefore requires a runtime credential instead of offering a
  security-mode-dependent omission.
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
fields to `POST /workflows/{workflow_id}/event-subscriptions/test`. It does not
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

- Affected UI tests: 353 passing across 14 files; mock API checks: 9 passing.
- New Kafka UI/helper coverage: 91.57% statements and 85.38% branches.
- Frontend `npm run check` and production build pass. Existing repository lint
  warnings remain; the Kafka files introduce no warnings.
- Browser verification against the isolated mock API covered creating the trigger,
  preflight, saving, reloading, reopening, and keyboard navigation. Integration,
  runtime credential, topic, and optional schema omission were preserved.
- Live Kafka/runtime verification requires a running deployment with Kafka configured.
