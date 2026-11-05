---
name: podman-compose-spinup-pr
description: "Spin up the full podman-compose environment to locally test a specific PR."
user-invocable: true
---

Spin up the Syntara podman-compose environment to locally test a PR. The user provides a PR number or branch name as the argument (e.g. `/podman-compose-spinup-pr 936` or `/podman-compose-spinup-pr feat/my-branch`).

Windows-specific workarounds are documented in [`docs/windows-setup-guide.md`](../../../docs/windows-setup-guide.md).

## Phase 1: Resolve the PR and check out the branch

1. **Parse the argument.** If the user passed a number, treat it as a GitHub PR number. If they passed a string, treat it as a branch name.

2. **Fetch PR metadata** (if a PR number was given):

   ```bash
   gh pr view <PR_NUMBER> --json headRefName,title,state,url
   ```

   Confirm the PR is open. Show the user the PR title and branch name.

3. **Stash any uncommitted work** to avoid losing changes:

   ```bash
   git stash -u -m "podman-compose-spinup-pr: stash before checking out PR"
   ```

   Only stash if `git status` shows uncommitted changes. If you stashed, immediately capture the stash entry SHA so the user can restore it safely later:

   ```bash
   git stash list --format='%H %gs' | head -1
   ```

   Tell the user the stash SHA so they can restore with `git stash apply <sha>` (never bare `git stash pop` — the stash stack is shared across worktrees and sessions).

4. **Check out the branch:**

   ```bash
   # For a PR number:
   gh pr checkout <PR_NUMBER>

   # For a branch name:
   git fetch origin <BRANCH> && git checkout <BRANCH>
   ```

5. **Confirm** the checkout succeeded by showing `git log --oneline -3`.

## Phase 2: Detect platform and check prerequisites

1. **Detect the operating system:**

   ```bash
   uname -s
   ```

   - `Linux` → Linux (no special workarounds needed)
   - `Darwin` → macOS (needs Podman machine)
   - `MINGW*`, `MSYS*`, `CYGWIN*`, or any output containing `NT` → Windows (apply Windows workarounds in later phases)

   Store the detected platform for use in conditional steps below.

2. **Verify the toolchain.** Run all checks in parallel:

   ```bash
   podman --version
   uv --version
   node --version
   npm --version
   make --version
   ```

3. **Podman machine** (Windows and macOS only — Linux runs Podman natively):

   ```bash
   podman machine list
   ```

   If the machine exists but is not running, start it:

   ```bash
   podman machine start
   ```

   If no machine exists:

   ```bash
   podman machine init
   podman machine start
   ```

## Phase 3: Install dependencies

1. **Backend dependencies:**

   ```bash
   make -C backend install
   ```

2. **[Windows only] Fix podman-compose:**

   podman-compose <= 1.6.0 has a bug where `is_context_git_url()` misidentifies Windows drive-letter paths (e.g. `C:\...`) as git URLs, causing builds to fail with "no Containerfile or Dockerfile specified." Fixed upstream in [containers/podman-compose#1469](https://github.com/containers/podman-compose/pull/1469) but not yet released.

   Check the installed version:

   ```bash
   cd backend && uv run podman-compose --version
   ```

   If the version is <= 1.6.0 **and** the platform is Windows:

   ```bash
   cd backend
   uv pip install "podman-compose @ git+https://github.com/containers/podman-compose.git@main"
   ```

   Skip this step on Linux/macOS or if podman-compose is > 1.6.0.

   Also install `python-magic-bin` on Windows (provides the `libmagic` DLL that `python-magic` needs):

   ```bash
   cd backend
   uv pip install python-magic-bin
   ```

3. **Frontend dependencies:**

   **[Windows only]** Check if `frontend/package.json` has `"win32"` in its `os` array. npm reports the Windows OS as `"win32"` but the field may only list `"windows"`. If `"win32"` is missing, add it alongside the existing entries.

   Then install on all platforms:

   ```bash
   cd frontend && npm ci
   ```

## Phase 4: Generate secrets and certificates

Check if secrets and certs already exist before regenerating:

```bash
ls backend/.secrets/jwt-primary.pem 2>/dev/null && echo "Secrets exist" || echo "Need secrets"
ls backend/.secrets/certs/ca.pem 2>/dev/null && echo "Certs exist" || echo "Need certs"
```

Only generate what is missing:

```bash
# If secrets are missing:
make secrets

# If certs are missing:
make certs
```

## Phase 5: Build and start services

1. **Shut down any existing environment** to avoid port conflicts:

   ```bash
   make services-down 2>/dev/null || true
   ```

2. **Build container images:**

   ```bash
   make build-images
   ```

   If this fails on Windows with "no Containerfile or Dockerfile specified", the podman-compose fix from Phase 3 was not applied. Go back and apply it.

3. **Start all infrastructure services:**

   ```bash
   make services-up
   ```

4. **Wait for services to be healthy**, then verify:

   ```bash
   cd backend && uv run podman-compose -p syntara -f ../podman-compose.yml ps
   ```

   All services should show `(healthy)`. If Temporal is still `(starting)`, wait up to 2 minutes and re-check.

## Phase 6: Database setup

1. **Run migrations:**

   On Linux/macOS:

   ```bash
   make db-migrate
   ```

   On Windows (workaround for `uv run alembic` path canonicalization bug):

   ```bash
   cd backend && uv run python -m alembic upgrade head
   ```

2. **Seed the database:**

   ```bash
   make db-seed
   ```

   Temporal connectivity warnings during seeding are expected and harmless when running from the host.

3. **Sync admin password:**

   ```bash
   make admin-password
   ```

## Phase 7: Final verification and access URLs

1. **Check all services are healthy:**

   ```bash
   cd backend && uv run podman-compose -p syntara -f ../podman-compose.yml ps
   ```

2. **Return the environment access URLs to the user.** This is the primary output of the skill. Format as a clear table:

   ```
   Syntara infrastructure is ready for PR #<NUMBER> (<BRANCH>)

   | Service              | URL                           | Status                       |
   |----------------------|-------------------------------|------------------------------|
   | Backend API          | http://localhost:8000         | After dev servers start      |
   | API Docs (Swagger)   | http://localhost:8000/docs    | After dev servers start      |
   | Frontend UI          | http://localhost:5173         | After `make dev`             |
   | Temporal UI          | http://localhost:8081         | Running                      |
   | MCP Server           | http://localhost:8765         | Running                      |
   | PostgreSQL           | localhost:5432                | User: admin / Pass: admin    |
   | Redis                | localhost:6379                | Pass: cache                  |

   Admin credentials: see backend/.secrets/admin-password
   ```

   **Tell the user they need to start the dev servers manually.** These run in the foreground and require interactive terminals — they cannot be started from within the skill.

   On **Linux/macOS**, a single command works:

   ```bash
   make dev
   ```

   On **Windows**, `make dev` does not work because GNU Make uses `cmd.exe` as its shell (breaking `uname`, single-quoted args, and inline env vars). Additionally, the Temporal worker uses `asyncio.add_signal_handler()` which is not supported on Windows.

   Instead, use the **containerized Temporal workers** (already running from `make services-up`) and only start the API and frontend locally. The backend must run **without mTLS** (`APP_S2S_TLS_ENABLED=false`) and the frontend must point to **`http://`** (not `https://`) — otherwise the Vite proxy fails with `wrong version number` because it cannot negotiate TLS 1.3 + mTLS with the backend.

   Open **two Git Bash terminals**:

   ```bash
   # Terminal 1 — Backend API (TLS disabled for local dev)
   cd backend && APP_S2S_TLS_ENABLED=false uv run python -m syntara.api.main

   # Terminal 2 — Frontend UI (http, not https)
   cd frontend/packages/syntara-ui && VITE_API_URL=http://localhost:8000 npx vite
   ```

   The Temporal workers (`syntara_temporal-worker_1` and `syntara_temporal-background-worker_1`) are already running inside containers from Phase 5 — no need to start them locally.

   Also include:
   - To shut down dev servers: `Ctrl+C` in each terminal
   - To tear down infrastructure: `/podman-compose-teardown` (or `--purge` to also delete volumes)
   - To get back to the previous branch: `git checkout -`, then restore stashed work with `git stash apply <sha>` using the entry SHA captured in Phase 1 (never bare `git stash pop`; the stash stack is shared across worktrees and sessions)

## Error recovery

- **"Cannot connect to Podman"**: Run `podman machine start` (Windows/macOS) and retry.
- **Build fails with Containerfile error (Windows)**: Re-apply the podman-compose fix from Phase 3.
- **`npm ci` platform error (Windows)**: Ensure `"win32"` is in `frontend/package.json` `os` array.
- **Migration fails**: Ensure the database container is healthy before retrying.
- **Port already in use**: Run `make services-down` to stop any leftover containers, then retry.
