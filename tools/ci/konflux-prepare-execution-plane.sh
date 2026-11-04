#!/usr/bin/env bash
# Intentional no-op.
#
# Every responsibility of this script moved elsewhere:
#   - dispatcher credential, cluster registration (openshift Integration),
#     and execution-target placement: aap-dev's configure-ep-execution-target
#     after-deploy hook (ansible/aap-dev#1141), gated on
#     AO_EXECUTION_PLANE=true;
#   - waiting for the EP API/worker and wiring myao-worker for script Steps:
#     aap-dev's configure-ao-sdk-script-step hook;
#   - AO<->EP callback wiring: the operator reconcile;
#   - dispatcher RBAC verification: tests/e2e/test_execution_target_rbac.py.
#
# The file remains (empty) because the ao-api-tests bundle pipeline's
# prepare-execution-plane task checks for its existence before running it.
# Drop both once that task is removed from the bundle.
set -euo pipefail

echo "==> konflux-prepare-execution-plane.sh is a no-op: the aap-dev deploy hooks own the Execution Plane wiring"
