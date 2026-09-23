# Cold-start OpenShift development

## Prerequisites

- `oc` logged into the target cluster
- permission to create `ep-dev-workers` and namespace-scoped RBAC
- Podman (or Docker Compose for local development) and `uv`
- a worker image whose main process remains alive with stdin open and whose
  configured exec command reads one JSON line and writes one JSON line

The detected ROSA API endpoint for this environment is
`https://api.pde-ao-03.cjjv.p3.openshiftapps.com:443`. Use the endpoint returned
by `oc whoami --show-server`; ROSA does not require changing it to port 6443.

## One-time setup

From the repository root:

```bash
make install
make setup
make -C backend ep-openshift-setup
make -C backend ep-register-dev-target
```

`ep-openshift-setup` applies
`execution-plane/deploy/openshift-setup.yaml`, requests a 24-hour bound token,
stores it at `backend/.secrets/execution-plane/openshift-token`, and verifies
the required permissions. Rerun it before expiry to rotate the token. Override
the requested lifetime with `EP_OPENSHIFT_TOKEN_DURATION` if cluster policy
allows it.

For the private Quay executor images, place the robot's token in
`backend/.secrets/execution-plane/quay-robot-token` with mode `0600` before
running `ep-openshift-setup`. The script creates or updates the
`quay-executor-pull` Secret and links it to the default ServiceAccount in the
dedicated worker namespace. The default robot username is
`ahetheri+execution_plane_robot`; set `EP_QUAY_ROBOT_USERNAME` if using another
robot. The token file and generated Secret are not committed.

`ep-register-dev-target` applies the execution-plane Alembic migrations and
upserts `dev-openshift-cluster` using
`execution-plane/deploy/register-dev-target.sql`. The target record contains a
file reference, never the token value.

After the local API is running, create the Syntara integration and encrypted
management credential. The `default` Syntara project owns that credential;
this is separate from the OpenShift worker namespace.

```bash
(cd backend && uv run python execution-plane/scripts/register-openshift-integration.py \
  --endpoint "$(oc whoami --show-server)" \
  --insecure-local-api-tls)
```

The script prints the integration ID and a link under Syntara
**Configuration → Integrations**. It checks that the ServiceAccount can list
pods in `ep-dev-workers`. Rerun setup and registration after token rotation.
The Execution Plane target still holds only a token-file reference.

To route existing Temporal HTTP and Script workflow nodes through this
integration, start the workers with these environment values:

```bash
export APP_SCRIPT_NODES_ENABLED=true
export APP_EP_COLD_START_WORKFLOW_NODES=true
export APP_EP_OPENSHIFT_INTEGRATION_ID='<ID printed by registration script>'
docker compose -f podman-compose.yml up -d temporal-worker execution-plane-worker
```

The image settings default to the AMD64 HTTP and Python images from the
stdin-executor branch. The Bash image is
`quay.io/ahetheri/script-bash-executor:amd64`, but the Quay robot must first
be granted Read access to its repository; then set
`APP_EP_SCRIPT_BASH_EXECUTOR_IMAGE` to that image. Authenticated HTTP nodes
and requests with sensitive-looking header or query names stay on the existing
local HTTP path: resolved credentials are not copied into plaintext Execution
Plane WorkItems. A missing or disabled execution target fails the activity.

Build and restart the EP image after code changes:

```bash
make -C backend build-images
make services-up
```

The `:dev` HTTP image is ARM64-only, while this ROSA cluster is AMD64. Use
`quay.io/ahetheri/http-executor:amd64` for HTTP tasks. The Python script image
is `quay.io/ahetheri/script-python-executor:amd64`; its repository is private
and requires an image-pull Secret in `ep-dev-workers`.

## Submit a task

`POST /api/execution_plane/v1/submit` requires the Syntara `work_item:create`
permission. A development request looks like:

```json
{
  "target_selector": {
    "environment": "development",
    "execution-mode": "cold-start",
    "platform": "openshift"
  },
  "task_definition": {
    "image": "quay.io/ahetheri/http-executor:amd64",
    "pod_command": ["/bin/sh", "-c", "sleep infinity"],
    "command": ["python", "-m", "syntara.http_executor"],
    "input": {
      "url": "https://api.github.com",
      "method": "GET"
    },
    "timeout_seconds": 120,
    "image_pull_policy": "Always"
  }
}
```

The response is HTTP 202 with the queued `WorkItem`. Inspect progress with
`GET /api/execution_plane/v1/work_items` or query
`execution_plane.work_items`.

The HTTP and script executor images use different JSON commands. For a Python
script task, use `quay.io/ahetheri/script-python-executor:amd64`, set
`pod_command` to `["/usr/bin/python3", "-c", "import time; time.sleep(3600)"]`,
set `command` to `["/usr/local/bin/script-executor", "--once"]`, and set
`input` to `{"code":"print('hello from OpenShift')"}`. The Python process keeps
the pod alive for the Kubernetes exec call; the runner executes the code once.

## Live verification

The integration test is skipped unless all live-environment values are set:

```bash
export EP_E2E_API_URL=https://localhost:8000
export EP_E2E_API_TOKEN='<syntara-access-token>'
export EP_E2E_DATABASE_URL='postgresql://admin:admin@localhost:5432/syntara_api'
export EP_E2E_KUBECONFIG="$KUBECONFIG"
uv run --directory backend pytest execution-plane/tests/test_cold_start.py -v
```

The test submits through `/submit`, observes the labelled OpenShift pod, checks
the persisted terminal result, and verifies pod deletion.

To verify the first-class Syntara integration through a real Temporal workflow,
run the dedicated HTTP → Python fixture after setting the integration ID above:

```bash
docker compose -f podman-compose.yml run --rm --no-deps --entrypoint python \
  -e APP_EP_COLD_START_WORKFLOW_NODES=true \
  -e APP_EP_OPENSHIFT_INTEGRATION_ID="$APP_EP_OPENSHIFT_INTEGRATION_ID" \
  -e APP_SCRIPT_NODES_ENABLED=true \
  -v "$PWD/backend/execution-plane/scripts/verify-workflow-integration.py:/tmp/verify-workflow-integration.py:ro" \
  -v "$PWD/backend/tests/integration/workflows/examples/ep/openshift-http-script.json:/tmp/openshift-http-script.json:ro" \
  temporal-worker /tmp/verify-workflow-integration.py /tmp/openshift-http-script.json
```

The verifier asserts HTTP 200 and the Python script's computed JSON result,
`{"value": 18}`. Both WorkItems should be completed and no ephemeral pods
should remain in `ep-dev-workers` afterward. Their pods are intentionally
short-lived, so the OpenShift UI may show no pods between runs.

## Credential rotation and cleanup

The generated token is short-lived by design. Rerunning
`ep-openshift-setup` replaces the local file; restart
`execution-plane-worker` so new API clients use it. To revoke execution
permissions without deleting the worker namespace, delete the RoleBinding:

```bash
oc delete rolebinding execution-plane-executor -n ep-dev-workers
```
