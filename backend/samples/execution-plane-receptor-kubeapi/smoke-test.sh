#!/usr/bin/env bash
set -euo pipefail

sample_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
control_ns=syntara-control-poc
execution_ns=syntara-execution-poc

oc apply -k "$sample_dir"
oc -n "$control_ns" rollout status deployment/receptor-hub --timeout=120s
oc -n "$execution_ns" rollout status deployment/receptor-bridge --timeout=120s
oc -n "$execution_ns" rollout status deployment/http-executor-worker --timeout=120s

oc -n "$control_ns" delete job/dispatcher-poc --ignore-not-found
oc -n "$control_ns" apply -f "$sample_dir/dispatcher-poc.yaml"
oc -n "$control_ns" wait --for=condition=complete job/dispatcher-poc --timeout=120s
oc -n "$control_ns" logs job/dispatcher-poc | tee /dev/stderr | jq -e '.ok == true and .result.ok == true and .result.status_code == 200' >/dev/null
