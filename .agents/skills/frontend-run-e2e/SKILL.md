---
name: frontend-run-e2e
description: "Run Playwright E2E tests in this monorepo — interactive wizard with sensible defaults for real backend and mock API modes. Use this skill whenever you need to run, execute, or launch E2E tests, Playwright tests, or end-to-end tests for the frontend. Also use when debugging why E2E tests won't start, when figuring out what environment variables are needed, or when the user asks you to verify a change with E2E tests."
user-invocable: true
---

# Running E2E Tests

This skill walks you through running Playwright E2E tests. For how to **write** them, see `.agents/skills/frontend-playwright-e2e/SKILL.md`.

When this skill is invoked, follow the wizard below. Ask for any missing configuration together, using the interaction mechanism available in the current agent and pre-filling sensible defaults. Treat choices the user already gave as answers.

---

## CRITICAL: Password Security

This block stays in the public tree on purpose: it teaches agents how to **use** a secret without **displaying** it. Never put the password value in this file.

The admin password (`SYNTARA_E2E_PASSWORD`) is a secret. It must never appear in logs, tool output, or conversation text.

**Rules:**

1. **Never read the password file contents.** Use `test -f "$PATH"` to check existence — never `cat`, `head`, `read`, or any command that would output the password value.
2. **Never print, echo, or log the password.** Do not include the password value in any text output to the user.
3. **Use `$(cat ...)` for runtime expansion only.** The shell command should contain the literal string `$(cat $REPO_ROOT/backend/.secrets/admin-password)` (or the user's custom path) so the value is only expanded at execution time by the shell, never captured in tool output.
4. **Mask the password when previewing commands.** When showing the user what will run, display the `$(cat ...)` form — never the expanded value.
5. **Never pass the password as a bare string in an env var.** Always read from file at runtime: `SYNTARA_E2E_PASSWORD=$(cat $PATH)`, never `SYNTARA_E2E_PASSWORD=theactualpassword`.

If you accidentally read the password file, do not repeat its contents. Acknowledge the mistake and move on.

---

## Wizard

### Step 1: Resolve defaults

Before asking the user anything, find the repo root and check which supported URLs are reachable:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
```

| Setting | Default | How to verify |
|---|---|---|
| UI project path | `$REPO_ROOT/frontend/packages/syntara-ui` | `ls "$REPO_ROOT/frontend/packages/syntara-ui/playwright.config.ts"` |
| Admin password path | `$REPO_ROOT/backend/.secrets/admin-password` | `test -f "$REPO_ROOT/backend/.secrets/admin-password"` |
| Local TLS CA cert | `$REPO_ROOT/backend/.secrets/certs/ca.pem` | `test -f "$REPO_ROOT/backend/.secrets/certs/ca.pem"` |
| Local-dev API URL | `https://localhost:8000` | `curl -sf --cacert "$REPO_ROOT/backend/.secrets/certs/ca.pem" https://localhost:8000/healthz/ready -o /dev/null` |
| Compose API URL | `http://localhost:8000` | `curl -sf http://localhost:8000/healthz/ready -o /dev/null` |
| Local Vite URL | `http://localhost:5173` | `curl -sf http://localhost:5173 -o /dev/null` |
| Compose UI URL | `http://localhost:8080` | `curl -sf http://localhost:8080 -o /dev/null` |

Local development (`make dev`) serves the API over HTTPS on port 8000 and the Vite UI on port 5173. Compose (`make -C backend run-all`) serves the API over HTTP on port 8000 and the UI on port 8080. Use reachable endpoints as defaults; if the intended setup is unclear, ask which one the user wants.

### Step 2: Ask the user

Ask only for choices the user has not already specified, combining the remaining questions in one interaction:

1. **Mode** — "Run against real backend or mock API?"
   - **Real backend (Recommended)** — Tests against live Syntara API, database, and auth. Requires backend + frontend to be running.
   - **Mock API** — Self-contained, Playwright auto-starts mock API + UI. No services needed.

2. **What to run** — "Which tests?"
   - **All tests** — Run the full E2E suite
   - **Specific file** — Run a single spec file (ask which one)
   - **By pattern** — Filter by test name with `--grep` (ask for pattern)

3. **Run mode** — "How to run?"
   - **Headless (Recommended)** — Fastest, no browser window
   - **Playwright UI** — Interactive test picker and debugger (`--ui`)
   - **Headed** — Visible browser window (`--headed`)
   - **Debug** — Step-through with Playwright Inspector (`--debug`)

If the user chose **mock API** mode, skip to Step 4 — no further configuration needed.

If the user chose **real backend** mode, continue to Step 3.

### Step 3: Real backend configuration

Ask the user to confirm or override the detected defaults:

1. **Admin password path** — "Path to admin password file?"
   - Default: `$REPO_ROOT/backend/.secrets/admin-password`
   - If the file doesn't exist, warn: "File not found — run `make secrets` to generate it."

2. **CA cert path** — ask only when the selected API URL uses HTTPS.
   - Default: `$REPO_ROOT/backend/.secrets/certs/ca.pem`
   - If it doesn't exist, warn: "File not found — run `make certs` to generate it."
   - Compose uses HTTP and does not need a CA cert.

3. **Backend URL** — "Backend API URL?"
   - Local development default: `https://localhost:8000`
   - Compose default: `http://localhost:8000`
   - If neither health check succeeded, explain that local development uses `make dev` and Compose uses `make -C backend run-all`; ask which setup they use before choosing a URL.

4. **Frontend URL** — "Frontend URL?"
   - Local Vite default: `http://localhost:5173`
   - Compose default: `http://localhost:8080`
   - If no UI responds but the API is ready, the skill can start a local Vite UI on port 5173 pointed at the selected API URL.

Most of the time the user will accept the detected defaults.
Carry the confirmed values as `PASSWORD_PATH`, `CA_PATH` (for HTTPS only), `BACKEND_URL`, and `FRONTEND_URL` through the preflight and test command.

### Step 4: Preflight checks

Before running, ensure dependencies are installed. Run `make install` from the repository root after a fresh clone or when required dependencies are missing or have changed. It runs `npm ci` for the frontend, so it does not need to run before every wizard launch.

For real-backend mode, verify the selected endpoints and automatically start a local E2E Vite server if no UI is already running.

**For real backend mode:**

```bash
# 1. Password file exists (NEVER cat/read the file — only check existence)
test -f "$PASSWORD_PATH" && echo "OK: password file found" || echo "FAIL: password file not found — run: make secrets"

# 2. Backend is responding at the selected URL. Use the local CA only for HTTPS:
if [[ "$BACKEND_URL" == https://* ]]; then
  curl -sf --cacert "$CA_PATH" "${BACKEND_URL%/}/healthz/ready" -o /dev/null && echo "OK: backend responding" || echo "FAIL: backend not responding"
else
  curl -sf "${BACKEND_URL%/}/healthz/ready" -o /dev/null && echo "OK: backend responding" || echo "FAIL: backend not responding"
fi

# 3. Frontend is responding at the selected URL
curl -sf "$FRONTEND_URL" -o /dev/null && echo "OK: frontend responding"
```

If no frontend URL is responding but the backend is ready, set `FRONTEND_URL=http://localhost:5173` and start the E2E-only Vite server (not `start:ui`, which also starts Storybook):

```bash
cd "$REPO_ROOT/frontend"
VITE_API_URL="$BACKEND_URL" npm run start:e2e --prefix packages/syntara-ui -- --port 5173
```

Run it in a persistent terminal, then wait for it to come up (poll every 2 seconds, up to 60 seconds):

```bash
echo "Starting frontend dev server..."
for i in $(seq 1 30); do
  curl -sf "$FRONTEND_URL" -o /dev/null && break
  sleep 2
done
curl -sf "$FRONTEND_URL" -o /dev/null && echo "OK: frontend is ready" || echo "FAIL: frontend failed to start after 60s"
```

Tell the user what you're doing ("Frontend not running — starting it now..."). If the password file is missing or the backend isn't responding, tell the user what's wrong and how to fix it. Don't proceed until the environment is ready (or the user explicitly says to go ahead).

**For mock API mode:**

No preflight checks needed — Playwright auto-starts both the mock API and UI. Just proceed to Step 5.

### Step 5: Build and run the command

Construct the command from the wizard answers. Use the selected backend and frontend URLs and the password file path from Step 3.

**Real backend mode:**

```bash
(cd "$REPO_ROOT/frontend/packages/syntara-ui" && \
VITE_API_URL="$BACKEND_URL" \
SYNTARA_E2E_SKIP_WEB_SERVER=1 \
SYNTARA_E2E_BASE_URL="$FRONTEND_URL" \
SYNTARA_E2E_PASSWORD="$(cat "$PASSWORD_PATH")" \
npx playwright test)
```

Append the selected spec and run-mode options directly to `npx playwright test`. For example: `npx playwright test e2e/workflows.spec.ts --headed` or `npx playwright test --grep 'user creates a workflow' --debug`. Do not store quoted options in a scalar such as `$TEST_ARGS`: quotes inside a variable are not reparsed by the shell, so patterns with spaces split into multiple arguments.

**Mock API mode:**

```bash
(cd "$REPO_ROOT/frontend/packages/syntara-ui" && npx playwright test)
```

No E2E env vars are needed — Playwright auto-starts the mock API and UI. In mock mode the default suite also includes the screenshot tests under `e2e/visual-regression/`. Append a spec, `--grep 'pattern'`, or the selected run-mode flag directly to the command.

Show the user the full command before executing it. For real-backend mode, keep `$(cat "$PASSWORD_PATH")` literal in the preview — never show its expanded value. This is both the preview and the actual command; the shell expands it at runtime.

### Step 6: Report results

After the test run completes, present a clear summary to the user. Do not just let the raw Playwright output scroll by — parse it and report.

**If all tests passed:**

> **All tests passed** (X passed in Ys)

**If any tests failed:**

1. **Summary line** — e.g., "2 passed, 1 failed (15.3s)"
2. **Failed tests** — list each by name with a one-line description of the error
3. **Link to the full HTML report:**
   ```
   open $REPO_ROOT/frontend/packages/syntara-ui/playwright-report/index.html
   ```

Keep the report concise — the user should be able to see the result at a glance without scrolling through raw output.

---

## Reference

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `http://localhost:3300` | Mock API URL for direct API calls in test fixtures; set to the selected API URL in real-backend mode |
| `SYNTARA_E2E_SKIP_WEB_SERVER` | _(unset)_ | Set to `1` for real-backend mode; disables Playwright server startup and excludes `e2e/visual-regression/` |
| `SYNTARA_E2E_BASE_URL` | `http://localhost:4173` | UI URL for browser navigation; set to the selected UI URL in real-backend mode |
| `SYNTARA_E2E_PORT` | `4173` | UI server port (mock mode only) |
| `SYNTARA_E2E_API_PORT` | `3300` | Mock API port (mock mode only) |
| `SYNTARA_E2E_PASSWORD` | _(unset)_ | Admin password for real backend login |

### Admin password

Generated by `make secrets` during initial setup. Located at `backend/.secrets/admin-password` relative to the repo root. If the file is missing:

```bash
make secrets
```

**Common issue: "Incorrect login credentials" during E2E tests.** The password file and the database can get out of sync — the file has one password but the database has another (e.g., after regenerating secrets without re-syncing). To fix, run from the repo root:

```bash
make admin-password
```

This syncs the password from `backend/.secrets/admin-password` into the database. This is a frequent cause of E2E login failures against the real backend.

### Starting services (if not already running)

From the repository root, choose the setup that matches the selected URLs:

```bash
# Local development: API https://localhost:8000, Vite UI http://localhost:5173
make dev

# Compose: API http://localhost:8000, UI http://localhost:8080
make -C backend run-all

# If the local backend is already running and only the UI is missing:
cd frontend
VITE_API_URL=https://localhost:8000 npm run start:e2e --prefix packages/syntara-ui -- --port 5173
```

### Running specific tests

```bash
# Single file
npx playwright test e2e/workflows.spec.ts

# By name pattern
npx playwright test --grep 'user creates a workflow'

# @pr-check suite — fast, critical-path subset (intended quick gate; not yet used by CI automatically)
npx playwright test --grep @pr-check

# Exclude tests tagged @local-only
npx playwright test --grep-invert '@local-only'

# Run the page screenshot suite (from frontend/; default mock E2E also discovers these tests)
cd "$REPO_ROOT/frontend" && npm run e2e:visual-regression

# Full-app accessibility audit (report-only; mock API; from frontend/; see frontend-a11y-audit skill)
cd "$REPO_ROOT/frontend" && npm run e2e:a11y-audit

# Show trace from a failed run
npx playwright show-trace test-results/*/trace.zip
```

### Test suite tags summary

| Tag | Select with | Purpose |
|---|---|---|
| `@pr-check` | `--grep @pr-check` | Fast critical-path subset for quick local validation |
| `@local-only` | `--grep-invert '@local-only'` | Mock-dependent audits and screenshot tests; not a blanket CI exclusion. Standard real-backend E2E skips these tests, while dedicated baseline workflows run page screenshots in CI. |

See `.agents/skills/frontend-playwright-e2e/SKILL.md` → **Test Suite Tags** for the full rules on when to apply each tag.

### Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Connection refused | Selected server is not running | Start local services with `make dev`, Compose with `make -C backend run-all`, or check the selected URLs |
| SYNTARA_E2E_PASSWORD required | Missing password env var | Set it: `SYNTARA_E2E_PASSWORD=$(cat <path>)` |
| "Incorrect login credentials" | Password file and database are out of sync | Run `make admin-password` from repo root to sync |
| Login errors (other) | Wrong password file or unseeded DB | Regenerate: `make secrets` then `make admin-password` |
| API 404s in mock mode | UI started without correct VITE_API_URL | Playwright handles this automatically; if manual, use `VITE_API_URL=http://localhost:3300` |
| Port conflicts | Another service uses an E2E port | Stop that service or set `SYNTARA_E2E_PORT` and `SYNTARA_E2E_API_PORT` to free ports |
| Visual regression tests skipped | Expected in real-backend mode | The config excludes `e2e/visual-regression/` when `SYNTARA_E2E_SKIP_WEB_SERVER=1`; run them in mock mode with `npm run e2e:visual-regression` from `frontend/` |

### What works where

| Tests | Mock API | Real Backend |
|---|---|---|
| CRUD workflows, credentials, integrations | Yes | Yes |
| Builder interactions | Yes | Yes |
| Filtering, search, pagination | Yes (seed data) | Yes (if data exists) |
| Permission gating (viewer/auditor/user) | Yes (mock tokens) | Yes (real roles created) |
| Visual regression | Yes | No (skipped) |
| Accessibility audit (`e2e:a11y-audit`) | Yes (report-only) | No (skipped) |
| Journey tests (auth flows) | No (skipped) | Yes |
| Role provisioning tests | No (skipped) | Yes |
