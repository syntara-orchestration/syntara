#!/usr/bin/env bash
# Prepare the execution-plane namespace on the AO Kind cluster (Konflux / aap-dev).
#
# Applies execution-plane-init.yaml to the *current* cluster (same Kind that
# hosts AO), mints a syntara-dispatcher token without printing it, checks that
# the dispatcher Role can create pods only in this namespace, registers that
# cluster as an ExecutionTarget, deploys the EP worker in execution-plane,
# pre-pulls the public script-node image onto the Kind node (PR #747), enables
# script dispatch on myao-worker, opens Temporal 7233 from this namespace
# (operator NP otherwise drops it), and copies AO mTLS secrets so the EP
# worker can complete the async activity.
# The hello-world demo belongs in konflux-run-hello-world-demo.sh.
#
# Intended to run on the mapt VM after deploy-ao, with KUBECONFIG pointing at
# Kind 27-next-ao-operator. Idempotent (kubectl apply). Register the target
# *before* starting the worker so bootstrap does not create a dummy local target.
set -euo pipefail

# aap-dev installs kind/kubectl into $HOME/aap-dev/bin; non-interactive SSH
# does not put that directory on PATH.
export PATH="${HOME}/aap-dev/bin:${PATH}"

KUBECONFIG="${KUBECONFIG:-${HOME}/aap-dev/.tmp/27-next-ao-operator.kubeconfig}"
export KUBECONFIG

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TOOLS_DIR=$(cd "${SCRIPT_DIR}/../../execution-plane/tools" && pwd)
INIT_YAML="${INIT_YAML:-${SCRIPT_DIR}/execution-plane-init.yaml}"
WORKER_YAML="${WORKER_YAML:-${SCRIPT_DIR}/execution-plane-worker.yaml}"
NAMESPACE="${NAMESPACE:-execution-plane}"
AO_NAMESPACE="${AO_NAMESPACE:-aap27-next}"
SA_NAME="${SA_NAME:-syntara-dispatcher}"
CLUSTER_NAME="${CLUSTER_NAME:-27-next-ao-operator}"
ENDPOINT="${ENDPOINT:-https://kubernetes.default.svc}"
TOKEN_FILE="${TOKEN_FILE:-/var/tmp/syntara-dispatcher.token}"
TOKEN_DURATION="${TOKEN_DURATION:-24h}"
# Same public default as node_container_images (PR #747). Override with NODE_IMAGE
# when CI publishes a digest-pinned tag.
NODE_IMAGE="${NODE_IMAGE:-quay.io/ahetheri/syntara-node-script:migration-test}"

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "ERROR: kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi
if [[ ! -f "${INIT_YAML}" ]]; then
  echo "ERROR: init manifest not found: ${INIT_YAML}" >&2
  exit 1
fi

_apply_worker_manifest() {
  local image=$1 temporal=$2
  local src="${WORKER_YAML}"
  if [[ ! -f "${src}" ]]; then
    echo "worker YAML not in tree; using embedded manifest"
    src=$(mktemp)
    cat > "${src}" <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: execution-plane-worker
  namespace: execution-plane
  labels:
    app.kubernetes.io/name: execution-plane-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: execution-plane-worker
  template:
    metadata:
      labels:
        app.kubernetes.io/name: execution-plane-worker
    spec:
      serviceAccountName: syntara-dispatcher
      automountServiceAccountToken: true
      containers:
        - name: worker
          image: __IMAGE__
          imagePullPolicy: IfNotPresent
          command:
            - /bin/sh
            - -c
            - |
              export NODE_K8S_CA_CERTIFICATE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/ca.crt)"
              exec /opt/app-root/src/.venv/bin/execution-plane-worker
          env:
            - name: APP_DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: execution-plane-worker-env
                  key: APP_DATABASE_URL
            - name: APP_TEMPORAL_ADDRESS
              value: __TEMPORAL__
            - name: APP_TEMPORAL_NAMESPACE
              value: default
            - name: APP_S2S_TLS_ENABLED
              value: "false"
            - name: NODE_K8S_VERIFY_SSL
              value: "true"
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
EOF
  fi
  sed -e "s#__IMAGE__#${image}#g" -e "s#__TEMPORAL__#${temporal}#g" "${src}" | kubectl apply -f -
}

_deploy_env_value() {
  local var=$1
  local deploy value secret_name secret_key
  for deploy in myao-worker myao-backend; do
    value=$(kubectl get deploy "${deploy}" -n "${AO_NAMESPACE}" \
      -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='${var}')].value}" 2>/dev/null || true)
    if [[ -n "${value}" ]]; then
      printf '%s' "${value}"
      return 0
    fi
    secret_name=$(kubectl get deploy "${deploy}" -n "${AO_NAMESPACE}" \
      -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='${var}')].valueFrom.secretKeyRef.name}" 2>/dev/null || true)
    secret_key=$(kubectl get deploy "${deploy}" -n "${AO_NAMESPACE}" \
      -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='${var}')].valueFrom.secretKeyRef.key}" 2>/dev/null || true)
    if [[ -n "${secret_name}" && -n "${secret_key}" ]]; then
      kubectl get secret "${secret_name}" -n "${AO_NAMESPACE}" -o jsonpath="{.data.${secret_key}}" | base64 -d
      return 0
    fi
  done
  return 1
}

_qualify_svc_host() {
  local namespace=$2
  python3 -c "
import sys
from urllib.parse import urlsplit, urlunsplit
raw, ns = sys.argv[1], sys.argv[2]
if '://' in raw:
    parts = urlsplit(raw)
    host = parts.hostname or ''
    if host and '.' not in host:
        userinfo = parts.username or ''
        if parts.username and parts.password is not None:
            userinfo = f'{parts.username}:{parts.password}'
        prefix = f'{userinfo}@' if userinfo else ''
        port = f':{parts.port}' if parts.port else ''
        netloc = f'{prefix}{host}.{ns}.svc{port}'
        raw = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    sys.stdout.write(raw)
    raise SystemExit(0)
host, sep, rest = raw.partition(':')
if host and '.' not in host:
    raw = f'{host}.{ns}.svc{sep}{rest}'
sys.stdout.write(raw)
" "$1" "${namespace}"
}

_database_url_from_secret() {
  local user password database
  user=$(kubectl get secret backend-db-secret -n "${AO_NAMESPACE}" -o jsonpath='{.data.username}' | base64 -d)
  password=$(kubectl get secret backend-db-secret -n "${AO_NAMESPACE}" -o jsonpath='{.data.password}' | base64 -d)
  database=$(kubectl get secret backend-db-secret -n "${AO_NAMESPACE}" -o jsonpath='{.data.database}' | base64 -d)
  python3 -c "
import sys
from urllib.parse import quote
user, password, database, ns = sys.argv[1:]
print(
    f'postgresql+asyncpg://{quote(user, safe=\"\")}:{quote(password, safe=\"\")}@ao-postgres.{ns}.svc:5432/{quote(database, safe=\"\")}',
    end='',
)
" "${user}" "${password}" "${database}" "${AO_NAMESPACE}"
}

_backend_pod() {
  local pod
  pod=$(kubectl get pods -n "${AO_NAMESPACE}" --field-selector=status.phase=Running \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | awk '/myao-backend/{print; exit}')
  if [[ -z "${pod}" ]]; then
    echo "ERROR: no Running myao-backend pod in ${AO_NAMESPACE}" >&2
    exit 1
  fi
  printf '%s' "${pod}"
}

_temporal_address() {
  local addr svc
  if addr=$(_deploy_env_value APP_TEMPORAL_ADDRESS); then
    _qualify_svc_host "${addr}" "${AO_NAMESPACE}"
    return 0
  fi
  svc=$(kubectl get svc -n "${AO_NAMESPACE}" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' \
    | awk 'tolower($0) ~ /temporal/ {print; exit}')
  if [[ -z "${svc}" ]]; then
    echo "ERROR: could not discover Temporal service in ${AO_NAMESPACE}" >&2
    exit 1
  fi
  printf '%s' "${svc}.${AO_NAMESPACE}.svc:7233"
}

# Operator Temporal NP only admits backend/worker/background-worker pods in
# aap27-next onto :7233. Cross-namespace clients get a TCP timeout (SYN drop),
# which is exactly the hello-world hang: node pod ran, callback never landed.
_allow_temporal_from_ep() {
  echo "=== Allow ${NAMESPACE} -> Temporal :7233 ==="
  kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-execution-plane-temporal
  namespace: ${AO_NAMESPACE}
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: temporal-server
      app.kubernetes.io/name: automation-orchestrator
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ${NAMESPACE}
          podSelector:
            matchLabels:
              app.kubernetes.io/name: execution-plane-worker
      ports:
        - protocol: TCP
          port: 7233
EOF
}

_copy_secret_to_namespace() {
  local name=$1
  kubectl get secret "${name}" -n "${AO_NAMESPACE}" -o json | python3 -c "
import json, sys
doc = json.load(sys.stdin)
out = {
    'apiVersion': 'v1',
    'kind': 'Secret',
    'metadata': {'name': doc['metadata']['name'], 'namespace': sys.argv[1]},
    'type': doc.get('type', 'Opaque'),
}
if 'data' in doc:
    out['data'] = doc['data']
json.dump(out, sys.stdout)
" "${NAMESPACE}" | kubectl apply -f -
}

# Temporal frontend requireClientAuth=true. myao-worker already has S2S mTLS;
# reuse those secrets in execution-plane (different namespace cannot mount them).
_enable_ep_temporal_mtls() {
  local tls_enabled ca_secret tls_secret
  tls_enabled=$(_deploy_env_value APP_S2S_TLS_ENABLED || true)
  if [[ "${tls_enabled}" != "true" ]]; then
    echo "=== APP_S2S_TLS_ENABLED=${tls_enabled:-unset}; EP worker stays plaintext Temporal ==="
    return 0
  fi
  ca_secret=$(kubectl get deploy myao-worker -n "${AO_NAMESPACE}" \
    -o jsonpath='{.spec.template.spec.volumes[?(@.name=="internal-ca")].secret.secretName}')
  tls_secret=$(kubectl get deploy myao-worker -n "${AO_NAMESPACE}" \
    -o jsonpath='{.spec.template.spec.volumes[?(@.name=="service-tls")].secret.secretName}')
  if [[ -z "${ca_secret}" || -z "${tls_secret}" ]]; then
    echo "ERROR: myao-worker has APP_S2S_TLS_ENABLED=true but no internal-ca/service-tls volumes" >&2
    return 1
  fi
  echo "=== Copy Temporal mTLS secrets ${ca_secret} ${tls_secret} into ${NAMESPACE} ==="
  _copy_secret_to_namespace "${ca_secret}"
  _copy_secret_to_namespace "${tls_secret}"
  kubectl patch deploy/execution-plane-worker -n "${NAMESPACE}" --type strategic --patch "
spec:
  template:
    spec:
      volumes:
        - name: internal-ca
          secret:
            secretName: ${ca_secret}
        - name: service-tls
          secret:
            secretName: ${tls_secret}
      containers:
        - name: worker
          volumeMounts:
            - name: internal-ca
              mountPath: /certs/ca
              readOnly: true
            - name: service-tls
              mountPath: /certs/service
              readOnly: true
          env:
            - name: APP_S2S_TLS_ENABLED
              value: \"true\"
            - name: APP_S2S_TLS_CA_CERT_PATH
              value: /certs/ca/ca.crt
            - name: APP_S2S_TLS_CERT_PATH
              value: /certs/service/tls.crt
            - name: APP_S2S_TLS_KEY_PATH
              value: /certs/service/tls.key
"
}

_assert_temporal_tcp() {
  local addr=$1 host port
  host=${addr%:*}
  port=${addr##*:}
  echo "=== Probe Temporal TCP ${host}:${port} from execution-plane-worker ==="
  kubectl exec -n "${NAMESPACE}" deploy/execution-plane-worker -- \
    /opt/app-root/src/.venv/bin/python -c "
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    s = socket.create_connection((host, port), 8)
    s.close()
except OSError as e:
    print(f'ERROR: cannot reach Temporal {host}:{port}: {e}', file=sys.stderr)
    sys.exit(1)
print(f'reached {host}:{port}')
" "${host}" "${port}"
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
  # Same as kind-demo-runbook Step 5: the node pulls from quay (no kind load).
  # Required here so ImagePullBackOff cannot eat the hello-world poll window.
  _node_exec crictl pull "${image}"
  _node_exec crictl images
  echo "pre-pulled ${image} on ${node}"
}

_enable_script_dispatch() {
  local image=$1
  local images_json
  images_json=$(python3 -c 'import json, sys; print(json.dumps({"script": sys.argv[1]}))' "${image}")
  echo "=== Enable script nodes on myao-worker ==="
  kubectl set env deploy/myao-worker -n "${AO_NAMESPACE}" \
    APP_SCRIPT_NODES_ENABLED=true \
    "APP_NODE_CONTAINER_IMAGES=${images_json}"
  kubectl rollout status deploy/myao-worker -n "${AO_NAMESPACE}" --timeout=180s
}

echo "=== Cluster ==="
kubectl cluster-info
kubectl get namespace "${AO_NAMESPACE}" >/dev/null
echo "AO namespace ${AO_NAMESPACE} is present (operator remains there)"

echo "=== Apply ${INIT_YAML} ==="
kubectl apply -f "${INIT_YAML}"
_allow_temporal_from_ep

echo "=== Verify ${NAMESPACE} ==="
kubectl get namespace "${NAMESPACE}"
kubectl get serviceaccount "${SA_NAME}" -n "${NAMESPACE}"
kubectl get role syntara-node-dispatcher -n "${NAMESPACE}"
kubectl get rolebinding syntara-node-dispatcher -n "${NAMESPACE}"

echo "=== Mint ${SA_NAME} token (not printed) ==="
TOKEN="$(kubectl create token "${SA_NAME}" -n "${NAMESPACE}" --duration="${TOKEN_DURATION}")"
if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: failed to mint ${SA_NAME} token" >&2
  exit 1
fi
printf '%s' "${TOKEN}" > "${TOKEN_FILE}"
chmod 600 "${TOKEN_FILE}"
echo "minted ${SA_NAME} token (${#TOKEN} chars)"
unset TOKEN

DISPATCHER_AS="system:serviceaccount:${NAMESPACE}:${SA_NAME}"

echo "=== RBAC: pods in ${NAMESPACE} (must be yes) ==="
if ! kubectl auth can-i create pods --as="${DISPATCHER_AS}" -n "${NAMESPACE}"; then
  echo "ERROR: ${SA_NAME} cannot create pods in ${NAMESPACE}" >&2
  exit 1
fi

echo "=== RBAC: pods in ${AO_NAMESPACE} (must be no) ==="
if kubectl auth can-i create pods --as="${DISPATCHER_AS}" -n "${AO_NAMESPACE}"; then
  echo "ERROR: ${SA_NAME} can create pods in ${AO_NAMESPACE}; Role is too wide" >&2
  exit 1
fi

BACKEND_POD=$(_backend_pod)
echo "using backend pod ${BACKEND_POD} for schema + registration"

# AO operator pods expose APP_DB_* rather than APP_DATABASE_URL. Alembic only
# reads DATABASE_URL; register_kind_sa_target.py used to fall back to localhost.
_IN_POD_DATABASE_URL='
if [ -n "${APP_DATABASE_URL:-}" ]; then
  DATABASE_URL="${APP_DATABASE_URL}"
else
  DATABASE_URL="postgresql+asyncpg://${APP_DB_USER}:${APP_DB_PASSWORD}@${APP_DB_HOST}:${APP_DB_PORT:-5432}/${APP_DB_NAME}"
fi
export DATABASE_URL
'

echo "=== execution_plane schema ==="
kubectl exec -n "${AO_NAMESPACE}" "${BACKEND_POD}" -- /bin/sh -c "
${_IN_POD_DATABASE_URL}
cd /opt/app-root/src
/opt/app-root/src/.venv/bin/python -m alembic -c execution-plane/alembic.ini upgrade head
"

_write_to_pod() {
  local dest=$1
  kubectl exec -i -n "${AO_NAMESPACE}" "${BACKEND_POD}" -- /bin/sh -c "cat > ${dest}"
}

echo "=== Register ExecutionTarget (before worker start) ==="
# The AO image is UBI-minimal and has no tar, so kubectl cp cannot be used.
_write_to_pod /tmp/register_kind_sa_target.py < "${TOOLS_DIR}/register_kind_sa_target.py"
_write_to_pod /tmp/dev_cli.py < "${TOOLS_DIR}/dev_cli.py"
_write_to_pod /tmp/ao_registration.py < "${TOOLS_DIR}/ao_registration.py"
_write_to_pod /tmp/sa-token.txt < "${TOKEN_FILE}"
kubectl exec -n "${AO_NAMESPACE}" "${BACKEND_POD}" -- /bin/sh -c "
${_IN_POD_DATABASE_URL}
cd /tmp && PYTHONPATH=\"/tmp:\${PYTHONPATH:-/opt/app-root/src/src}\" \
  /opt/app-root/src/.venv/bin/python register_kind_sa_target.py /tmp/sa-token.txt \
  --cluster '${CLUSTER_NAME}' --namespace '${NAMESPACE}' --endpoint '${ENDPOINT}'
"
kubectl exec -n "${AO_NAMESPACE}" "${BACKEND_POD}" -- rm -f /tmp/sa-token.txt
echo "registered cluster ${CLUSTER_NAME} namespace ${NAMESPACE} endpoint ${ENDPOINT}"

echo "=== Deploy execution-plane-worker ==="
IMAGE=$(kubectl get deploy myao-backend -n "${AO_NAMESPACE}" -o jsonpath='{.spec.template.spec.containers[0].image}')
if [[ -z "${IMAGE}" ]]; then
  echo "ERROR: could not read myao-backend image" >&2
  exit 1
fi
echo "EP worker image: ${IMAGE}"

if ! DB_URL=$(_deploy_env_value APP_DATABASE_URL); then
  DB_URL=$(_database_url_from_secret)
else
  DB_URL=$(_qualify_svc_host "${DB_URL}" "${AO_NAMESPACE}")
fi
TEMPORAL_ADDR=$(_temporal_address)

kubectl create secret generic execution-plane-worker-env \
  --namespace "${NAMESPACE}" \
  --from-literal=APP_DATABASE_URL="${DB_URL}" \
  --dry-run=client -o yaml | kubectl apply -f -
unset DB_URL

_apply_worker_manifest "${IMAGE}" "${TEMPORAL_ADDR}"
_enable_ep_temporal_mtls

echo "=== Wait for execution-plane-worker ==="
kubectl rollout status deployment/execution-plane-worker -n "${NAMESPACE}" --timeout=180s
kubectl get pods -n "${NAMESPACE}" -o wide
_assert_temporal_tcp "${TEMPORAL_ADDR}"

_prepull_node_image "${NODE_IMAGE}"
_enable_script_dispatch "${NODE_IMAGE}"

echo "execution-plane worker is registered; script nodes dispatch ${NODE_IMAGE}"
