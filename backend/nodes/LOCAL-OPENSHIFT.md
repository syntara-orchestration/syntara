# Local Syntara with OpenShift workers

## Development instance

The migration branch is `feat/sdk-node-containers`, in the `syntara-sdk-nodes`
worktree. Its local services use the Compose project `syntara-sdk-nodes` and
separate data volumes. Configuration is in the ignored root and `backend/.env`
files; generated keys and the admin password are under `backend/.secrets/`.

| Service | Address |
| --- | --- |
| Syntara UI | http://localhost:5175 |
| Syntara API | https://localhost:8002 |
| Temporal UI | http://localhost:8083 |
| PostgreSQL | localhost:5434 |
| Redis | localhost:6381 |
| Temporal | localhost:7235 |
| Local S3 fixture | http://localhost:5557 |

Sign in as `admin` using the password in `backend/.secrets/admin-password`.
The API uses the generated development CA at `backend/.secrets/certs/ca.pem`.
Vite proxies API calls to it. Secrets are not included in this runbook.

The Syntara project is `sdk-node-migration`, with the project-scoped OpenShift
integration `ep-dev-workers`. The integration targets
`https://api.pde-ao-03.cjjv.p3.openshiftapps.com:443`, namespace `ep-dev-workers`.
Its management credential, `ep-dev-workers-dispatcher`, belongs to service account
`ep-dev-workers:syntara-sdk-dispatcher` and is encrypted by Syntara. The Role permits
pod creation, reading, deletion and port-forwarding within that namespace.

Five gRPC server images were built in the namespace with tag `grpc-3d560406`:

```text
image-registry.openshift-image-registry.svc:5000/ep-dev-workers/syntara-node-http-request
image-registry.openshift-image-registry.svc:5000/ep-dev-workers/syntara-node-agent
image-registry.openshift-image-registry.svc:5000/ep-dev-workers/syntara-node-script
image-registry.openshift-image-registry.svc:5000/ep-dev-workers/syntara-node-aap-job
image-registry.openshift-image-registry.svc:5000/ep-dev-workers/syntara-node-aap-workflow
```

Both `.env` files pin the images by digest. Non-secret resource IDs, image references
and credential expiry are recorded in `backend/.secrets/node-migration.json`.
The gRPC BuildConfigs have names ending in `-grpc-3d560406`. Earlier stdin images
remain available under their previous tags, but the current adapter requires gRPC.

Every invocation creates a fresh pod. The worker calls `Health`, then `Execute`
over gRPC on port 50051 through the authenticated Kubernetes port-forward API.
Progress and the terminal result return on the same RPC stream; `Cancel` requests
cooperative cleanup. The server binds to pod loopback and needs no Service or Route.

## Restart

From the worktree root, start the infrastructure using the existing Compose file:

```bash
docker compose --env-file .env -p syntara-sdk-nodes -f podman-compose.yml \
  up -d database redis temporal temporal-ui moto
```

This machine uses Docker because its Podman VM is stopped and `podman-compose`
cannot parse the installed Docker version when used as its runtime. On a working
Podman installation, use `uv run podman-compose` from `backend/` instead.

Start these processes in separate terminals. For the API, explicitly select the
backend environment and database so the separate EP migration project uses the
same environment and the isolated database:

```bash
cd backend
UV_PROJECT_ENVIRONMENT="$PWD/.venv" \
  APP_DATABASE_URL=postgresql+asyncpg://admin:admin@localhost:5434/syntara_api \
  APP_S3_ENDPOINT_URL=http://localhost:5557 APP_S3_BUCKET_NAME=syntara-files \
  make dev
```

```bash
cd backend
make worker-run WORKER_BASE_URL=https://localhost:8002/api/v1
```

```bash
cd backend
make background-worker-run WORKER_BASE_URL=https://localhost:8002/api/v1
```

```bash
cd frontend/packages/syntara-ui
VITE_API_URL=https://localhost:8002 npm exec -- vite --host 127.0.0.1 --port 5175 --strictPort
```

Stop these processes with Ctrl-C. Stop only this instance's infrastructure with:

```bash
docker compose --env-file .env -p syntara-sdk-nodes -f podman-compose.yml stop
```

## Refresh the management credential

The initial service-account token expires on **2026-09-30 at 13:13:37 UTC**
(14:13:37 in Dublin). Generate
a replacement using an authorized cluster login:

```bash
oc create token syntara-sdk-dispatcher -n ep-dev-workers --duration=24h
```

Update the token field of `ep-dev-workers-dispatcher` in the local Syntara UI and
validate the `ep-dev-workers` integration. Keep the token out of source files,
image layers and pod specifications. Credential changes are resolved on the next
activity invocation; no worker restart is needed.

## Verification and remaining connections

All five images passed real pod startup and gRPC execution tests under
OpenShift's restricted security policy, using an HTTP fixture for HTTP, AAP and
Agent Orchestrator responses. Python, Bash, script failure output, timeout,
cancellation and missing-image cleanup were also exercised. Execution pods and
the disposable fixture were removed; image builds and the dispatcher identity remain.

The saved `sdk-remote-http-python-bash` workflow completed through the local API,
Temporal worker and three separate remote pods. Successful execution:
`432d88a4-7dbe-483d-9403-8338f6a43922`. Its final Bash output was
`Remote containers: Sample Slide Show`.

HTTP, script and both AAP routes are enabled in the local configuration. AAP
workflows still need an AAP integration and credentials for a real controller.
Agent container routing remains disabled locally until Agent Orchestrator has an
address reachable from the cluster and its TLS client Secret is provisioned in
`ep-dev-workers`. The local API contains Agent Orchestrator, but the cluster cannot
use its loopback address. Set `APP_NODE_CONTAINER_AGENT_BASE_URL`, provision the
Secret described in the main README, add `agentic` to the enabled types, and restart
the local API/workers when that connection is available.

The agent image's dispatch/cancel behavior passed fixture tests. Real model execution,
the remote agent-to-local-AO connection, and production AAP jobs are not certified
by the fixture tests.

## Automated checks

The node workspace's 43 tests, 121 focused routing/workflow tests, backend and node
mypy checks, Pyrefly, and Ruff checks passed. The gRPC tests cover real TCP calls,
streamed progress, credential redaction, exact JSON integers, cancellation, dropped
connections, deadlines, duplicate execution rejection and mutual TLS. All five
locally built images also passed gRPC smoke tests with an arbitrary UID and a
read-only filesystem. The full repository gates are not
clean: `make test-all` reports nested `pytest_plugins` collection errors; the unit
suite has two telemetry assertions expecting a different `container_image_version`;
and `make lint` reaches a frontend ESLint package-path error. Those failures are
outside the migrated executors. Formatter-only changes to unrelated frontend
examples were removed from this branch.
