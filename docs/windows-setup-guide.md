# Syntara Local Development Setup on Windows

This guide covers spinning up the full podman-compose environment on Windows (WSL2-backed Podman).

## Prerequisites

- **Podman Desktop** (or Podman CLI) installed with a WSL2 machine
- **Node.js 22+** and **npm**
- **uv** (Python package manager)
- **GNU Make** (e.g., via Chocolatey: `choco install make`)
- **Git Bash** or equivalent POSIX shell

## Windows-Specific Issues and Fixes

### 1. podman-compose: Windows drive letters parsed as git URLs

**Affects:** podman-compose <= 1.6.0

**Symptom:** `make build-images` or any `podman-compose build` fails with:

```
Error: no Containerfile or Dockerfile specified or found in context directory,
C:\Users\...\backend: The system cannot find the file specified.
```

**Root cause:** The `is_context_git_url()` function in podman-compose uses `urllib.parse.urlparse()` to detect git URLs. On Windows, a path like `C:\Users\...` gets parsed with `C` as a URL scheme (since `C:` looks like `scheme:`), causing podman-compose to skip Containerfile detection entirely.

**Fix:** Install podman-compose from the `main` branch, which includes [PR #1469](https://github.com/containers/podman-compose/pull/1469):

```bash
cd backend
uv pip install "podman-compose @ git+https://github.com/containers/podman-compose.git@main"
```

> **Note:** Running `uv sync` or `make install` reverts to the released v1.6.0. Re-run the command above after each sync until a new release ships the fix.

### 2. Alembic: `uv run alembic` fails with "Failed to canonicalize script path"

**Symptom:** `make db-migrate` fails because `uv run alembic upgrade head` errors on Windows.

**Workaround:** Run alembic as a Python module instead:

```bash
cd backend
uv run python -m alembic upgrade head
```

### 3. Audit worker: `os.uname()` not available on Windows

**Symptom:** The database seeder logs an `AttributeError: module 'os' has no attribute 'uname'` from the audit outbox worker.

**Impact:** Cosmetic only. The seeding completes successfully. This only affects the OTEL audit export path, which is not required for local development.

### 4. `make dev` fails on Windows

**Symptom:** `make dev` fails with `process_begin: CreateProcess(NULL, uname -s, ...) failed` and `'vite' is not recognized as an internal or external command`.

**Root cause:** GNU Make on Windows uses `cmd.exe` as its shell, even when invoked from Git Bash. This breaks:
- `uname -s` (Unix command, not available in cmd.exe)
- Single-quoted arguments in `concurrently 'vite --open'` (cmd.exe doesn't support single quotes)
- Inline environment variables like `VITE_API_URL=https://localhost:8000 npm run start`

**Workaround:** Use the containerized Temporal workers (from `make services-up`) and run only the API and frontend locally. The backend must run with `APP_S2S_TLS_ENABLED=false` and the frontend must point to `http://` (not `https://`) — otherwise the Vite proxy fails with `wrong version number` because it cannot negotiate TLS 1.3 + mTLS with the backend.

Open two Git Bash terminals:

```bash
# Terminal 1 — Backend API (TLS disabled for local dev)
cd backend && APP_S2S_TLS_ENABLED=false uv run python -m syntara.api.main

# Terminal 2 — Frontend UI (http, not https)
cd frontend/packages/syntara-ui && VITE_API_URL=http://localhost:8000 npx vite
```

### 5. `python-magic` crashes on Windows

**Symptom:** `import magic` raises `OSError: exception: access violation reading 0xFFFFFFFFFFFFFFFF`.

**Root cause:** The `python-magic` package requires the `libmagic` C library, which is not bundled on Windows.

**Fix:** Install `python-magic-bin`, which bundles the library:

```bash
cd backend
uv pip install python-magic-bin
```

### 6. Temporal worker crashes with `NotImplementedError` on Windows

**Symptom:** `uv run python -m syntara.workflows.worker` raises `NotImplementedError` at `loop.add_signal_handler(signal.SIGINT, ...)`.

**Root cause:** `asyncio.add_signal_handler()` is not implemented on Windows.

**Workaround:** Do not run the Temporal worker locally. Use the containerized workers instead — `make services-up` starts `syntara_temporal-worker_1` and `syntara_temporal-background-worker_1` in containers. Only start the backend API and frontend on the host.

## Step-by-Step Setup

### 1. Start the Podman machine

```bash
podman machine start
```

If no machine exists, create one first:

```bash
podman machine init
podman machine start
```

Verify it's running:

```bash
podman machine list
# Should show STATUS: Running
```

### 2. Install backend dependencies

```bash
cd backend && uv sync --extra dev
```

> **Note:** `make -C backend install` does not work on Windows — GNU Make uses `cmd.exe` as its shell, and the `_check-uv` target uses Bash syntax (`if ! command -v uv`). Run `uv sync` directly from Git Bash instead.

### 3. Fix podman-compose (Windows-only)

```bash
cd backend
uv pip install "podman-compose @ git+https://github.com/containers/podman-compose.git@main"
```

### 4. Install frontend dependencies

The `"win32"` fix is already included in this branch (see issue #2 above). Run:

```bash
cd frontend && npm ci
```

### 5. Generate secrets

```bash
make secrets
```

Creates JWT keys, admin password, and encryption key in `backend/.secrets/`.

### 6. Generate TLS certificates

```bash
make certs
```

Creates self-signed CA and service certificates in `backend/.secrets/certs/` for mTLS between services.

### 7. Build container images

```bash
make build-images
```

Builds the `localhost/syntara:latest` and `localhost/syntara-mcp:latest` images.

### 8. Start all infrastructure services

```bash
make services-up
```

Starts 9 containers in the background:

| Service                    | Port  | Container                          |
|----------------------------|-------|------------------------------------|
| PostgreSQL                 | 5432  | `syntara_database_1`               |
| Redis                      | 6379  | `syntara_redis_1`                  |
| Moto (S3 mock)             | 5555  | `syntara_moto_1`                   |
| Temporal Server            | 7233  | `syntara_temporal_1`               |
| Temporal UI                | 8081  | `syntara_temporal-ui_1`            |
| Temporal Worker            | -     | `syntara_temporal-worker_1`        |
| Temporal Background Worker | -     | `syntara_temporal-background-worker_1` |
| MCP Server                 | 8765  | `syntara_mcp-server_1`             |
| MCP Scenarios              | 8766-8767 | `syntara_mcp-server-scenarios_1` |

### 9. Run database migrations

```bash
cd backend
uv run python -m alembic upgrade head
```

### 10. Seed the database

```bash
make db-seed
```

The Temporal connectivity warnings during seeding are expected when running the seeder from the host (it can't reach the containerized Temporal via mTLS).

### 11. Sync the admin password

```bash
make admin-password
```

### 12. Verify

```bash
cd backend
uv run podman-compose -p syntara -f ../podman-compose.yml ps
```

All services should show `(healthy)` status.

## Day-to-Day Commands

```bash
# Start infrastructure (if stopped) — includes containerized Temporal workers
make services-up

# Start dev servers (two separate Git Bash terminals — workers run in containers)
cd backend && APP_S2S_TLS_ENABLED=false uv run python -m syntara.api.main         # Terminal 1 — Backend API (no TLS)
cd frontend/packages/syntara-ui && VITE_API_URL=http://localhost:8000 npx vite    # Terminal 2 — Frontend (http)

# View service logs
make services-logs

# Stop all services
make services-down

# Rebuild images after code changes
make build-images

# Re-run migrations after schema changes
cd backend && uv run python -m alembic upgrade head
```

> **Note:** `make dev` does not work on Windows — see issue #5 above. Use the individual commands instead.

## Troubleshooting

### Podman machine not running

```
Cannot connect to Podman. Please verify your connection to the Linux system
using `podman system connection list`, or try `podman machine init` and
`podman machine start` to manage a new Linux VM
```

**Fix:** `podman machine start`

### Services won't start after reboot

The Podman machine doesn't auto-start on Windows. Run:

```bash
podman machine start
make services-up
```

### podman-compose reverted after `uv sync`

Re-apply the fix:

```bash
cd backend
uv pip install "podman-compose @ git+https://github.com/containers/podman-compose.git@main"
```
