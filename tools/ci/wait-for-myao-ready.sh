#!/usr/bin/env bash
# Wait until AutomationOrchestrator/myao reports Ready=True.
#
# Catalog deploy-ao wait-for-ao-ready SSHes `kubectl wait --timeout=600s` with
# no ServerAliveInterval. With Execution Plane enabled that wait is silent for
# minutes; AWS idle NAT then drops the TCP session and Tekton reports
# "context deadline exceeded" with no CR status. This hook runs inside
# `skaffold deploy` (still producing SSH traffic) and dumps why Ready is stuck.
set -euo pipefail

export PATH="${HOME}/aap-dev/bin:${PATH}"

KUBECONFIG="${AAP_KUBECONFIG:-${KUBECONFIG:-}}"
NS="${AAP_KUBE_NAMESPACE:-aap27-next}"
NAME="${AO_NAME:-myao}"
TIMEOUT="${MYAO_READY_TIMEOUT_SECONDS:-720}"
INTERVAL="${MYAO_READY_POLL_SECONDS:-15}"

if [[ -z "${KUBECONFIG}" ]]; then
  echo "ERROR: AAP_KUBECONFIG / KUBECONFIG is not set" >&2
  exit 1
fi

kubectl_ns() {
  kubectl --kubeconfig="${KUBECONFIG}" -n "${NS}" "$@"
}

_dump() {
  echo "=== AutomationOrchestrator/${NAME} ==="
  kubectl_ns get automationorchestrator "${NAME}" -o yaml 2>&1 || true
  echo ""
  echo "=== Deployments / jobs / pods ==="
  kubectl_ns get deploy,sts,job,pods -o wide 2>&1 || true
  echo ""
  echo "=== operator RELATED_IMAGE_* ==="
  kubectl_ns get deploy automation-orchestrator-operator-controller-manager \
    -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' 2>&1 \
    | grep -E 'RELATED_IMAGE|EXECUTION' || true
  echo ""
  echo "=== operator logs ==="
  kubectl_ns logs deploy/automation-orchestrator-operator-controller-manager --tail=80 2>&1 || true
  echo ""
  echo "=== job logs ==="
  local job
  for job in $(kubectl_ns get jobs -o name 2>/dev/null || true); do
    echo "--- ${job} ---"
    kubectl_ns logs "${job}" --tail=80 2>&1 || true
  done
  echo ""
  echo "=== not-ready / non-running pods ==="
  local pod
  for pod in $(kubectl_ns get pods --no-headers 2>/dev/null | awk '$3 !~ /^(Running|Completed|Succeeded)$/ {print $1}'); do
    echo "--- describe ${pod} ---"
    kubectl_ns describe pod "${pod}" 2>&1 | tail -80 || true
    echo "--- logs ${pod} ---"
    kubectl_ns logs "${pod}" --all-containers --tail=80 2>&1 || true
  done
  echo ""
  echo "=== events ==="
  kubectl_ns get events --sort-by=.lastTimestamp 2>&1 | tail -40 || true
}

echo "=== Waiting for AutomationOrchestrator/${NAME} Ready in ${NS} (timeout ${TIMEOUT}s) ==="
elapsed=0
while (( elapsed < TIMEOUT )); do
  status=$(kubectl_ns get automationorchestrator "${NAME}" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
  reason=$(kubectl_ns get automationorchestrator "${NAME}" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].reason}' 2>/dev/null || true)
  message=$(kubectl_ns get automationorchestrator "${NAME}" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}' 2>/dev/null || true)
  pods=$(kubectl_ns get pods --no-headers 2>/dev/null | awk '{printf "%s:%s ", $1,$3}' || true)
  echo "$(date -u +%H:%M:%S) elapsed=${elapsed}s Ready=${status:-<unset>} reason=${reason:-} ${message}"
  echo "  pods: ${pods}"
  if [[ "${status}" == "True" ]]; then
    echo "AutomationOrchestrator/${NAME} is Ready."
    exit 0
  fi
  sleep "${INTERVAL}"
  elapsed=$((elapsed + INTERVAL))
done

echo "ERROR: AutomationOrchestrator/${NAME} not Ready after ${TIMEOUT}s" >&2
_dump
exit 1
