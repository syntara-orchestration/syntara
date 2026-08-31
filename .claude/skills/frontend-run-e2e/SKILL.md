---
name: frontend-run-e2e
description: "Run Playwright E2E tests in this monorepo — interactive wizard with sensible defaults for real backend and mock API modes. Use this skill whenever you need to run, execute, or launch E2E tests, Playwright tests, or end-to-end tests for the frontend. Also use when debugging why E2E tests won't start, when figuring out what environment variables are needed, or when the user asks you to verify a change with E2E tests."
user-invocable: true
---

# Running E2E Tests

This skill walks you through running Playwright E2E tests. For how to **write** them, see `.claude/skills/frontend-playwright-e2e/SKILL.md`.

When this skill is invoked, follow the wizard below. Use `AskUserQuestion` to gather configuration, pre-filling sensible defaults. The user should only need to confirm or override — not fill in from scratch.

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

Before asking the user anything, find the repo root and verify defaults silently:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
```

| Setting | Default | How to verify |
|---|---|---|
| UI project path | `$REPO_ROOT/frontend/packages/syntara-ui` | `ls $REPO_ROOT/frontend/packages/syntara-ui/playwright.config.ts` |
| Admin password path | `$REPO_ROOT/backend/.secrets/admin-password` | `test -f $REPO_ROOT/backend/.secrets/admin-password` |
| CA cert path | `$REPO_ROOT/backend/.secrets/certs/ca.pem` | `test -f $REPO_ROOT/backend/.secrets/certs/ca.pem` |
| Backend URL | `https://localhost:8000` | `curl -sf --cacert $REPO_ROOT/backend/.secrets/certs/ca.pem https://localhost:8000/healthz/ready` |
| Frontend URL | `http://localhost:5173` | `curl -sf http://localhost:5173 -o /dev/null` |

Use the results to inform the wizard — if a check fails, mention it in the question so the user knows something needs attention.

### Step 2: Ask the user

Present a single `AskUserQuestion` with these questions:

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

Present another `AskUserQuestion` showing the detected defaults and asking the user to confirm or override:

1. **Admin password path** — "Path to admin password file?"
   - Default: `$REPO_ROOT/backend/.secrets/admin-password`
   - If the file doesn't exist, warn: "File not found — run `make -C backend secrets` to generate it."

2. **Backend URL** — "Backend API URL?"
   - Default: `https://localhost:8000`
   - If the health check failed in Step 1, warn: "Backend not responding — start it with `make run-all`."

3. **Frontend URL** — "Frontend dev server URL?"
   - Default: `http://localhost:5173`
   - If the check failed in Step 1, warn: "Frontend not responding — start it with `VITE_API_URL=https://localhost:8000 npm run start:ui` from `frontend/`."

Most of the time the user will accept all defaults by selecting the default option.

### Step 4: Preflight checks

Before running, verify the environment is ready. For real backend mode, the skill should **automatically start the frontend dev server** if it's not already running.

**For real backend mode:**

```bash
# 1. Password file exists (NEVER cat/read the file — only check existence)
test -f $REPO_ROOT/backend/.secrets/admin-password && echo "OK: password file found" || echo "FAIL: password file not found — run: make -C backend secrets"

# 2. Backend is responding
curl -sf --cacert $REPO_ROOT/backend/.secrets/certs/ca.pem https://localhost:8000/healthz/ready -o /dev/null && echo "OK: backend responding" || echo "FAIL: backend not responding — run: make run-all"

# 3. Frontend is responding — start it if not
curl -sf http://localhost:5173 -o /dev/null && echo "OK: frontend responding"
```

If the frontend is **not** responding, start it automatically:

```bash
cd $REPO_ROOT/frontend && VITE_API_URL=https://localhost:8000 npm run start:ui &
```

Then wait for it to come up (poll every 2 seconds, up to 60 seconds):

```bash
echo "Starting frontend dev server..."
for i in $(seq 1 30); do
  curl -sf http://localhost:5173 -o /dev/null && break
  sleep 2
done
curl -sf http://localhost:5173 -o /dev/null && echo "OK: frontend is ready" || echo "FAIL: frontend failed to start after 60s"
```

Tell the user what you're doing ("Frontend not running — starting it now..."). If the password file is missing or the backend isn't responding, tell the user what's wrong and how to fix it. Don't proceed until the environment is ready (or the user explicitly says to go ahead).

**For mock API mode:**

No preflight checks needed — Playwright auto-starts both the mock API and UI. Just proceed to Step 5.

### Step 5: Build and run the command

Construct the command based on the wizard answers.

**Real backend mode:**

```bash
(cd $REPO_ROOT/frontend/packages/syntara-ui && \
VITE_API_URL=https://localhost:8000 \
SYNTARA_E2E_SKIP_WEB_SERVER=1 \
SYNTARA_E2E_BASE_URL=http://localhost:5173 \
SYNTARA_E2E_PASSWORD=$(cat $REPO_ROOT/backend/.secrets/admin-password) \
npx playwright test $TEST_ARGS)
```

If the user provided a custom admin password path, backend URL, or frontend URL, substitute those values. `$TEST_ARGS` is:
- All tests: _(empty)_
- Specific file: `e2e/workflows.spec.ts` (or whatever the user specified)
- By pattern: `--grep "pattern"`
- Add `--ui`, `--headed`, or `--debug` based on run mode

**Mock API mode:**

```bash
(cd $REPO_ROOT/frontend/packages/syntara-ui && npx playwright test $TEST_ARGS)
```

No env vars needed — Playwright auto-starts everything.

Show the user the full command before executing it. The command must use `$(cat $REPO_ROOT/backend/.secrets/admin-password)` for the password — never the expanded value. This is both the preview and the actual command; the shell expands it at runtime.

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
| `VITE_API_URL` | `http://localhost:3300` | Backend URL for direct API calls in test fixtures |
| `SYNTARA_E2E_SKIP_WEB_SERVER` | _(unset)_ | Set to `1` to skip auto-starting servers |
| `SYNTARA_E2E_BASE_URL` | `http://localhost:4173` | UI URL for browser navigation |
| `SYNTARA_E2E_PORT` | `4173` | UI server port (mock mode only) |
| `SYNTARA_E2E_API_PORT` | `3300` | Mock API port (mock mode only) |
| `SYNTARA_E2E_PASSWORD` | _(unset)_ | Admin password for real backend login |

### Admin password

Generated by `make secrets` during initial setup. Located at `backend/.secrets/admin-password` relative to the repo root. If the file is missing:

```bash
make -C backend secrets
```

**Common issue: "Incorrect login credentials" during E2E tests.** The password file and the database can get out of sync — the file has one password but the database has another (e.g., after regenerating secrets without re-syncing). To fix, run from the repo root:

```bash
make admin-password
```

This syncs the password from `backend/.secrets/admin-password` into the database. This is a frequent cause of E2E login failures against the real backend.

### Starting services (if not already running)

From the repo root:

```bash
# Start everything at once
make dev

# Or start individually:
make services-up              # Infrastructure (DB, Redis, Temporal, OPA)
make run-all                  # Backend API on https://localhost:8000
cd frontend && VITE_API_URL=https://localhost:8000 npm run start:ui  # Frontend on http://localhost:5173
```

### Running specific tests

```bash
# Single file
npx playwright test e2e/workflows.spec.ts

# By name pattern
npx playwright test --grep "user creates a workflow"

# @pr-check suite — fast, critical-path subset (intended quick gate; not yet used by CI automatically)
npx playwright test --grep @pr-check

# Simulate Konflux behavior — exclude @konflux-skip tests (mirrors Tekton playwright-grep-invert param)
npx playwright test --grep-invert @konflux-skip

# Exclude visual-regression (they require npm run e2e:visual-regression, not the default runner)
npx playwright test --grep-invert @local-only

# Show trace from a failed run
npx playwright show-trace test-results/*/trace.zip
```

### Test suite tags summary

| Tag | Select with | Purpose |
|---|---|---|
| `@pr-check` | `--grep @pr-check` | Fast critical-path subset for quick local validation |
| `@konflux-skip` | `--grep-invert @konflux-skip` | Tests skipped in Konflux pipelines (flaky in that env only) |
| `@local-only` | `--grep-invert @local-only` | Visual regression tests; excluded from all CI automatically |

See `.claude/skills/frontend-playwright-e2e/SKILL.md` → **Test Suite Tags** for the full rules on when to apply each tag.

### Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Connection refused | Servers not running | Start with `make dev` or check URLs |
| SYNTARA_E2E_PASSWORD required | Missing password env var | Set it: `SYNTARA_E2E_PASSWORD=$(cat <path>)` |
| "Incorrect login credentials" | Password file and database are out of sync | Run `make admin-password` from repo root to sync |
| Login errors (other) | Wrong password file or unseeded DB | Regenerate: `make -C backend secrets` then `make admin-password` |
| API 404s in mock mode | UI started without correct VITE_API_URL | Playwright handles this automatically; if manual, use `VITE_API_URL=http://localhost:3300` |
| Port conflicts | Stale processes | `kill-port 3300 4173` |
| Visual regression tests skipped | Expected in real backend mode | These only run in mock mode with deterministic data |

### What works where

| Tests | Mock API | Real Backend |
|---|---|---|
| CRUD workflows, credentials, integrations | Yes | Yes |
| Builder interactions | Yes | Yes |
| Filtering, search, pagination | Yes (seed data) | Yes (if data exists) |
| Permission gating (viewer/auditor/user) | Yes (mock tokens) | Yes (real roles created) |
| Visual regression | Yes | No (skipped) |
| Journey tests (auth flows) | No (skipped) | Yes |
| Role provisioning tests | No (skipped) | Yes |
