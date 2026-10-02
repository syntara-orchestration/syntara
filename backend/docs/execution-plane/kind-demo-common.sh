#!/usr/bin/env bash
# Shared helpers for the kind cold-start hello-world demo (Step 8).
# Sourced by run-hello-world-demo.sh and retry-hello-world-demo.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BASE="${BASE:-https://localhost:8000}"
API="${BASE}/api/v1"

_admin_password() {
  if [[ -n "${ADMIN_PASSWORD:-}" ]]; then
    printf '%s' "${ADMIN_PASSWORD}"
    return
  fi
  local secret_file="${APP_ADMIN_PASSWORD_PATH:-${BACKEND_DIR}/.secrets/admin-password}"
  if [[ -f "${secret_file}" ]]; then
    cat "${secret_file}"
    return
  fi
  if podman exec syntara_syntara_1 cat /run/secrets/admin-password 2>/dev/null; then
    return
  fi
  echo "Error: set ADMIN_PASSWORD, or provide ${secret_file}, or start the syntara container" >&2
  exit 1
}

kind_demo_login() {
  local password token
  password="$(_admin_password)"
  token="$(curl -sk -X POST "${API}/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"admin\",\"password\":\"${password}\"}" | jq -r .access_token)"
  if [[ -z "${token}" || "${token}" == "null" ]]; then
    echo "Error: login failed (check API at ${BASE} and the admin password)" >&2
    exit 1
  fi
  printf '%s' "${token}"
}

kind_demo_poll_execution() {
  local token="$1" exec_id="$2" status="" i
  local attempts="${KIND_DEMO_POLL_ATTEMPTS:-30}"
  for i in $(seq 1 "${attempts}"); do
    status="$(curl -sk "${API}/executions/${exec_id}" \
      -H "Authorization: Bearer ${token}" | jq -r .status)"
    echo "${status}"
    if [[ "${status}" == "completed" ]]; then
      return 0
    fi
    if [[ "${status}" == "failed" ]]; then
      echo "Error: execution ${exec_id} failed" >&2
      return 1
    fi
    sleep 3
  done
  echo "Error: execution ${exec_id} did not finish after polling" >&2
  return 1
}
