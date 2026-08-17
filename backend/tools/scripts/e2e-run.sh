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
${COMPOSE_CMD} --profile telemetry-e2e --profile mcp-scenarios up -d --force-recreate temporal temporal-worker temporal-background-worker mock-segment mcp-server mcp-server-scenarios syntara \
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
until curl -sf --cacert .secrets/certs/ca.pem https://localhost:8000/health 2>/dev/null | grep -q '"status":"healthy"'; do
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
uv run pytest "${PYTEST_ARGS[@]}"
