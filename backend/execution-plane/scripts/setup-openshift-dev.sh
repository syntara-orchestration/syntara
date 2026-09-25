#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ep_dir="$(cd "${script_dir}/.." && pwd)"
backend_dir="$(cd "${ep_dir}/.." && pwd)"
manifest="${ep_dir}/deploy/openshift-setup.yaml"
secret_dir="${backend_dir}/.secrets/execution-plane"
token_file="${secret_dir}/openshift-token"
robot_token_file="${EP_QUAY_ROBOT_TOKEN_FILE:-${secret_dir}/quay-robot-token}"
robot_username="${EP_QUAY_ROBOT_USERNAME:-ahetheri+execution_plane_robot}"
namespace="ep-dev-workers"
service_account="execution-plane-executor"
token_duration="${EP_OPENSHIFT_TOKEN_DURATION:-24h}"

command -v oc >/dev/null 2>&1 || { echo "oc is required" >&2; exit 1; }
endpoint="$(oc whoami --show-server)"
oc whoami >/dev/null

oc apply -f "${manifest}"

mkdir -p "${secret_dir}"
chmod 700 "${secret_dir}"
umask 077
temporary_token_file="$(mktemp "${secret_dir}/.openshift-token.XXXXXX")"
trap 'rm -f "${temporary_token_file}"' EXIT
oc create token "${service_account}" -n "${namespace}" --duration="${token_duration}" > "${temporary_token_file}"
mv "${temporary_token_file}" "${token_file}"
trap - EXIT
chmod 600 "${token_file}"

token="$(<"${token_file}")"
for permission in \
  "create pods" \
  "delete pods" \
  "create pods/exec" \
  "get pods/log"; do
  read -r verb resource <<<"${permission}"
  allowed="$(oc --server="${endpoint}" --token="${token}" auth can-i "${verb}" "${resource}" -n "${namespace}")"
  if [[ "${allowed}" != "yes" ]]; then
    echo "ServiceAccount cannot ${verb} ${resource} in ${namespace}" >&2
    exit 1
  fi
done

if [[ -f "${robot_token_file}" ]]; then
  temporary_pull_config="$(mktemp "${secret_dir}/.quay-config.XXXXXX")"
  trap 'rm -f "${temporary_pull_config}"' EXIT
  python3 - "${robot_token_file}" "${temporary_pull_config}" "${robot_username}" <<'PY'
import base64
import json
import sys
from pathlib import Path

token = Path(sys.argv[1]).read_text().strip()
if not token:
    raise SystemExit("Quay robot token file is empty")
username = sys.argv[3]
auth = base64.b64encode(f"{username}:{token}".encode()).decode()
Path(sys.argv[2]).write_text(json.dumps({"auths": {"quay.io": {"auth": auth}}}))
PY
  oc create secret generic quay-executor-pull \
    --from-file=".dockerconfigjson=${temporary_pull_config}" \
    --type=kubernetes.io/dockerconfigjson \
    -n "${namespace}" --dry-run=client -o yaml | oc apply -f -
  oc secrets link default quay-executor-pull --for=pull -n "${namespace}"
  rm -f "${temporary_pull_config}"
  trap - EXIT
  echo "Quay image-pull Secret is configured for ${namespace}."
else
  echo "Quay robot token file not found; private executor images will need an image-pull Secret." >&2
fi

echo "OpenShift worker namespace and RBAC are ready."
echo "API endpoint: ${endpoint}"
echo "Token path: ${token_file} (expires after ${token_duration}; rerun this script to rotate)"
