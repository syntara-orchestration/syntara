# Kafka Publish in the workflow builder

Choose **Add step → Action → Kafka Publish**. The Action picker lists Kafka
Publish, REST API, and Script in that order. Kafka Publish uses the Kafka logo
in the picker, editor header, and workflow canvas, with the description
“Publish a structured message to a Kafka topic.”

The Action description is “Run scripts, make API calls, or invoke another
published workflow.” This grouping preserves Kafka Publish's own configuration
form and `kafka_publish` workflow node type. Existing workflow definitions
continue to open directly in the Kafka Publish editor.

In Parameters, select an **Integration**, then choose **Set up connection** to
select the runtime Kafka credential. Selection collapses to the credential name
with a **Change** action. **Cancel** closes the picker without changing the
selection. Changing the Integration clears the credential and closes setup.
Credential setup is hidden until an Integration is selected. Every connection
mode requires a runtime Kafka credential. SASL_SSL needs username and password;
SSL and opted-in PLAINTEXT can use a Kafka credential with empty inputs. Omitted
or null credential references prevent saving the action configuration. The
Integration's management credential is never substituted. Integration choices
show their broker addresses and validation status. Set the **Target topic**
below the connection controls.

## Tests

From the repository root, install dependencies before running checks:

```bash
make install
```

Run the unit and component integration tests for registration, picker navigation,
copy, ordering, icon identity, keyboard access, and accessibility:

```bash
npm --prefix frontend/packages/syntara-ui run vitest -- \
  src/routes/builder/AddNodePanel.test.tsx \
  src/routes/builder/AddNodePanel.kafkaPublish.test.tsx \
  src/routes/builder/registry/nodes/registerActionNode.test.ts \
  src/routes/builder/registry/nodes/registerKafkaPublishNode.test.ts \
  src/routes/builder/node-forms/KafkaPublishNodeForm.test.tsx \
  src/routes/builder/node-forms/kafkaPublishFormSchema.test.ts \
  src/routes/builder/node-forms/KafkaCredentialConnection.test.tsx \
  src/routes/builder/components/CredentialSelector.test.tsx \
  src/routes/builder/components/IntegrationSelector.test.tsx \
  src/routes/configuration/credentials/form/CredentialTypeHelp.test.tsx \
  src/routes/workflows/canvas/nodeTypeColors.test.ts \
  src/routes/workflows/canvas/nodes/nodeIconResolver.test.ts \
  src/routes/workflows/canvas/nodes/renderNodeIcon.test.tsx
```

Run the browser workflow scenario with the mock API and UI started automatically:

```bash
npm --prefix frontend/packages/syntara-ui run e2e -- e2e/kafka-publish.spec.ts
```

The live scenario requires a running backend and Temporal worker, the root Compose
Kafka SASL/TLS fixture, and a UI connected to that backend. With those services
ready, run:

```bash
SYNTARA_E2E_SKIP_WEB_SERVER=1 \
SYNTARA_E2E_BASE_URL=http://localhost:5173 \
SYNTARA_E2E_KAFKA_PUBLISH_LIVE=1 \
npm --prefix frontend/packages/syntara-ui run e2e -- e2e/kafka-publish-live.spec.ts
```

The live test still verifies the saved workflow and exact Kafka payload, key,
and ordered headers through the real worker.
