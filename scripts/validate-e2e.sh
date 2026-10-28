#!/usr/bin/env bash
# validate-e2e.sh — bring up and validate the full plugin-marketplace →
# Execution Plane E2E stack on a single host.
#
# Phases (all idempotent — safe to re-run):
#   1. prerequisites and configuration
#   2. poc-registry on the kind network
#   3. Execution Plane stack + kind execution target
#   4. credential-resolution stub (host process, pidfile)
#   5. kind node prep: containerd mirror + pre-pull the step image
#   6. syntara stack with APP_EXECUTION_PLANE_ENABLED=true
#   7. validate: trigger the workflow and assert stdout "2"
#
# Usage:
#   scripts/validate-e2e.sh              # full bring-up + validation
#   scripts/validate-e2e.sh --check      # verify only (no mutation)
#   scripts/validate-e2e.sh --skip-stack # validate against a running stack
#
# Environment overrides:
#   SYNTARA_DIR       (default: this script's repo root)
#   EP_DIR            (default: ../syntara-execution-plane)
#   STEP_IMAGE        (default: the digest-pinned script-step image)
#   WORKFLOW_ID       (default: the step-type demo workflow)
#   TRIGGER_NODE_ID   (default: its manual trigger node)
#   EXPECTED_STDOUT   (default: empty — only require a completed EP step
#                      with return_code 0; set e.g. EXPECTED_STDOUT="2" to
#                      also assert the exact stdout)

set -euo pipefail

# --- configuration -----------------------------------------------------------

SYNTARA_DIR="${SYNTARA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
EP_DIR="${EP_DIR:-$(cd "$SYNTARA_DIR/.." && pwd)/syntara-execution-plane}"
STEP_IMAGE="${STEP_IMAGE:-localhost:5000/syntara-script-step@sha256:996f8effe4c56d61f24e4ed9a8a4dff5a9fc1b070b2d3df4dd9c9f7b56308986}"
WORKFLOW_ID="${WORKFLOW_ID:-65a88c64-ded2-45a0-9f9c-15d3472029fd}"
TRIGGER_NODE_ID="${TRIGGER_NODE_ID:-activity_7ed345ed_8a73_441a_8761_fad0b6989529}"
EXPECTED_STDOUT="${EXPECTED_STDOUT:-}"
KIND_NODE="ep-kind-control-plane"
KIND_NETWORK="kind"
EP_NETWORK="syntara-execution-plane_default"
STUB_PORT=8444
CHECK_ONLY=0
SKIP_STACK=0

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --skip-stack) SKIP_STACK=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[1;32m[e2e]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[e2e]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[e2e]\033[0m FAIL: %s\n' "$*"; exit 1; }

# Wait until a command succeeds, or fail with a message.
wait_for() {
  local desc="$1" timeout="${2:-120}" shift_shift=2
  local deadline=$((SECONDS + timeout))
  until "${@:3}" >/dev/null 2>&1; do
    [ "$SECONDS" -ge "$deadline" ] && fail "timeout waiting for: $desc"
    sleep 3
  done
  log "ready: $desc"
}

# --- phase 1: prerequisites ---------------------------------------------------

log "phase 1: prerequisites"
[ -d "$EP_DIR" ] || fail "EP repo not found at $EP_DIR (set EP_DIR)"
for tool in podman docker kubectl uv uvx; do
  command -v "$tool" >/dev/null || fail "missing tool: $tool"
done

# The podman twin of the kind cluster is a trap: kubectl and the EP target
# talk to the docker one, and node fixes applied to the podman one vanish.
if podman ps -a --format '{{.Names}}' | grep -qx "$KIND_NODE" && \
   ! docker ps --format '{{.Names}}' | grep -qx "$KIND_NODE"; then
  # Podman node exists but the docker one does not — invert of the supported
  # layout; refuse rather than guess.
  warn "kind node '$KIND_NODE' exists only in podman (expected docker)."
  warn "Delete it or recreate the cluster with docker, then re-run."
  fail "unsupported cluster layout"
fi
if podman ps -a --format '{{.Names}}' | grep -qx "$KIND_NODE"; then
  if [ "$CHECK_ONLY" -eq 1 ]; then
    warn "podman twin of '$KIND_NODE' still exists (confusion risk; consider deleting)"
  else
    warn "removing stale podman twin of '$KIND_NODE'"
    podman rm -f "$KIND_NODE" >/dev/null 2>&1 || true
  fi
fi

kubectl config use-context kind-ep-kind >/dev/null 2>&1 || fail "kubectl context kind-ep-kind not found"

if [ "$CHECK_ONLY" -eq 1 ]; then
  log "check mode: verifying an already-running stack (no changes)"
fi

# --- phase 2: poc-registry ----------------------------------------------------

log "phase 2: poc-registry on network $KIND_NETWORK"
if [ "$CHECK_ONLY" -eq 0 ]; then
  REGISTRY_DATA=$(podman inspect poc-registry --format '{{range .Mounts}}{{.Source}}{{end}}' 2>/dev/null || true)
  if [ -z "$REGISTRY_DATA" ]; then
    warn "poc-registry missing or has no volume; recreating it loses pushed images"
    podman rm -f poc-registry >/dev/null 2>&1 || true
    fail "poc-registry not found — recreate it with its data volume first (see docs)"
  fi
  # Attach to the kind network if not already attached (pasta containers
  # cannot be attached; recreate with the network and the published port).
  if ! podman inspect poc-registry --format '{{json .NetworkSettings.Networks}}' | grep -q "\"$KIND_NETWORK\""; then
    warn "poc-registry not on network '$KIND_NETWORK' — recreating attached to it"
    podman rm -f poc-registry >/dev/null
    podman run -d --name poc-registry --network "$KIND_NETWORK" -p 5000:5000 \
      -v "$REGISTRY_DATA:/var/lib/registry" docker.io/library/registry:2 >/dev/null
  fi
fi
wait_for "registry HTTP API" 30 curl -sf http://localhost:5000/v2/ -o /dev/null

# --- phase 3: Execution Plane + kind target ------------------------------------

log "phase 3: execution plane stack"
if [ "$CHECK_ONLY" -eq 0 ] && [ "$SKIP_STACK" -eq 0 ]; then
  (cd "$EP_DIR" && uvx podman-compose up -d >/dev/null)
fi
wait_for "EP API healthz" 60 curl -sk https://127.0.0.1:8001/healthz/ready -o /dev/null

# Register the kind cluster as an execution target (idempotent upsert).
if [ "$CHECK_ONLY" -eq 0 ]; then
  TARGETS=$(cd "$EP_DIR" && uv run python - <<'PY'
from execution_plane.work_item_client import ep_request, ep_service_token, default_api_url
import sys
token = ep_service_token()
status, body = ep_request("GET", default_api_url() + "/v1/execution-targets", token)
targets = body.get("resources", []) if isinstance(body, dict) else []
active = [t for t in targets if t.get("status") == "active"]
sys.exit(0 if active else 1)
PY
  ) || TARGETS=""
  if [ -z "$TARGETS" ]; then
    log "registering kind execution target (deploy_kind_execution_target.py)"
    (cd "$EP_DIR" && uv run python tools/deploy_kind_execution_target.py \
      --create-ao-credential --ao-insecure \
      --ao-api-url https://localhost:8000 \
      --ao-admin-password-file "$SYNTARA_DIR/backend/.secrets/admin-password" >/dev/null)
  else
    log "execution target already active"
  fi
fi

# --- phase 4: credential-resolution stub ---------------------------------------

log "phase 4: credential-resolution stub (port $STUB_PORT)"
STUB_PIDFILE="/tmp/syntara-credential-stub.pid"
if ! curl -sk "https://localhost:$STUB_PORT/healthz" -o /dev/null 2>/dev/null; then
  [ "$CHECK_ONLY" -eq 1 ] && fail "credential stub not running (start it or drop --check)"
  log "starting stub"
  (cd "$EP_DIR" && nohup uv run python tools/credential_resolution_stub.py \
    > /tmp/syntara-credential-stub.log 2>&1 & echo $! > "$STUB_PIDFILE")
fi
wait_for "credential stub healthz" 30 curl -sk "https://localhost:$STUB_PORT/healthz" -o /dev/null

# The EP worker must be (re)started with the callback URL when the stub was
# just started — compose env change, so restart the container.
if [ "$CHECK_ONLY" -eq 0 ]; then
  if ! podman exec syntara-execution-plane_worker_1 env 2>/dev/null | grep -q "EP_CREDENTIAL_RESOLUTION_CALLBACK_URL=https://host.containers.internal:$STUB_PORT"; then
    warn "EP worker missing callback env — restarting with it"
    (cd "$EP_DIR" && EP_CREDENTIAL_RESOLUTION_CALLBACK_URL="https://host.containers.internal:$STUB_PORT" \
      uvx podman-compose up -d worker >/dev/null)
  fi
fi

# --- phase 5: kind node prep ---------------------------------------------------

log "phase 5: kind node prep (mirror + image)"
NODE_MIRROR="/etc/containerd/certs.d/localhost:5000/hosts.toml"
if [ "$CHECK_ONLY" -eq 0 ]; then
  if ! docker exec "$KIND_NODE" grep -q "172.18.0.1:5000" "$NODE_MIRROR" 2>/dev/null; then
    log "configuring containerd mirror on kind node"
    docker exec "$KIND_NODE" mkdir -p /etc/containerd/certs.d/localhost:5000
    docker exec "$KIND_NODE" sh -c "printf 'server = \"http://172.18.0.1:5000\"\n\n[host.\"http://172.18.0.1:5000\"]\n  capabilities = [\"pull\", \"resolve\"]\n  skip_verify = true\n' > $NODE_MIRROR"
    if ! docker exec "$KIND_NODE" grep -q 'cri.v1.images".registry]' /etc/containerd/config.toml 2>/dev/null; then
      docker exec "$KIND_NODE" sh -c 'printf "\n[plugins.\"io.containerd.cri.v1.images\".registry]\n  config_path = \"/etc/containerd/certs.d\"\n" >> /etc/containerd/config.toml'
      docker exec "$KIND_NODE" pkill -x containerd || true
      sleep 5
    fi
  fi
  log "pre-pulling step image on kind node (serial pulls are too slow for the dispatch timeout)"
  docker exec "$KIND_NODE" crictl pull "$STEP_IMAGE" >/dev/null
fi
docker exec "$KIND_NODE" crictl images 2>/dev/null | grep syntara-script-step >/dev/null \
  || fail "step image not present on kind node"

# --- phase 6: syntara stack ----------------------------------------------------

log "phase 6: syntara stack"
if [ "$CHECK_ONLY" -eq 0 ] && [ "$SKIP_STACK" -eq 0 ]; then
  (cd "$SYNTARA_DIR" && APP_EXECUTION_PLANE_ENABLED=true uvx podman-compose up -d >/dev/null)
  # Source is volume-mounted: compose does not restart the worker on code
  # changes. Restart it so the running code matches the tree.
  podman restart syntara_temporal-worker_1 >/dev/null
fi
wait_for "syntara API" 120 curl -sk https://localhost:8000/healthz -o /dev/null

# --- phase 7: validate ---------------------------------------------------------

log "phase 7: validate (workflow → EP → stdout 2)"
cd "$SYNTARA_DIR"
ADMIN_PASSWORD=$(cat backend/.secrets/admin-password)
TOKEN=$(curl -sk -X POST https://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

EXEC_ID=$(curl -sk -X POST https://localhost:8000/api/v1/executions \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"workflow_id\": \"$WORKFLOW_ID\", \"trigger_node_id\": \"$TRIGGER_NODE_ID\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
log "execution created: $EXEC_ID"

deadline=$((SECONDS + 300))
while :; do
  STATUS=$(curl -sk "https://localhost:8000/api/v1/executions/$EXEC_ID" \
    -H "Authorization: Bearer $TOKEN" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$STATUS" in
    completed|failed|cancelled) break ;;
  esac
  [ "$SECONDS" -ge "$deadline" ] && fail "execution $EXEC_ID did not finish in 300s (status: $STATUS)"
  sleep 5
done
[ "$STATUS" = "completed" ] || fail "execution $EXEC_ID ended: $STATUS"

EP_RESULT=$(curl -sk "https://localhost:8000/api/v1/executions/$EXEC_ID/activities?limit=20" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c '
import json, sys
items = json.load(sys.stdin)
items = items if isinstance(items, list) else items.get("resources", [])
outputs = [n.get("output_data") or n.get("output") or {} for n in items]
eps = [o for o in outputs if isinstance(o, dict) and o.get("executed_via") == "execution-plane"]
print(json.dumps([{"status": e.get("status"), "return_code": e.get("return_code"),
                   "stdout": e.get("stdout", "")} for e in eps]))')

echo "$EP_RESULT" | python3 -c '
import json, sys
results = json.load(sys.stdin)
if not results:
    sys.exit("FAIL: no execution-plane step outputs")
for step in results:
    status = step.get("status")
    return_code = step.get("return_code")
    stdout = step.get("stdout", "")
    if status != "completed":
        sys.exit("FAIL: EP step status: " + str(status))
    if return_code != 0:
        sys.exit("FAIL: EP step return_code: " + str(return_code))
    print("EP step output: " + repr(stdout))
expected = sys.argv[1]
if expected:
    for step in results:
        if step.get("stdout", "").strip() == expected.strip():
            break
    else:
        sys.exit("FAIL: no EP step produced stdout " + repr(expected))
print("PASS: " + str(len(results)) + " EP step(s) completed with return_code 0")
' "$EXPECTED_STDOUT" || fail "validation failed (see above)"

log "PASS: workflow executed on the Execution Plane"
