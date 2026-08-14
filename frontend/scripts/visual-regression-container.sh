#!/usr/bin/env bash
# Run visual regression tests inside a Linux container that matches CI.
# Supports both Docker and Podman — whichever is available on your machine.
#
# Usage:
#   ./scripts/visual-regression-container.sh             # compare mode
#   ./scripts/visual-regression-container.sh --update     # update baselines
set -euo pipefail

# --- Detect container runtime (Docker or Podman) ---
# Prefer Podman when it has a running machine; fall back to Docker.
RUNTIME=""
if command -v podman &>/dev/null; then
  # On macOS, Podman requires a running VM — check it actually works before selecting it.
  if [[ "$(uname -s)" != "Darwin" ]] || podman machine list --format '{{.Running}}' 2>/dev/null | grep -q "true"; then
    RUNTIME="podman"
  fi
fi
if [[ -z "${RUNTIME}" ]]; then
  if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    RUNTIME="docker"
  elif command -v podman &>/dev/null; then
    # Podman is installed but machine isn't running — give a helpful error.
    echo "Error: Podman is installed but no machine is running."
    echo "Start one with: podman machine init && podman machine start"
    echo "Or install and start Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
  else
    echo "Error: Neither Docker nor Podman is installed."
    echo ""
    echo "Install one of:"
    echo "  Podman (recommended): brew install podman && podman machine init --memory 4096 && podman machine start"
    echo "  Docker:               https://docs.docker.com/get-docker/"
    exit 1
  fi
fi

echo "Using container runtime: ${RUNTIME}"

# --- Podman-specific preflight on macOS: verify machine has enough RAM ---
if [[ "${RUNTIME}" == "podman" && "$(uname -s)" == "Darwin" ]]; then
  MIN_MEMORY_MB=4096
  MACHINE_MEMORY=$(podman machine inspect --format '{{.Resources.Memory}}' 2>/dev/null || echo "0")
  if [[ "${MACHINE_MEMORY}" -lt "${MIN_MEMORY_MB}" ]]; then
    echo "Error: Podman machine has ${MACHINE_MEMORY}MB RAM. At least ${MIN_MEMORY_MB}MB is required."
    echo "Increase it with:"
    echo "  podman machine stop && podman machine set --memory ${MIN_MEMORY_MB} && podman machine start"
    exit 1
  fi
fi

# --- Resolve paths ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Extract Playwright version from lockfile ---
PW_VERSION=$(grep -A3 '"node_modules/@playwright/test"' "${REPO_ROOT}/package-lock.json" \
  | grep '"version"' \
  | head -1 \
  | sed 's/.*"version": *"\([^"]*\)".*/\1/')

if [[ -z "${PW_VERSION}" ]]; then
  echo "Error: Could not determine Playwright version from package-lock.json"
  exit 1
fi

if [[ ! "${PW_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: Playwright version '${PW_VERSION}' does not look like a valid semver string"
  exit 1
fi

IMAGE="mcr.microsoft.com/playwright:v${PW_VERSION}-noble"
echo "Using Playwright image: ${IMAGE}"

# --- Parse arguments ---
UPDATE_FLAG=""
if [[ "${1:-}" == "--update" || "${1:-}" == "--update-snapshots" ]]; then
  UPDATE_FLAG="--update-snapshots"
  echo "Mode: update baselines"
else
  echo "Mode: compare against existing baselines"
fi
echo ""

SNAPSHOT_DIR="packages/syntara-ui/e2e/visual-regression/page-screenshots.spec.ts-snapshots"
API_PORT=3300
UI_PORT=4173

# --- Docker credential workaround ---
# docker-credential-osxkeychain is referenced in ~/.docker/config.json on macOS
# but may not be in PATH (common with Docker Desktop). Public registries like
# mcr.microsoft.com don't need credentials — use a bare config to skip the helper.
#
# The config path is passed to Python as argv rather than interpolated into the
# script source, so a HOME containing shell/Python metacharacters can't inject code.
DOCKER_CONFIG_PATH="${HOME}/.docker/config.json"
if [[ "${RUNTIME}" == "docker" ]] \
  && [[ -f "${DOCKER_CONFIG_PATH}" ]] \
  && grep -q '"credsStore"' "${DOCKER_CONFIG_PATH}" 2>/dev/null \
  && ! command -v "docker-credential-$(python3 -c "import json, sys; print(json.load(open(sys.argv[1])).get('credsStore',''))" "${DOCKER_CONFIG_PATH}" 2>/dev/null)" &>/dev/null; then
  _DOCKER_CREDS_DIR=$(mktemp -d)
  echo '{}' > "${_DOCKER_CREDS_DIR}/config.json"
  export DOCKER_CONFIG="${_DOCKER_CREDS_DIR}"
  echo "Note: docker-credential-osxkeychain not in PATH — using anonymous config for public registry pull."
fi

# --- Run the container ---
# Source is copied to /work (excluding node_modules/.git) so npm ci installs
# Linux-native binaries without corrupting the host. The build + servers run
# manually because the Vite build exceeds Playwright's default 180s webServer
# timeout under emulation. Updated snapshots are copied back to the host.
#
# Chromium needs more than the default 64MB /dev/shm or it crashes/renders
# inconsistently. --shm-size grows the container's own shared memory instead of
# reaching for --ipc=host, which would share (and expose) the host's IPC namespace.
set +e
"${RUNTIME}" run --rm \
  --platform linux/amd64 \
  --shm-size=2gb \
  -v "${REPO_ROOT}:/repo:ro" \
  -v "${REPO_ROOT}/${SNAPSHOT_DIR}:/output" \
  "${IMAGE}" \
  bash -c "
    set -euo pipefail

    cleanup() { kill \$(jobs -p) 2>/dev/null || true; }
    trap cleanup EXIT

    echo '--- Copying source files ---'
    mkdir -p /work
    (cd /repo && tar cf - \
      --exclude='node_modules' \
      --exclude='.git' \
      --exclude='test-results' \
      --exclude='playwright-report' \
      .) | (cd /work && tar xf -)
    cd /work

    echo '--- Installing dependencies ---'
    npm ci --no-fund --no-audit

    echo ''
    echo '--- Building app (production) ---'
    # NODE_OPTIONS limits heap to reduce memory pressure under amd64 emulation on
    # Apple Silicon. The build may segfault on Node.js cleanup even when dist output
    # is already written -- check for dist/index.html rather than trusting exit code.
    set +e
    NODE_OPTIONS='--max-old-space-size=4096' \
    VITE_API_URL=http://localhost:${API_PORT} \
    npm run build --prefix packages/syntara-ui
    BUILD_EXIT=\$?
    set -e
    if [[ \$BUILD_EXIT -ne 0 ]]; then
      if [[ -f packages/syntara-ui/dist/index.html ]]; then
        echo \"Note: build exited \${BUILD_EXIT} but dist output exists, continuing.\"
      else
        echo \"Build failed (exit \${BUILD_EXIT}) and no dist/index.html found.\"
        exit \${BUILD_EXIT}
      fi
    fi

    echo ''
    echo '--- Starting mock API and preview server ---'
    PORT=${API_PORT} npm run start --prefix packages/syntara-mock-api &
    (cd packages/syntara-ui && npx vite preview --port ${UI_PORT}) &

    echo 'Waiting for servers...'
    for i in \$(seq 1 60); do
      API_OK=\$(curl -so /dev/null -w '%{http_code}' http://localhost:${API_PORT}/api/v1/workflows 2>/dev/null || echo '000')
      UI_OK=\$(curl -so /dev/null -w '%{http_code}' http://localhost:${UI_PORT} 2>/dev/null || echo '000')
      if [[ \$API_OK =~ ^[23] ]] && [[ \$UI_OK =~ ^[23] ]]; then
        echo \"Servers ready (API: \${API_OK}, UI: \${UI_OK}).\"
        break
      fi
      if [[ \$i -eq 60 ]]; then
        echo \"Error: Servers did not start within 60 seconds (API: \${API_OK}, UI: \${UI_OK}).\"
        exit 1
      fi
      sleep 1
    done

    echo ''
    echo '--- Running visual regression tests ---'
    TEST_EXIT=0
    cd packages/syntara-ui
    SYNTARA_E2E_BASE_URL=http://localhost:${UI_PORT} \
    SYNTARA_E2E_API_PORT=${API_PORT} \
    npx playwright test e2e/visual-regression/page-screenshots.spec.ts ${UPDATE_FLAG} || TEST_EXIT=\$?

    echo ''
    echo '--- Copying snapshots to host ---'
    cp -r e2e/visual-regression/page-screenshots.spec.ts-snapshots/. /output/
    COPY_EXIT=\$?
    if [[ \$COPY_EXIT -ne 0 ]]; then
      echo \"Error: Failed to copy snapshots to host (exit code \${COPY_EXIT})\"
      exit 1
    fi

    exit \${TEST_EXIT}
  "
EXIT_CODE=$?
set -e

echo ""
if [[ -n "${UPDATE_FLAG}" ]]; then
  echo "Baselines updated. Review changes with:"
  echo "  git diff --stat ${SNAPSHOT_DIR}/"
else
  if [[ ${EXIT_CODE} -eq 0 ]]; then
    echo "Visual regression tests passed."
  else
    echo "Visual regression tests failed (exit code ${EXIT_CODE})."
    echo ""
    echo "To accept intentional UI changes, update the baselines:"
    echo "  npm run e2e:visual-regression:container:update"
    echo ""
    echo "To see a diff report, open playwright-report/index.html after running:"
    echo "  npm run e2e:visual-regression:container"
  fi
fi

exit ${EXIT_CODE}
