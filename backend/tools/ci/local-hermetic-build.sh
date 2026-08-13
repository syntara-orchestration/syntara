#!/usr/bin/env bash
# Build the container locally simulating a hermetic Konflux build (pip + rpm + generic).
#
# Usage:
#   bash tools/ci/local-hermetic-build.sh                         # full build (prefetch + KBC build)
#   bash tools/ci/local-hermetic-build.sh --skip-prefetch         # reuse cached prefetch
#   bash tools/ci/local-hermetic-build.sh --shell                 # drop into builder for debugging
#   bash tools/ci/local-hermetic-build.sh --pip-only              # skip rpm + RHSM requirements
#   bash tools/ci/local-hermetic-build.sh --offline-build         # explicit offline mode (default)
#   bash tools/ci/local-hermetic-build.sh --cache-mode graphroot  # use host GraphRoot cache instead of volume
set -euo pipefail

BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE_ROOT="$(cd "${BACKEND_ROOT}/.." && pwd)"
HERMETO_IMAGE="${HERMETO_IMAGE:-quay.io/konflux-ci/hermeto:0.55.0@sha256:27936b01262824104cce87d433ffcb622bf906bc833033b6b05c62257f3c3232}"
KBC_IMAGE="${KBC_IMAGE:-quay.io/konflux-ci/konflux-build-cli:latest}"
OUTPUT_DIR="${BACKEND_ROOT}/.hermeto-output"
PREFETCH_OUTPUT_DIR="${OUTPUT_DIR}/output"
IMAGE_TAG="${IMAGE_TAG:-localhost/syntara-local:hermetic}"
PREFETCH_MODE="${PREFETCH_MODE:-permissive}"
ENABLE_PACKAGE_REGISTRY_PROXY="${ENABLE_PACKAGE_REGISTRY_PROXY:-false}"
PREFETCH_INPUT_DEFAULT='[{"type":"pip","path":"backend"},{"type":"rpm","path":"backend"},{"type":"generic","path":"backend"}]'
PREFETCH_INPUT="${PREFETCH_INPUT:-${PREFETCH_INPUT_DEFAULT}}"
KBC_CACHE_MODE="${KBC_CACHE_MODE:-volume}"
KBC_STORAGE_VOLUME="${KBC_STORAGE_VOLUME:-kbc-storage-cache}"
KBC_INCLUDE_SOURCE_REPOS="${KBC_INCLUDE_SOURCE_REPOS:-false}"
SKIP_PREFETCH=false
SHELL_MODE=false
PIP_ONLY=false
OFFLINE_BUILD=true
KEY_DIR=""
AUTH_FILE=""
GRAPHROOT=""
BUILD_LOG="${BACKEND_ROOT}/.kbc-build.log"
WORKTREE_GIT_BACKUP=false
GIT_COMMON_HOST_DIR=""

while [ "$#" -gt 0 ]; do
	arg="$1"
	case "$arg" in
		--skip-prefetch)
			SKIP_PREFETCH=true
			shift
			;;
		--shell)
			SHELL_MODE=true
			shift
			;;
		--pip-only)
			PIP_ONLY=true
			shift
			;;
		--offline-build)
			OFFLINE_BUILD=true
			shift
			;;
		--cache-mode)
			if [ "$#" -lt 2 ]; then
				echo "ERROR: --cache-mode requires a value (volume|graphroot)" >&2
				exit 2
			fi
			KBC_CACHE_MODE="$2"
			shift 2
			;;
		--cache-mode=*)
			KBC_CACHE_MODE="${arg#*=}"
			shift
			;;
		*)
			echo "Unknown argument: $arg" >&2
			exit 2
			;;
	esac
done

cd "${BACKEND_ROOT}"

restore_worktree_git() {
	local ws_git="${WORKSPACE_ROOT}/.git"
	if [ "${WORKTREE_GIT_BACKUP}" = true ] && [ -f "${ws_git}.worktree-backup" ]; then
		rm -rf "${ws_git}"
		mv "${ws_git}.worktree-backup" "${ws_git}"
		WORKTREE_GIT_BACKUP=false
	fi
}

prepare_worktree_git() {
	local ws_git="${WORKSPACE_ROOT}/.git"

	# Recover from a previously interrupted run
	if [ -f "${ws_git}.worktree-backup" ]; then
		if [ -d "${ws_git}" ]; then
			rm -rf "${ws_git}"
		fi
		mv "${ws_git}.worktree-backup" "${ws_git}"
	fi

	# Only act when .git is a file (worktree pointer)
	[ -f "${ws_git}" ] || return 0

	echo "=== Detected git worktree; preparing .git directory for container ==="

	local real_common_dir current_head
	real_common_dir="$(cd "$(git -C "${WORKSPACE_ROOT}" rev-parse --git-common-dir)" && pwd)"
	current_head="$(git -C "${WORKSPACE_ROOT}" rev-parse HEAD)"

	mv "${ws_git}" "${ws_git}.worktree-backup"

	mkdir -p "${ws_git}/objects/info" "${ws_git}/refs"
	cp "${real_common_dir}/config" "${ws_git}/config"
	printf "%s\n" "${current_head}" >"${ws_git}/HEAD"

	# Point git alternates at the container-mounted main repo objects so
	# Hermeto can resolve commits without copying 300+ MB of pack data.
	printf "/git-common/objects\n" >"${ws_git}/objects/info/alternates"

	# packed-refs is needed to resolve branch/tag names
	[ -f "${real_common_dir}/packed-refs" ] && \
		cp "${real_common_dir}/packed-refs" "${ws_git}/packed-refs"

	GIT_COMMON_HOST_DIR="${real_common_dir}"
	WORKTREE_GIT_BACKUP=true
}

cleanup() {
	restore_worktree_git
	[ -n "${KEY_DIR}" ] && rm -rf "${KEY_DIR}"
}
trap cleanup EXIT

ensure_cache_mode() {
	case "${KBC_CACHE_MODE}" in
		volume|graphroot) ;;
		*)
			echo "ERROR: invalid cache mode '${KBC_CACHE_MODE}'. Use 'volume' or 'graphroot'." >&2
			exit 2
			;;
	esac
}

require_rhsm() {
	: "${RHSM_ORG_ID:?missing RHSM_ORG_ID}"
	: "${RHSM_ACTIVATION_KEY:?missing RHSM_ACTIVATION_KEY}"
}

declare -a REQUIRED_BACKENDS=("pip" "rpm" "generic")
if [ "${PIP_ONLY}" = true ]; then
	REQUIRED_BACKENDS=("pip" "generic")
	PREFETCH_INPUT='[{"type":"pip","path":"backend"},{"type":"generic","path":"backend"}]'
fi

resolve_auth_file() {
	if [ -n "${REGISTRY_AUTH_FILE:-}" ] && [ -f "${REGISTRY_AUTH_FILE}" ]; then
		AUTH_FILE="${REGISTRY_AUTH_FILE}"
		return
	fi

	local runtime_auth="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/containers/auth.json"
	if [ -f "${runtime_auth}" ]; then
		AUTH_FILE="${runtime_auth}"
		return
	fi

	local docker_auth="${HOME}/.docker/config.json"
	if [ -f "${docker_auth}" ]; then
		AUTH_FILE="${docker_auth}"
		return
	fi

	echo "ERROR: No registry auth file found. Run: podman login registry.redhat.io" >&2
	exit 1
}

resolve_cache_mount() {
	case "${KBC_CACHE_MODE}" in
		volume)
			podman volume create "${KBC_STORAGE_VOLUME}" >/dev/null
			printf "%s" "${KBC_STORAGE_VOLUME}:/var/lib/containers/storage:Z"
			;;
		graphroot)
			GRAPHROOT="$(podman info --format '{{.Store.GraphRoot}}')"
			if [ ! -d "${GRAPHROOT}" ]; then
				echo "ERROR: GraphRoot does not exist: ${GRAPHROOT}" >&2
				exit 1
			fi
			printf "%s" "${GRAPHROOT}:/var/lib/containers/storage:Z"
			;;
	esac
}

prefetch_cache_available() {
	local backend
	for backend in "${REQUIRED_BACKENDS[@]}"; do
		if [ ! -d "${PREFETCH_OUTPUT_DIR}/deps/${backend}" ]; then
			return 1
		fi
	done
	[ -f "${OUTPUT_DIR}/cachi2.env" ]
}

run_prefetch() {
	# Remove stale prefetch output from previous runs. Hermeto may generate
	# cargo config/lock data under output/deps that can taint subsequent runs.
	rm -rf "${PREFETCH_OUTPUT_DIR}"
	rm -f \
		"${OUTPUT_DIR}/cachi2.env" \
		"${OUTPUT_DIR}/prefetch.env" \
		"${OUTPUT_DIR}/prefetch-env.json"

	mkdir -p "${OUTPUT_DIR}" "${PREFETCH_OUTPUT_DIR}"

	local rhsm_args=""
	local -a podman_cmd=(
		podman run --rm
		-v "${WORKSPACE_ROOT}:/workspace:z"
		-w /workspace
		-e "PREFETCH_INPUT=${PREFETCH_INPUT}"
		-e "PREFETCH_MODE=${PREFETCH_MODE}"
		-e "ENABLE_PACKAGE_REGISTRY_PROXY=${ENABLE_PACKAGE_REGISTRY_PROXY}"
		--entrypoint /bin/bash
	)

	if [ -n "${GIT_COMMON_HOST_DIR}" ]; then
		podman_cmd+=(-v "${GIT_COMMON_HOST_DIR}:/git-common:ro,z")
	fi

	if [ "${PIP_ONLY}" = false ]; then
		require_rhsm
		KEY_DIR="$(mktemp -d)"
		printf "%s" "${RHSM_ORG_ID}" >"${KEY_DIR}/org"
		printf "%s" "${RHSM_ACTIVATION_KEY}" >"${KEY_DIR}/activationkey"
		podman_cmd+=(-v "${KEY_DIR}:/activation-key:ro,z")
		rhsm_args="--rhsm-org /activation-key/org --rhsm-activation-key /activation-key/activationkey"
	fi

	local container_cmd
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
  ${rhsm_args}"

	podman_cmd+=("${HERMETO_IMAGE}" -lc "${container_cmd}")
	"${podman_cmd[@]}"
}

collect_base_images() {
	local containerfile="${BACKEND_ROOT}/containers/syntara/Containerfile"
	local -a base_images
	local image=""

	while IFS= read -r line; do
		line="${line#"${line%%[![:space:]]*}"}"
		[[ -z "${line}" ]] && continue
		[[ "${line}" =~ ^# ]] && continue
		if [[ "${line}" =~ ^FROM[[:space:]]+([^[:space:]]+) ]]; then
			image="${BASH_REMATCH[1]}"
			base_images+=("${image}")
		fi
	done <"${containerfile}"

	if [ "${#base_images[@]}" -eq 0 ]; then
		echo "ERROR: no FROM images found in ${containerfile}" >&2
		exit 1
	fi

	mapfile -t base_images < <(printf "%s\n" "${base_images[@]}" | sort -u)
	printf "%s\n" "${base_images[@]}"
}

prepull_base_images() {
	local image=""
	local storage_mount="$1"
	mapfile -t base_images < <(collect_base_images)
	echo "=== Pre-pulling base images before hermetic build ==="

	for image in "${base_images[@]}"; do
		echo "  ensuring: ${image}"
		if [ "${KBC_CACHE_MODE}" = "graphroot" ]; then
			podman image exists "${image}" || podman pull --authfile "${AUTH_FILE}" "${image}"
			podman image exists "${image}" || {
				echo "ERROR: base image missing after pull: ${image}" >&2
				exit 1
			}
		else
			podman run --rm --privileged -u 0 \
				-e REGISTRY_AUTH_FILE=/tmp/host-auth.json \
				-v "${AUTH_FILE}:/tmp/host-auth.json:ro,Z" \
				-v "${storage_mount}" \
				--entrypoint /bin/bash \
				"${KBC_IMAGE}" \
				-lc "set -euo pipefail; buildah pull --authfile /tmp/host-auth.json '${image}' >/dev/null"
		fi
	done
}

require_prefetch_outputs() {
	local backend=""
	for backend in "${REQUIRED_BACKENDS[@]}"; do
		local p="${PREFETCH_OUTPUT_DIR}/deps/${backend}"
		if [ ! -d "${p}" ]; then
			echo "ERROR: missing prefetch output directory: ${p}" >&2
			exit 1
		fi
	done
	if [ ! -f "${OUTPUT_DIR}/cachi2.env" ]; then
		echo "ERROR: missing prefetch environment file: ${OUTPUT_DIR}/cachi2.env" >&2
		exit 1
	fi
}

build_with_kbc() {
	ensure_cache_mode
	resolve_auth_file
	require_prefetch_outputs

	local storage_mount
	storage_mount="$(resolve_cache_mount)"

	if [ "${OFFLINE_BUILD}" = true ]; then
		prepull_base_images "${storage_mount}"
	fi

	echo "=== Building container image with konflux-build-cli ==="
	echo "  driver: konflux-build-cli image build"
	echo "  cache mode: ${KBC_CACHE_MODE}"
	echo "  hermetic: true"
	echo "  offline pre-pull: ${OFFLINE_BUILD}"
	echo "  output image: ${IMAGE_TAG}"

	local -a kbc_args=(
		image build
		-f /workspace/backend/containers/syntara/Containerfile
		-t "${IMAGE_TAG}"
		--source /workspace
		--context backend
		--hermetic
		--prefetch-dir /var/workdir/cachi2
		--prefetch-dir-copy /var/workdir/prefetch-copy
		--prefetch-env-mount /cachi2/cachi2.env
		--prefetch-output-mount /cachi2/output
	)
	if [ "${KBC_INCLUDE_SOURCE_REPOS}" = "true" ]; then
		echo "  extra yum repos: /workspace/backend/repositories (enabled)"
		echo "  WARNING: this may re-enable external rhel-9 repos in hermetic mode." >&2
		kbc_args+=(
			--yum-repos-d-sources /workspace/backend/repositories
			--yum-repos-d-target /etc/yum.repos.d
		)
	else
		echo "  extra yum repos: disabled (using prefetch-provided cachi2.repo)"
	fi

	local -a podman_cmd=(
		podman run --rm -i --privileged -u 0
		-e REGISTRY_AUTH_FILE=/tmp/host-auth.json
		-v "${AUTH_FILE}:/tmp/host-auth.json:ro,Z"
		-v "${storage_mount}"
		-v "${WORKSPACE_ROOT}:/workspace:Z"
		-v "${OUTPUT_DIR}:/var/workdir/cachi2:Z"
		-w /workspace
		--entrypoint /usr/local/bin/konflux-build-cli
	)
	if [ -n "${GIT_COMMON_HOST_DIR}" ]; then
		podman_cmd+=(-v "${GIT_COMMON_HOST_DIR}:/git-common:ro,z")
	fi
	podman_cmd+=("${KBC_IMAGE}")

	set +e
	"${podman_cmd[@]}" "${kbc_args[@]}" 2>&1 | tee "${BUILD_LOG}"
	local status=${PIPESTATUS[0]}
	set -e

	if [ "${status}" -ne 0 ]; then
		if grep -Eq 'rhel-9-for-|cdn\.redhat\.com' "${BUILD_LOG}"; then
			echo "HINT: build attempted external RHEL repos. Keep KBC_INCLUDE_SOURCE_REPOS=false for hermetic local builds." >&2
		fi
		echo "ERROR: konflux-build-cli image build failed. See ${BUILD_LOG}" >&2
		exit "${status}"
	fi
	echo "=== Build complete: ${IMAGE_TAG} ==="
}

# ── Step 0: Worktree support ─────────────────────────────────────────────────
# Hermeto requires an 'origin' remote. In a git worktree the .git file is a
# pointer to the main repo's .git/worktrees/ dir, which is outside the
# container mount. Replace it with a minimal .git/ directory for the build.
prepare_worktree_git

# ── Step 1: Prefetch dependencies (pip/rpm/generic) ──────────────────────────
if [ "${SKIP_PREFETCH}" = true ] && prefetch_cache_available; then
	echo "=== Reusing cached prefetch in ${PREFETCH_OUTPUT_DIR} ==="
else
	echo "=== Prefetching dependencies with konflux-build-cli ==="
	if [ "${PIP_ONLY}" = true ]; then
		echo "=== Pip-only mode enabled (rpm prefetch skipped) ==="
	fi
	run_prefetch
	echo "=== Prefetch complete ==="
fi

if [ "${SHELL_MODE}" = true ]; then
	echo "=== Launching interactive builder shell ==="
	echo "Inside the container:"
	echo "  source /cachi2/cachi2.env"
	echo "  uv sync --frozen --no-index --find-links \"\${PIP_FIND_LINKS}\" --offline"
	echo ""
	podman run --rm -it \
		-v "${OUTPUT_DIR}:/cachi2:z" \
		-v "${BACKEND_ROOT}:${BACKEND_ROOT}:z" \
		-w "${BACKEND_ROOT}" \
		-e PYTHON=python3.12 \
		-e PYO3_PYTHON=python3.12 \
		registry.redhat.io/rust-builder-image/rust-rhel9:1.94.1@sha256:4de71f3c0702c617e9f79a5d40dd025d9b8189a135fe73be93d3ecef6871d821 \
		bash
else
	build_with_kbc
fi
