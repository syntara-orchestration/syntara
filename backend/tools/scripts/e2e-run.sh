#!/usr/bin/env bash
# Start the full E2E stack (mock Segment, database, Temporal, API server),
# run pytest, then tear everything down.
#
# Usage:
#   COMPOSE_CMD="uv run podman-compose -p syntara -f podman-compose.yml" \
#       ./tools/scripts/e2e-run.sh [pytest-args...]
#
# Environment:
#   COMPOSE_CMD           Full compose command with project/file args
#                         (default: uv run podman-compose -p syntara -f podman-compose.yml)
set -euo pipefail

COMPOSE_CMD="${COMPOSE_CMD:-uv run podman-compose -p syntara -f podman-compose.yml}"
MAKE="${MAKE:-make}"
PYTEST_ARGS=("$@")

# Execution Plane mode (make test-e2e-ep, or E2E_EP=1): start the EP services
# from this compose, register a local kind cluster as their dispatch target,
# and activate the EP-backed e2e tests (EP_API_URL et al.).
E2E_EP="${E2E_EP:-0}"
EP_IMAGE="${EP_IMAGE:-localhost/execution-plane:latest}"
EP_REPOSITORY="${EP_REPOSITORY:-../../syntara-execution-plane}"
EP_API_PORT="${EP_API_PORT:-8001}"
EP_KIND_CLUSTER="${EP_KIND_CLUSTER:-ep-kind}"
# Must match the EP API's EP_AO_JWT_ISSUER, which follows AO's jwt_issuer:
# APP_SERVER_PUBLIC_URL when set (backend/.env wins over the compose default)
# or the https://0.0.0.0:8000 fallback.
EP_JWT_ISSUER="${EP_AO_JWT_ISSUER:-$(grep -E '^APP_SERVER_PUBLIC_URL=' .env 2>/dev/null | tail -1 | cut -d= -f2- | cut -d'#' -f1 | tr -d '"' | xargs)}"
EP_JWT_ISSUER="${EP_JWT_ISSUER:-https://0.0.0.0:8000}"

# The Execution Plane services live behind the "execution-plane" compose
# profile: enabling the profile starts exactly the service set the EP e2e
# needs (db-init, migrate, api, worker) without enumerating them here.
EP_PROFILES=()
if [[ "${E2E_EP}" == "1" ]]; then
    EP_PROFILES=(--profile execution-plane)
    # podman-compose does not honor "${EP_API_PORT:-8001}" defaults in port
    # mappings (it falls back to the container port); export the variable so the
    # documented 8001 publish port is actually used.
    export EP_API_PORT
fi

# Follow the logs of every pod in the EP kind cluster while the tests run.
# Workload pods are deleted as soon as their Job completes, so dumping the
# logs after the fact (in cleanup) would see nothing: the logs must be
# captured live, pod by pod.
# Build the AO step images from a syntara-step-types checkout and import
# them into the kind cluster. Script-node dispatch resolves its workload
# image from the ExecutionPlanePlugin registry (seeded with
# quay.io/aap/ansible-automation-platform/ao-{python,bash}-rhel9:devel), and
# nothing publishes those images yet — without this import every dispatched
# node pod dies on ErrImagePull (401 from the registry).
load_step_images() {
    local step_types_repo="${STEP_TYPES_REPOSITORY:-../../syntara-step-types}"
    local node="${EP_KIND_CLUSTER}-control-plane"
    if ! podman container exists "${node}"; then
        echo "⚠️  No ${node} container; skipping the step image import" >&2
        return 0
    fi
    if [[ ! -f "${step_types_repo}/script-bash/Containerfile" ]]; then
        echo "⚠️  No syntara-step-types checkout at ${step_types_repo}; script nodes will fail" \
            "to pull quay.io/aap/.../ao-*-rhel9:devel unless the images are otherwise available" >&2
        return 0
    fi
    local image plugin_dir
    for image in ao-python-rhel9 ao-bash-rhel9; do
        case "${image}" in
            ao-python-rhel9) plugin_dir=script-python ;;
            ao-bash-rhel9) plugin_dir=script-bash ;;
        esac
        local full="quay.io/aap/ansible-automation-platform/${image}:devel"
        echo "📦 Building ${full} from ${step_types_repo}..."
        if ! podman build -q -f "${step_types_repo}/${plugin_dir}/Containerfile" \
            -t "${full}" "${step_types_repo}" > /dev/null; then
            echo "⚠️  Failed to build ${full}; script nodes needing it will fail" >&2
            continue
        fi
        # kind load is unreliable with the podman provider; import directly
        # into the node's containerd image store instead.
        if ! podman save "${full}" | podman exec -i "${node}" ctr --namespace=k8s.io images import - > /dev/null 2>&1; then
            echo "⚠️  Failed to import ${full} into ${node}" >&2
        fi
    done
}

start_kind_log_collector() {
    if ! kubectl --context "kind-${EP_KIND_CLUSTER}" get ns >/dev/null 2>&1; then
        echo "⚠️  No 'kind-${EP_KIND_CLUSTER}' kubeconfig context; skipping kind log collection"
        return 0
    fi
    local log_dir="/tmp/syntara-e2e-logs/kind"
    rm -rf "${log_dir}"
    KIND_LOG_DIR="${log_dir}" KIND_CONTEXT="kind-${EP_KIND_CLUSTER}" bash -c '
        declare -A followed=()
        while true; do
            # Only follow pods whose containers already exist: a failed
            # "kubectl logs -f" (Pending/ContainerCreating pod) would mark
            # them as followed forever. Completed pods are still followed:
            # "logs -f" dumps what is left and exits.
            while read -r ns name phase; do
                case "${phase}" in
                    Running|Succeeded|Failed|Completed) ;;
                    *) continue ;;
                esac
                [[ -n "${followed[${ns}/${name}]:-}" ]] && continue
                followed["${ns}/${name}"]=1
                mkdir -p "${KIND_LOG_DIR}/${ns}"
                kubectl --context "${KIND_CONTEXT}" -n "${ns}" logs -f --timestamps --prefix \
                    --all-containers "${name}" >> "${KIND_LOG_DIR}/${ns}/${name}.log" 2>/dev/null &
            done < <(kubectl --context "${KIND_CONTEXT}" get pods -A --no-headers 2>/dev/null \
                | awk "{print \$1, \$2, \$4}")
            # Poll fast: completed workload pods are garbage-collected within
            # seconds of their Job finishing.
            sleep 1
        done
    ' >/dev/null 2>&1 &
    KIND_LOG_COLLECTOR_PID=$!
    echo "📋 Recording kind cluster pod logs to ${log_dir}/ ..."
}

stop_kind_log_collector() {
    [[ -n "${KIND_LOG_COLLECTOR_PID:-}" ]] || return 0
    echo "📋 Capturing kind cluster state and events..."
    local log_dir="/tmp/syntara-e2e-logs/kind"
    kubectl --context "kind-${EP_KIND_CLUSTER}" get events -A --sort-by=.lastTimestamp \
        > "${log_dir}/events.log" 2>/dev/null || true
    kubectl --context "kind-${EP_KIND_CLUSTER}" get pods -A -o wide \
        > "${log_dir}/pods.txt" 2>/dev/null || true
    # Kill the kubectl followers before their parent: once the parent is
    # dead they get re-parented to PID 1 and pkill -P would miss them.
    pkill -P "${KIND_LOG_COLLECTOR_PID}" 2>/dev/null || true
    kill "${KIND_LOG_COLLECTOR_PID}" 2>/dev/null || true
    wait "${KIND_LOG_COLLECTOR_PID}" 2>/dev/null || true
    unset KIND_LOG_COLLECTOR_PID
}

cleanup() {
    echo "🧹 Stopping background services..."

    # Snapshot the kind cluster (events, pod table) before anything is torn
    # down, and stop the live pod log collector.
    stop_kind_log_collector

    # Save container logs before tearing down (useful for debugging failures).
    # Keep the kind/ subdirectory: it holds the logs recorded during the run.
    local log_dir="/tmp/syntara-e2e-logs"
    rm -f "${log_dir}"/*.log
    mkdir -p "$log_dir"
    echo "📋 Saving container logs to ${log_dir}/ ..."
    for container in $(podman ps -a --format '{{.Names}}' --filter "label=com.docker.compose.project" 2>/dev/null); do
        podman logs "$container" > "${log_dir}/${container}.log" 2>&1 || true
    done

    ${COMPOSE_CMD} --profile telemetry-e2e --profile mcp-scenarios ${EP_PROFILES[*]+"${EP_PROFILES[@]}"} down > /dev/null 2>&1 || true
}
trap cleanup EXIT

${MAKE} _deps-install-dev

# Fix SELinux context if running on SELinux-enabled system
if command -v chcon >/dev/null 2>&1 && getenforce 2>/dev/null | grep -qi enforcing; then
    echo "🔒 Fixing SELinux context for api_client..."
    chcon -R -t container_file_t src/api_client 2>/dev/null || true
fi

echo "🚀 Starting database first..."
${COMPOSE_CMD} --profile telemetry-e2e up -d --force-recreate database \
    > /tmp/syntara-e2e-infra.log 2>&1

echo "🚀 Starting remaining services..."
APP_SCRIPT_NODES_ENABLED=true \
APP_SEGMENT_WRITE_KEY=test-e2e-write-key \
APP_SEGMENT_ENDPOINT="http://mock-segment:9999" \
APP_SEGMENT_MAX_RETRIES=2 \
APP_SEGMENT_TIMEOUT=5 \
APP_COLLECTION_INTERVAL_SECONDS=10 \
APP_INTEGRATION_URL_ALLOWED_HOSTS='["mcp-server"]' \
# Bare up with profiles: every non-profiled service plus the active profiles
# (mock-segment, mcp-server-scenarios, and the Execution Plane set in EP mode).
# The UIs sit behind the "ui" profile so they stay down; no --force-recreate
# so the database container started above is not restarted (podman-compose
# still recreates containers whose configuration changed, and cleanup tears
# the stack down after each run anyway).
${COMPOSE_CMD} --profile telemetry-e2e --profile mcp-scenarios ${EP_PROFILES[*]+"${EP_PROFILES[@]}"} up -d \
    >> /tmp/syntara-e2e-infra.log 2>&1

echo "⏳ Waiting for mock Segment server..."
TRIES=0
until curl -sf "http://localhost:9999/health" 2>/dev/null | grep -q '"status":"ok"'; do
    sleep 1
    TRIES=$((TRIES + 1))
    if [[ $TRIES -ge 30 ]]; then
        echo "❌ Mock Segment server failed to start. Logs:"
        ${COMPOSE_CMD} --profile telemetry-e2e logs mock-segment 2>&1 | tail -10
        exit 1
    fi
done
echo "✅ Mock Segment server ready"

echo "⏳ Waiting for MCP scenario servers..."
TRIES=0
until [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${MCP_AUTH_PORT:-8766}/health" 2>/dev/null)" == "200" \
    && "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${MCP_FORBIDDEN_PORT:-8767}/health" 2>/dev/null)" == "403" ]]; do
    sleep 1
    TRIES=$((TRIES + 1))
    if [[ $TRIES -ge 60 ]]; then
        echo "❌ MCP scenario servers failed to start after 60s. Logs:"
        ${COMPOSE_CMD} --profile telemetry-e2e --profile mcp-scenarios logs mcp-server-scenarios 2>&1 | tail -20
        exit 1
    fi
done
echo "✅ MCP scenario servers ready"

echo "⏳ Waiting for Temporal to be ready..."
TRIES=0
until timeout 2 bash -c "echo > /dev/tcp/localhost/\${APP_TEMPORAL_PORT:-7233}" 2>/dev/null; do
    sleep 2
    TRIES=$((TRIES + 1))
    if [[ $TRIES -ge 60 ]]; then
        echo "❌ Temporal failed to start after 120s. Logs:"
        ${COMPOSE_CMD} --profile telemetry-e2e logs temporal 2>&1 | tail -20
        exit 1
    fi
done
echo "✅ Infrastructure ready"

echo "⏳ Waiting for API server to be ready..."
TRIES=0
until curl -sf --cacert .secrets/certs/ca.pem https://localhost:8000/healthz/ready 2>/dev/null | grep -q '"status":"ready"'; do
    sleep 1
    TRIES=$((TRIES + 1))
    if [[ $TRIES -ge 60 ]]; then
        echo "❌ API server failed to start after 60s"
        ${COMPOSE_CMD} logs syntara 2>&1 | tail -20
        exit 1
    fi
done
echo "✅ API server is ready"

echo "🔧 Setting admin password..."
uv run python tools/set_admin_password.py < .secrets/admin-password

if [[ "${E2E_EP}" == "1" ]]; then
    # The EP registration tool drives a local kind cluster and needs kind/kubectl
    # on PATH. Fall back to the usual local spots (~/aap-dev/bin, or an aap-dev
    # checkout next to this repository).
    if ! command -v kind >/dev/null 2>&1; then
        _REPO_PARENT=$(cd ../.. && pwd)
        for _candidate in "${HOME}/aap-dev/bin" "${_REPO_PARENT}/aap-dev/bin"; do
            if [[ -x "${_candidate}/kind" ]]; then
                export PATH="${_candidate}:${PATH}"
                break
            fi
        done
    fi
    command -v kind >/dev/null 2>&1 || {
        echo "❌ 'kind' is required for the Execution Plane e2e mode (install it or add it to PATH)" >&2
        exit 1
    }

    echo "🛫 Bringing up the Execution Plane..."
    if ! podman image exists "${EP_IMAGE}"; then
        echo "📦 Building the Execution Plane image from ${EP_REPOSITORY}..."
        podman build -f "${EP_REPOSITORY}/Containerfile" -t "${EP_IMAGE}" "${EP_REPOSITORY}"
    fi

    echo "⏳ Waiting for EP API server..."
    TRIES=0
    until curl -sf --cacert .secrets/certs/ca.pem "https://localhost:${EP_API_PORT}/healthz/ready" 2>/dev/null | grep -q '"status":"ready"'; do
        sleep 2
        TRIES=$((TRIES + 1))
        if [[ $TRIES -ge 45 ]]; then
            echo "❌ EP API server failed to start after 90s. Logs:"
            ${COMPOSE_CMD} logs execution-plane-api execution-plane-migrate 2>&1 | tail -30
            exit 1
        fi
    done
    echo "✅ EP API server is ready"

    echo "🌐 Registering the ${EP_KIND_CLUSTER} kind cluster as the EP dispatch target..."
    BACKEND_DIR=$(pwd)
    (
        cd "${EP_REPOSITORY}"
        EP_API_URL="https://localhost:${EP_API_PORT}" \
        EP_API_CA_FILE="${BACKEND_DIR}/.secrets/certs/ca.pem" \
        EP_AO_JWT_PRIVATE_KEY_FILE="${BACKEND_DIR}/.secrets/jwt-primary.pem" \
        EP_AO_JWT_ISSUER="${EP_JWT_ISSUER}" \
        uv run python -m tools.deploy_kind_execution_target \
            --cluster-name "${EP_KIND_CLUSTER}" \
            --api-url "https://localhost:${EP_API_PORT}" \
            --ao-api-url "https://localhost:8000" \
            --create-ao-credential \
            --ao-admin-password-file "${BACKEND_DIR}/.secrets/admin-password" \
            --ao-insecure \
            --wait-for-api 60
    )

    load_step_images

    start_kind_log_collector
fi

API="https://localhost:8000/api/v1"

# Get admin session token
ADMIN_TOKEN=$(curl -sf --cacert .secrets/certs/ca.pem "$API/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"admin\", \"password\": \"$(cat .secrets/admin-password)\"}" | python3 -c "
import sys, json
print(json.load(sys.stdin)['access_token'])
")

curl -sf --cacert .secrets/certs/ca.pem -X PATCH "$API/settings/metrics.perf_test_mode" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value": true}'

SEGMENT_SERVER_URL="http://localhost:9999" \
APP_SCRIPT_NODES_ENABLED=true \
APP_BASE_URL="${APP_BASE_URL:-https://localhost:8000}" \
APP_ADMIN_PASSWORD_PATH=.secrets/admin-password \
EP_API_URL="${EP_API_URL:-$([[ "${E2E_EP}" == "1" ]] && echo "https://localhost:${EP_API_PORT}")}" \
EP_API_CA_FILE="${EP_API_CA_FILE:-$([[ "${E2E_EP}" == "1" ]] && echo ".secrets/certs/ca.pem")}" \
EP_AO_JWT_PRIVATE_KEY_FILE="${EP_AO_JWT_PRIVATE_KEY_FILE:-$([[ "${E2E_EP}" == "1" ]] && echo ".secrets/jwt-primary.pem")}" \
EP_AO_JWT_ISSUER="${EP_JWT_ISSUER}" \
uv run pytest "${PYTEST_ARGS[@]}"
