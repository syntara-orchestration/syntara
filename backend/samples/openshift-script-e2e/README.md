# Script workload on OpenShift

These are example API seed payloads, not an automatic seeder. The hostname,
namespace, and UUIDs are dummy values. Do not apply them to an existing
installation without replacing them and confirming the development target.
No tokens, passwords, or cluster credentials belong in these files.

The integration branch combines the OpenShift integration work with the
Execution Plane dispatch implementation. Both source branches remain unchanged.
Temporal submits a `WorkExecute` command to EP with the selected execution target;
EP launches the SDK-native script container and reports completion back to AO.
Scripts are not executed inside the Temporal worker.

## Deployment configuration

Use the existing AO and EP deployment procedure. On the Temporal worker set:

```sh
APP_SCRIPT_NODES_ENABLED=true
APP_EP_API_URL=https://execution-plane.example.com
APP_NODE_CONTAINER_IMAGES='{"script":"quay.io/pjohari/syntara-node-script@sha256:a18617479a99fb46bd62f4f8c712eef764f73410adf2718bc2c00e0f28cf1280"}'
```

The target namespace must be able to pull the image; configure its normal
registry pull credentials if the repository is private.

The EP URL above is a placeholder. Configure the existing AO/EP service
authentication, trusted CA certificates, callback URL, and callback identity
allowlist for the real deployment. The script image is Linux AMD64 and exposes
`syntara.script.script` through the SDK ContainerService gRPC protocol.

## Database preparation and seed order

1. Run the normal Alembic upgrade on the development AO database. The combined
   history already provides OpenShift integration and EP synchronization tables;
   no separate schema or direct SQL changes are needed for the script image.
2. Create an HTTP Bearer Token management credential using the normal AO
   credential API or UI. Store its secret there, never in a seed payload. The
   credential needs workload permissions in the approved namespace.
3. Replace the URL, namespace, and management credential UUID in `integration.json`.
   Supply the real cluster CA when it is not trusted by the deployment. Submit
   that payload to `POST /api/v1/integrations` using an authorized AO account.
4. Wait for AO's integration-to-EP synchronization to report success and verify
   the EP cluster endpoint and namespace. Creating an integration does not deploy
   EP itself. The target API uses the installed cluster; confirm it is the intended
   OpenShift cluster before creating a target. This branch requires exactly one
   registered EP cluster. Use a dedicated test deployment; do not add a second
   cluster to an existing installation for this example.
5. Replace the namespace in `execution-target.json`. Submit it to
   `POST /api/execution_plane/v1/execution_targets` and record the returned UUID.
   The example does not change the deployment's default target.
6. Replace the project and execution target UUIDs in `workflow.json`. Submit it
   to `POST /api/v1/workflows`. Start an execution with `POST /api/v1/executions`
   using the returned workflow UUID, `trigger_node_id: "trigger"`, and empty
   `input_data`.

Seed through the APIs so encryption, permissions, integration synchronization,
and audit hooks run. Check for existing named test resources before creating
another set, and delete only the resources created for this test afterward.

## End-to-end verification

The existing live test checks both AO workflow completion and the corresponding
claimed/completed EP work item with the same unique output marker. Select the
approved target explicitly rather than relying on the default:

```sh
E2E_EXECUTION_TARGET_ID='<actual-target-uuid>' \
  uv run pytest tests/e2e/execution_plane/test_hello_world_workflow.py -v
```

Run from `backend/` with the existing E2E fixtures' AO login, EP API, and JWT/CA
configuration. Missing infrastructure causes the optional live suite to skip;
a skipped test is not proof of OpenShift execution. Confirm the launched workload
uses the pinned image in the selected namespace. Live deployment, seeding, and
execution remain pending until a development cluster and AO deployment are chosen.
