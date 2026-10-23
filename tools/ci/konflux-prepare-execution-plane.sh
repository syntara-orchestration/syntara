#!/usr/bin/env bash
# Finish Konflux e2e wiring after aap-dev deploys EP with the operator.
#
# deploy-ao (AO_EXECUTION_PLANE=true) already created myao-execution-plane-api
# and myao-execution-plane-worker in the AO namespace. This script does not
# deploy a sidecar EP. After AO is Ready it:
#   1. Verifies the execution-target pre-requisite (dispatcher SA and Job
#      namespace); aap-dev applies it during deploy when
#      AO_EXECUTION_PLANE=true (AAP-99675).
#   2. Waits for the operator EP API and worker.
#   3. Opens backend ingress from execution-plane-worker and allows the
#      operator callback CN on the AO backend before EP starts posting.
#   4. Sets EP_COMPLETION_CALLBACK_URL and
#      EP_CREDENTIAL_RESOLUTION_CALLBACK_URL to AO's
#      /api/execution_plane/v1/commands ingress.
#   5. Registers the Kind cluster as an EP cluster-binding via the EP API.
#   6. Points myao-worker at the operator EP (APP_EP_API_URL) and pre-pulls
#      the script-node image.
#
# CREDENTIAL_REF may name an existing AO credential that can access the Kind
# cluster's dispatcher service account. When omitted, one is created or
# refreshed from the dispatcher ServiceAccount token through the AO API.
set -euo pipefail

export PATH="${HOME}/aap-dev/bin:${PATH}"

KUBECONFIG="${KUBECONFIG:-${HOME}/aap-dev/.tmp/27-next-ao-operator.kubeconfig}"
export KUBECONFIG

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/../.." && pwd)
NAMESPACE="${NAMESPACE:-execution-plane}"
AO_NAMESPACE="${AO_NAMESPACE:-aap27-next}"
AO_NAME="${AO_NAME:-myao}"
EP_API_DEPLOY="${EP_API_DEPLOY:-${AO_NAME}-execution-plane-api}"
EP_WORKER_DEPLOY="${EP_WORKER_DEPLOY:-${AO_NAME}-execution-plane-worker}"
SA_NAME="${SA_NAME:-syntara-dispatcher}"
CLUSTER_NAME="${CLUSTER_NAME:-27-next-ao-operator}"
ENDPOINT="${ENDPOINT:-https://kubernetes.default.svc}"
NODE_IMAGE="${NODE_IMAGE:-quay.io/ahetheri/syntara-node-script:migration-test}"
CREDENTIAL_REF="${CREDENTIAL_REF:-}"
AO_API_BASE="${AO_API_BASE:-https://127.0.0.1:8443}"
WORK_DIR=""

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "ERROR: kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi
if [[ -n "${CREDENTIAL_REF}" && ! "${CREDENTIAL_REF}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  echo "ERROR: CREDENTIAL_REF must be a UUID" >&2
  exit 1
fi

_cleanup() {
  if [[ -n "${WORK_DIR}" ]]; then
    rm -rf "${WORK_DIR}"
  fi
}

_secret_data() {
  secret_name="$1"
  namespace="$2"
  key="$3"
  kubectl get secret "${secret_name}" -n "${namespace}" -o json | python3 -c "
import base64, json, sys
key = sys.argv[1]
print(base64.b64decode(json.load(sys.stdin)['data'][key]).decode(), end='')
" "${key}"
}

_ao_jwt_issuer() {
  local issuer
  issuer=$(kubectl get deploy "${EP_API_DEPLOY}" -n "${AO_NAMESPACE}" \
    -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='EP_AO_JWT_ISSUER')].value}" \
    2>/dev/null || true)
  if [[ -n "${issuer}" ]]; then
    printf '%s' "${issuer%/}"
    return 0
  fi
  issuer=$(kubectl exec -n "${AO_NAMESPACE}" "deploy/${AO_NAME}-backend" -- \
    /opt/app-root/src/.venv/bin/python -c \
    'from syntara.core.config.base import get_settings; print(get_settings().jwt_issuer, end="")' \
    2>/dev/null || true)
  if [[ -n "${issuer}" ]]; then
    printf '%s' "${issuer}"
    return 0
  fi
  issuer=$(kubectl get deploy "${AO_NAME}-backend" -n "${AO_NAMESPACE}" \
    -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='APP_SERVER_PUBLIC_URL')].value}" \
    2>/dev/null || true)
  if [[ -n "${issuer}" ]]; then
    printf '%s' "${issuer%/}"
    return 0
  fi
  printf '%s' "https://0.0.0.0:8000"
}

_create_ao_credential() {
  local dispatcher_token admin_password
  dispatcher_token=$(kubectl create token "${SA_NAME}" --namespace "${NAMESPACE}" --duration=12h)
  admin_password=$(_secret_data myao-initial-admin-password "${AO_NAMESPACE}" password)
  AO_ADMIN_PASSWORD="${admin_password}" AO_CREDENTIAL_TOKEN="${dispatcher_token}" \
    python3 "${REPO_ROOT}/tools/create_ao_credential.py" \
      --api-url "${AO_API_BASE}" \
      --cluster-name "${CLUSTER_NAME}" \
      --insecure
}

_ao_command_ingress_url() {
  printf '%s' "https://${AO_NAME}-backend.${AO_NAMESPACE}.svc.cluster.local:8000/api/execution_plane/v1/commands"
}

_ep_api_url() {
  printf '%s' "https://${EP_API_DEPLOY}.${AO_NAMESPACE}.svc.cluster.local:8443"
}

_require_operator_ep_opt_in() {
  local enabled
  enabled=$(kubectl get configmap "${AO_NAME}-admin-settings" -n "${AO_NAMESPACE}" \
    -o jsonpath='{.data.ENABLE_EXECUTION_PLANE}' 2>/dev/null || true)
  if [[ "${enabled}" != "true" ]]; then
    echo "ERROR: ${AO_NAME}-admin-settings ENABLE_EXECUTION_PLANE=${enabled:-<unset>}" >&2
    echo "deploy-ao must run with AO_EXECUTION_PLANE=true so the operator deploys EP" >&2
    kubectl get configmap "${AO_NAME}-admin-settings" -n "${AO_NAMESPACE}" -o yaml >&2 || true
    exit 1
  fi
  if [[ ! -f "${HOME}/aap-dev/src/syntara-execution-plane/Containerfile" ]]; then
    echo "ERROR: aap-dev did not overlay Execution Plane source at src/syntara-execution-plane" >&2
    echo "stage-ep-source must finish before deploy-ao, with AO_EXECUTION_PLANE=true" >&2
    ls -la "${HOME}/syntara-execution-plane" >&2 || true
    cat "${HOME}/aap-dev/src/sources.yaml" >&2 || true
    exit 1
  fi
  if ! grep -q 'syntara-execution-plane' "${HOME}/aap-dev/src/sources.yaml" 2>/dev/null; then
    echo "ERROR: src/sources.yaml does not name syntara-execution-plane; EP image is prebuilt" >&2
    cat "${HOME}/aap-dev/src/sources.yaml" >&2 || true
    exit 1
  fi
  if [[ ! -f "${HOME}/aap-dev/.tmp/ao-operator-from-src.env" ]]; then
    echo "ERROR: operator was not built from source (missing .tmp/ao-operator-from-src.env)" >&2
    echo "the prebuilt bundle ignores ENABLE_EXECUTION_PLANE; stage-operator-source must run before deploy-ao" >&2
    ls -la "${HOME}/automation-orchestrator-operator" >&2 || true
    cat "${HOME}/aap-dev/src/sources.yaml" >&2 || true
    exit 1
  fi
  echo "operator from-src: $(cat "${HOME}/aap-dev/.tmp/ao-operator-from-src.env")"
}

_wait_for_operator_ep() {
  local deadline
  echo "=== Wait for operator Execution Plane (${EP_API_DEPLOY}, ${EP_WORKER_DEPLOY}) ==="
  deadline=$((SECONDS + 300))
  while (( SECONDS < deadline )); do
    if kubectl get deploy "${EP_API_DEPLOY}" -n "${AO_NAMESPACE}" >/dev/null 2>&1 \
      && kubectl get deploy "${EP_WORKER_DEPLOY}" -n "${AO_NAMESPACE}" >/dev/null 2>&1; then
      break
    fi
    sleep 5
  done
  if ! kubectl get deploy "${EP_API_DEPLOY}" -n "${AO_NAMESPACE}" >/dev/null 2>&1; then
    echo "ERROR: operator did not create deploy/${EP_API_DEPLOY} in ${AO_NAMESPACE}" >&2
    kubectl get deploy -n "${AO_NAMESPACE}" >&2 || true
    kubectl get configmap "${AO_NAME}-admin-settings" -n "${AO_NAMESPACE}" -o yaml >&2 || true
    kubectl logs -n "${AO_NAMESPACE}" "deploy/automation-orchestrator-operator-controller-manager" --tail=80 >&2 || true
    exit 1
  fi
  if ! kubectl rollout status "deploy/${EP_API_DEPLOY}" -n "${AO_NAMESPACE}" --timeout=180s; then
    kubectl get pods -n "${AO_NAMESPACE}" -l "app.kubernetes.io/component=execution-plane-api" -o wide
    kubectl describe "deploy/${EP_API_DEPLOY}" -n "${AO_NAMESPACE}" || true
    exit 1
  fi
  if ! kubectl rollout status "deploy/${EP_WORKER_DEPLOY}" -n "${AO_NAMESPACE}" --timeout=180s; then
    kubectl get pods -n "${AO_NAMESPACE}" -l "app.kubernetes.io/component=execution-plane-worker" -o wide
    kubectl describe "deploy/${EP_WORKER_DEPLOY}" -n "${AO_NAMESPACE}" || true
    exit 1
  fi
  kubectl get pods -n "${AO_NAMESPACE}" -l "app.kubernetes.io/component in (execution-plane-api,execution-plane-worker)" -o wide
}

_allow_ep_callback_ingress() {
  echo "=== Allow ${EP_WORKER_DEPLOY} callback into ${AO_NAME}-backend ==="
  # Additive to the operator policies: myao-backend only admits UI/worker/
  # background-worker/backend, so the EP worker completion POST is dropped
  # (httpx ConnectTimeout) until this rule exists.
  kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-execution-plane-callback
  namespace: ${AO_NAMESPACE}
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: backend
      app.kubernetes.io/instance: ${AO_NAME}
      app.kubernetes.io/managed-by: automation-orchestrator-operator
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/component: execution-plane-worker
              app.kubernetes.io/instance: ${AO_NAME}
              app.kubernetes.io/managed-by: automation-orchestrator-operator
      ports:
        - protocol: TCP
          port: 8000
EOF
}

_configure_ep_callback_url() {
  local completion_url resolution_url ca_path cert_path key_path
  local -a env_args
  completion_url=$(_ao_command_ingress_url)
  resolution_url=$(_ao_command_ingress_url)
  ca_path=$(kubectl get deploy "${EP_WORKER_DEPLOY}" -n "${AO_NAMESPACE}" \
    -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='EP_CALLBACK_CA_CERT_PATH')].value}" \
    2>/dev/null || true)
  cert_path=$(kubectl get deploy "${EP_WORKER_DEPLOY}" -n "${AO_NAMESPACE}" \
    -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='EP_CALLBACK_CERT_PATH')].value}" \
    2>/dev/null || true)
  key_path=$(kubectl get deploy "${EP_WORKER_DEPLOY}" -n "${AO_NAMESPACE}" \
    -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='EP_CALLBACK_KEY_PATH')].value}" \
    2>/dev/null || true)
  env_args=(
    "EP_COMPLETION_CALLBACK_URL=${completion_url}"
    "EP_CREDENTIAL_RESOLUTION_CALLBACK_URL=${resolution_url}"
  )
  if [[ -n "${ca_path}" ]]; then
    env_args+=("EP_CREDENTIAL_RESOLUTION_CALLBACK_CA_CERT_PATH=${ca_path}")
  fi
  if [[ -n "${cert_path}" && -n "${key_path}" ]]; then
    env_args+=(
      "EP_CREDENTIAL_RESOLUTION_CALLBACK_CERT_PATH=${cert_path}"
      "EP_CREDENTIAL_RESOLUTION_CALLBACK_KEY_PATH=${key_path}"
    )
  fi
  echo "=== Set EP callback URLs on ${EP_WORKER_DEPLOY} ==="
  echo "EP_COMPLETION_CALLBACK_URL=${completion_url}"
  echo "EP_CREDENTIAL_RESOLUTION_CALLBACK_URL=${resolution_url}"
  kubectl set env "deploy/${EP_WORKER_DEPLOY}" -n "${AO_NAMESPACE}" "${env_args[@]}"
  kubectl rollout status "deploy/${EP_WORKER_DEPLOY}" -n "${AO_NAMESPACE}" --timeout=180s
}

_kind_node_container() {
  printf '%s' "${CLUSTER_NAME}-control-plane"
}

_node_exec() {
  local node
  node=$(_kind_node_container)
  if command -v podman >/dev/null 2>&1 && podman inspect "${node}" >/dev/null 2>&1; then
    podman exec "${node}" "$@"
    return 0
  fi
  if command -v docker >/dev/null 2>&1 && docker inspect "${node}" >/dev/null 2>&1; then
    docker exec "${node}" "$@"
    return 0
  fi
  echo "ERROR: Kind node container ${node} not found" >&2
  return 1
}

_prepull_node_image() {
  local image=$1
  local node
  node=$(_kind_node_container)
  echo "=== Pre-pull ${image} on Kind node ${node} ==="
  _node_exec crictl pull "${image}"
  _node_exec crictl images
  echo "pre-pulled ${image} on ${node}"
}

_allow_ep_callback_identity() {
  local callback_cn allowlist ep_url
  callback_cn="execution-plane-callback.ao.svc"
  ep_url=$(_ep_api_url)
  allowlist=$(kubectl get deploy "${AO_NAME}-backend" -n "${AO_NAMESPACE}" -o json | python3 -c '
import json, sys
deploy = json.load(sys.stdin)
env = deploy["spec"]["template"]["spec"]["containers"][0]["env"]
raw = next((e.get("value") or "[]" for e in env if e.get("name") == "APP_S2S_TLS_CN_ALLOWLIST"), "[]")
cns = json.loads(raw)
need = "execution-plane-callback.ao.svc"
if need not in cns:
    cns.append(need)
print(json.dumps(cns))
')
  echo "=== Allow EP callback CN ${callback_cn} on ${AO_NAME}-backend ==="
  kubectl set env "deploy/${AO_NAME}-backend" -n "${AO_NAMESPACE}" \
    "APP_EP_CALLBACK_SERVICE_CN=${callback_cn}" \
    "APP_S2S_TLS_CN_ALLOWLIST=${allowlist}" \
    "APP_EP_API_URL=${ep_url}"
  kubectl rollout status "deploy/${AO_NAME}-backend" -n "${AO_NAMESPACE}" --timeout=180s
}

_enable_script_dispatch() {
  local image=$1
  local images_json ep_url
  images_json=$(python3 -c 'import json, sys; print(json.dumps({"script": sys.argv[1]}))' "${image}")
  ep_url=$(_ep_api_url)
  echo "=== Point ${AO_NAME}-worker at operator EP ${ep_url} ==="
  kubectl set env "deploy/${AO_NAME}-worker" -n "${AO_NAMESPACE}" \
    APP_SCRIPT_NODES_ENABLED=true \
    "APP_NODE_CONTAINER_IMAGES=${images_json}" \
    "APP_EP_API_URL=${ep_url}"
  kubectl rollout status "deploy/${AO_NAME}-worker" -n "${AO_NAMESPACE}" --timeout=180s
}

_register_cluster_binding() {
  local issuer=$1 credential_ref=$2
  kubectl get configmap kube-root-ca.crt -n "${AO_NAMESPACE}" \
    -o jsonpath='{.data.ca\.crt}' > "${WORK_DIR}/cluster-ca.pem"
  python3 -c "
import json, sys, uuid
from pathlib import Path
cluster, endpoint, namespace, issuer, credential_ref, ca_path = sys.argv[1:]
payload = {
    'source_integration_id': str(uuid.uuid5(uuid.NAMESPACE_URL, f'https://execution-plane.local/kind/{cluster}')),
    'issuer': issuer,
    'desired': {
        'name': cluster,
        'endpoint': endpoint,
        'namespace': namespace,
        'credential_ref': credential_ref,
        'ca_certificate': Path(ca_path).read_text(),
        'enabled': True,
        'labels': {'execution-plane.syntara.io/local': 'kind'},
    },
}
json.dump(payload, sys.stdout)
" "${CLUSTER_NAME}" "${ENDPOINT}" "${NAMESPACE}" "${issuer}" "${credential_ref}" "${WORK_DIR}/cluster-ca.pem" \
    > "${WORK_DIR}/binding.json"

  kubectl exec -i -n "${AO_NAMESPACE}" "deploy/${EP_API_DEPLOY}" -- \
    /bin/sh -c 'cat > /tmp/jwt-primary.pem' < "${WORK_DIR}/jwt-primary.pem"
  kubectl exec -i -n "${AO_NAMESPACE}" "deploy/${EP_API_DEPLOY}" -- \
    /bin/sh -c 'cat > /tmp/binding.json' < "${WORK_DIR}/binding.json"

  echo "=== Register cluster binding via operator EP API ==="
  kubectl exec -i -n "${AO_NAMESPACE}" "deploy/${EP_API_DEPLOY}" -- \
    /opt/app-root/src/.venv/bin/python - <<'PY'
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt

from execution_plane_client.commands.clusters import ClusterProvision

payload = json.loads(Path("/tmp/binding.json").read_text())
key = Path("/tmp/jwt-primary.pem").read_text()
now = datetime.now(UTC)
token = jwt.encode(
    {
        "iss": payload["issuer"],
        "aud": "execution-plane",
        "client_id": "syntara-orchestration",
        "scope": "cluster.provision clusters:read execution-targets:read",
        "iat": now,
        "exp": now + timedelta(hours=1),
    },
    key,
    algorithm="ES256",
)
sid = uuid.UUID(payload["source_integration_id"])
desired = payload["desired"]
base = "https://127.0.0.1:8443"
headers = {"Authorization": f"Bearer {token}"}
with httpx.Client(verify=False, timeout=30.0) as client:
    got = client.get(f"{base}/v1/clusters/{sid}", headers=headers)
    revision = 1
    if got.status_code == 200:
        revision = int(got.json()["desired_revision"]) + 1
    envelope = ClusterProvision(
        resource_key=sid,
        desired_revision=revision,
        name=desired["name"],
        endpoint=desired["endpoint"],
        namespace=desired["namespace"],
        credential_ref=uuid.UUID(desired["credential_ref"]),
        ca_certificate=desired["ca_certificate"],
        enabled=True,
        labels=desired["labels"],
    ).to_message(
        source_id="syntara-orchestration",
        destination_id="execution-plane",
        client_id="syntara-orchestration",
    )
    posted = client.post(
        f"{base}/v1/commands",
        headers=headers,
        json=envelope.model_dump(mode="json"),
    )
    if posted.status_code >= 400:
        raise SystemExit(f"cluster.provision failed ({posted.status_code}): {posted.text}")
    print(f"upserted cluster {sid} revision {revision} status={posted.status_code}")
    deadline = time.time() + 90
    while time.time() < deadline:
        status, message = "unknown", ""
        got = client.get(f"{base}/v1/clusters/{sid}", headers=headers)
        if got.status_code == 200:
            doc = got.json()
            status = doc.get("status") or "unknown"
            message = doc.get("status_message") or ""
            print(f"cluster binding status: {status}")
            if status == "ready":
                break
            if status == "error":
                raise SystemExit(message or "cluster binding reconciliation failed")
        time.sleep(3)
    else:
        raise SystemExit(f"timed out waiting for cluster {sid} to become ready")
    targets = client.get(f"{base}/v1/execution-targets", headers=headers)
    if targets.status_code >= 400:
        raise SystemExit(f"listing execution targets failed ({targets.status_code}): {targets.text}")
    print(f"execution targets: {len(targets.json())}")
PY
  kubectl exec -n "${AO_NAMESPACE}" "deploy/${EP_API_DEPLOY}" -- \
    rm -f /tmp/jwt-primary.pem /tmp/binding.json >/dev/null 2>&1 || true
}

echo "=== Cluster ==="
kubectl cluster-info
kubectl get namespace "${AO_NAMESPACE}" >/dev/null
echo "AO namespace ${AO_NAMESPACE} is present"

WORK_DIR=$(mktemp -d)
chmod 700 "${WORK_DIR}"
trap _cleanup EXIT

_require_operator_ep_opt_in

echo "=== Verify ${NAMESPACE} (applied by aap-dev, AAP-99675) ==="
kubectl get namespace "${NAMESPACE}"
kubectl get serviceaccount "${SA_NAME}" -n "${NAMESPACE}"
kubectl get role syntara-node-dispatcher -n "${NAMESPACE}"
kubectl get rolebinding syntara-node-dispatcher -n "${NAMESPACE}"
kubectl get clusterrole syntara-resource-monitor
kubectl get clusterrolebinding syntara-resource-monitor

DISPATCHER_AS="system:serviceaccount:${NAMESPACE}:${SA_NAME}"

echo "=== RBAC: jobs in ${NAMESPACE} (must be yes) ==="
if ! kubectl auth can-i create jobs.batch --as="${DISPATCHER_AS}" -n "${NAMESPACE}"; then
  echo "ERROR: ${SA_NAME} cannot create jobs in ${NAMESPACE}" >&2
  exit 1
fi

echo "=== RBAC: list pods in ${NAMESPACE} (must be yes) ==="
if ! kubectl auth can-i list pods --as="${DISPATCHER_AS}" -n "${NAMESPACE}"; then
  echo "ERROR: ${SA_NAME} cannot list pods in ${NAMESPACE}" >&2
  exit 1
fi

echo "=== RBAC: get namespaces (must be yes) ==="
if ! kubectl auth can-i get namespaces --as="${DISPATCHER_AS}"; then
  echo "ERROR: ${SA_NAME} cannot get namespaces for the Resource Monitor probe" >&2
  exit 1
fi

echo "=== RBAC: list namespaces (must be no) ==="
if kubectl auth can-i list namespaces --as="${DISPATCHER_AS}"; then
  echo "ERROR: ${SA_NAME} can list namespaces; ClusterRole is too wide" >&2
  exit 1
fi

echo "=== RBAC: create pods in ${NAMESPACE} (must be no) ==="
if kubectl auth can-i create pods --as="${DISPATCHER_AS}" -n "${NAMESPACE}"; then
  echo "ERROR: ${SA_NAME} can create pods in ${NAMESPACE}; Role is too wide" >&2
  exit 1
fi

echo "=== RBAC: jobs in ${AO_NAMESPACE} (must be no) ==="
if kubectl auth can-i create jobs.batch --as="${DISPATCHER_AS}" -n "${AO_NAMESPACE}"; then
  echo "ERROR: ${SA_NAME} can create jobs in ${AO_NAMESPACE}; Role is too wide" >&2
  exit 1
fi

if [[ -z "${CREDENTIAL_REF}" ]]; then
  echo "=== Create or refresh the AO credential for ${SA_NAME} ==="
  CREDENTIAL_REF=$(_create_ao_credential)
fi
if [[ ! "${CREDENTIAL_REF}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  echo "ERROR: CREDENTIAL_REF must be the AO credential UUID" >&2
  exit 1
fi

_wait_for_operator_ep

echo "=== Extract AO JWT from ${AO_NAME}-jwt-primary ==="
_secret_data "${AO_NAME}-jwt-primary" "${AO_NAMESPACE}" jwt-primary.pem \
  > "${WORK_DIR}/jwt-primary.pem"
chmod 600 "${WORK_DIR}/jwt-primary.pem"

AO_JWT_ISSUER=$(_ao_jwt_issuer)
echo "AO JWT issuer: ${AO_JWT_ISSUER}"

_allow_ep_callback_ingress
_allow_ep_callback_identity
_configure_ep_callback_url
_register_cluster_binding "${AO_JWT_ISSUER}" "${CREDENTIAL_REF}"
_prepull_node_image "${NODE_IMAGE}"
_enable_script_dispatch "${NODE_IMAGE}"

echo "operator Execution Plane is up; script nodes dispatch ${NODE_IMAGE}"
echo "EP API: $(_ep_api_url)"
