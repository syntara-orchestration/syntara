#!/usr/bin/env bash
# Validate hermetic prefetch parity with Konflux (pip + rpm + generic).
set -euo pipefail

BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE_ROOT="$(cd "${BACKEND_ROOT}/.." && pwd)"
HERMETO_IMAGE="${HERMETO_IMAGE:-quay.io/konflux-ci/hermeto:0.55.0@sha256:27936b01262824104cce87d433ffcb622bf906bc833033b6b05c62257f3c3232}"
OUTPUT_DIR="${BACKEND_ROOT}/.hermeto-output"
PREFETCH_OUTPUT_DIR="${OUTPUT_DIR}/output"
PREFETCH_MODE="${PREFETCH_MODE:-permissive}"
ENABLE_PACKAGE_REGISTRY_PROXY="${ENABLE_PACKAGE_REGISTRY_PROXY:-false}"
PREFETCH_INPUT_DEFAULT='[{"type":"pip","path":"backend","requirements_files":["requirements.txt","requirements-vcs.txt"]},{"type":"rpm","path":"backend"},{"type":"generic","path":"backend"}]'
PREFETCH_INPUT="${PREFETCH_INPUT:-${PREFETCH_INPUT_DEFAULT}}"
PIP_ONLY=false
LOG_FILE="${BACKEND_ROOT}/.hermeto-prefetch.log"
KEY_DIR=""

for arg in "$@"; do
	case "$arg" in
		--pip-only) PIP_ONLY=true ;;
		*)
			echo "Unknown argument: $arg" >&2
			exit 2
			;;
	esac
done

cd "${BACKEND_ROOT}"

cleanup() {
	[ -n "${KEY_DIR}" ] && rm -rf "${KEY_DIR}"
}
trap cleanup EXIT

require_rhsm() {
	: "${RHSM_ORG_ID:?missing RHSM_ORG_ID}"
	: "${RHSM_ACTIVATION_KEY:?missing RHSM_ACTIVATION_KEY}"
}

declare -a REQUIRED_BACKENDS=("pip" "rpm" "generic")
if [ "${PIP_ONLY}" = true ]; then
	REQUIRED_BACKENDS=("pip" "generic")
	PREFETCH_INPUT='[{"type":"pip","path":"backend","requirements_files":["requirements.txt","requirements-vcs.txt"]},{"type":"generic","path":"backend"}]'
fi

# Remove stale prefetch output from previous runs. Hermeto may generate
# cargo config/lock data under output/deps that can taint subsequent runs.
rm -rf "${PREFETCH_OUTPUT_DIR}"
rm -f \
	"${OUTPUT_DIR}/cachi2.env" \
	"${OUTPUT_DIR}/prefetch.env" \
	"${OUTPUT_DIR}/prefetch-env.json"

mkdir -p "${OUTPUT_DIR}" "${PREFETCH_OUTPUT_DIR}"

local_rhsm_args=""
declare -a podman_cmd=(
	podman run --rm
	-v "${WORKSPACE_ROOT}:/workspace:z"
	-w /workspace
	-e "PREFETCH_INPUT=${PREFETCH_INPUT}"
	-e "PREFETCH_MODE=${PREFETCH_MODE}"
	-e "ENABLE_PACKAGE_REGISTRY_PROXY=${ENABLE_PACKAGE_REGISTRY_PROXY}"
	--entrypoint /bin/bash
)

if [ "${PIP_ONLY}" = false ]; then
	require_rhsm
	KEY_DIR="$(mktemp -d)"
	printf "%s" "${RHSM_ORG_ID}" >"${KEY_DIR}/org"
	printf "%s" "${RHSM_ACTIVATION_KEY}" >"${KEY_DIR}/activationkey"
	podman_cmd+=(-v "${KEY_DIR}:/activation-key:ro,z")
	local_rhsm_args="--rhsm-org /activation-key/org --rhsm-activation-key /activation-key/activationkey"
fi

container_cmd="set -euo pipefail; \
konflux-build-cli --loglevel debug prefetch-dependencies \
  --source-dir /workspace \
  --output-dir /workspace/backend/.hermeto-output/output \
  --output-dir-mount-point /cachi2/output \
  --mode \"\$PREFETCH_MODE\" \
  --input \"\$PREFETCH_INPUT\" \
  --enable-package-registry-proxy=\"\$ENABLE_PACKAGE_REGISTRY_PROXY\" \
  --env-files /workspace/backend/.hermeto-output/cachi2.env \
  --env-files /workspace/backend/.hermeto-output/prefetch.env \
  --env-files /workspace/backend/.hermeto-output/prefetch-env.json \
  ${local_rhsm_args}"

podman_cmd+=("${HERMETO_IMAGE}" -lc "${container_cmd}")

set +e
{
	echo "Running command in hermeto container:"
	echo "konflux-build-cli --loglevel debug prefetch-dependencies --source-dir /workspace --output-dir /workspace/backend/.hermeto-output/output --output-dir-mount-point /cachi2/output --mode ${PREFETCH_MODE} --input '${PREFETCH_INPUT}' --enable-package-registry-proxy=${ENABLE_PACKAGE_REGISTRY_PROXY} ${local_rhsm_args}"
	"${podman_cmd[@]}"
} >"${LOG_FILE}" 2>&1
status=$?
set -e

tail -40 "${LOG_FILE}"

if [[ "${status}" -ne 0 ]]; then
	echo "❌ konflux-build-cli prefetch failed (exit ${status}). See ${LOG_FILE}" >&2
	exit "${status}"
fi

missing=0
for backend in "${REQUIRED_BACKENDS[@]}"; do
	if [ -d "${PREFETCH_OUTPUT_DIR}/deps/${backend}" ]; then
		echo "✅ ${backend}: ${PREFETCH_OUTPUT_DIR}/deps/${backend}"
	else
		echo "❌ ${backend}: missing ${PREFETCH_OUTPUT_DIR}/deps/${backend}" >&2
		missing=1
	fi
done

if [ "${missing}" -ne 0 ]; then
	exit 22
fi

echo "✅ Hermeto prefetch parity validation succeeded"
