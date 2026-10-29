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
NODE_IMAGE="${NODE_IMAGE:-quay.io/ahetheri/syntara-node-script:migration-test}"
# Must match the EP API's EP_AO_JWT_ISSUER, which follows AO's jwt_issuer:
# APP_SERVER_PUBLIC_URL when set (backend/.env wins over the compose default)
# or the https://0.0.0.0:8000 fallback.
EP_JWT_ISSUER="${EP_AO_JWT_ISSUER:-$(grep -E '^APP_SERVER_PUBLIC_URL=' .env 2>/dev/null | tail -1 | cut -d= -f2- | cut -d'#' -f1 | tr -d '"' | xargs)}"
EP_JWT_ISSUER="${EP_JWT_ISSUER:-https://0.0.0.0:8000}"

EP_SERVICES=()
if [[ "${E2E_EP}" == "1" ]]; then
    EP_SERVICES=(execution-plane-db-init execution-plane-migrate execution-plane-api execution-plane-worker)
    # podman-compose does not honor "${EP_API_PORT:-8001}" defaults in port
    # mappings (it falls back to the container port); export the variable so the
    # documented 8001 publish port is actually used.
    export EP_API_PORT
fi

cleanup() {
    echo "🧹 Stopping background services..."

    # Save container logs before tearing down (useful for debugging failures)
    local log_dir="/tmp/syntara-e2e-logs"
    rm -rf "$log_dir"
    mkdir -p "$log_dir"
    echo "📋 Saving container logs to ${log_dir}/ ..."
    for container in $(podman ps -a --format '{{.Names}}' --filter "label=com.docker.compose.project" 2>/dev/null); do
        podman logs "$container" > "${log_dir}/${container}.log" 2>&1 || true
    done

    ${COMPOSE_CMD} --profile telemetry-e2e down > /dev/null 2>&1 || true
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
${COMPOSE_CMD} --profile telemetry-e2e --profile mcp-scenarios up -d --force-recreate temporal temporal-worker temporal-background-worker mock-segment mcp-server mcp-server-scenarios syntara ${EP_SERVICES[*]+"${EP_SERVICES[@]}"} \
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
        uv run python tools/deploy_kind_execution_target.py \
            --cluster-name "${EP_KIND_CLUSTER}" \
            --api-url "https://localhost:${EP_API_PORT}" \
            --ao-api-url "https://localhost:8000" \
            --create-ao-credential \
            --ao-admin-password-file "${BACKEND_DIR}/.secrets/admin-password" \
            --ao-insecure \
            --wait-for-api 60
    )

    echo "📦 Pre-pulling ${NODE_IMAGE} on the ${EP_KIND_CLUSTER} node..."
    if podman exec "${EP_KIND_CLUSTER}-control-plane" crictl pull "${NODE_IMAGE}"; then
        echo "✅ Node image pre-pulled"
    else
        echo "⚠️  Pre-pull failed; the Job will pull ${NODE_IMAGE} itself at dispatch time"
    fi
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
