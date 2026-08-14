---
name: maintain-my-prs
description: >-
  Rebase, regression-check, and keep the current user's open Syntara PRs
  merge-ready. Use when asked to maintain, rebase, babysit, or refresh your
  open pull requests.
user-invocable: true
---

# Skill: maintain-my-prs

Keep **your** open pull requests merge-ready on
https://github.com/syntara-orchestration/syntara.

**Repository:** `syntara-orchestration/syntara`  
**Working directory:** a local clone of that repository. If this session is in
a different project, `cd` into the Syntara clone before any `git` or `gh`
command. Do not hardcode a home-directory path.

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
# origin must be syntara-orchestration/syntara
gh pr list --repo syntara-orchestration/syntara --author @me --state open --limit 50
```

For each open PR, work through the steps below in order. Use a **git worktree
per PR** so this does not interfere with other sessions in the same clone:

```bash
git fetch origin devel
git worktree add "../$(basename "$REPO_ROOT")-pr-<number>" "<pr-branch>"
```

**Skip if:**

- Draft
- Already closed or merged
- Another session is clearly already working that branch (leave it alone)

This repository is public. Do not put internal hostnames, private runbooks,
credentials, personal filesystem paths, or org-only tracker IDs in commits,
PR bodies, comments, or docs.

---

## Step 0 — Load skills before touching any code

Load the following skills from the latest `devel` branch
(`.claude/skills/*/SKILL.md`) before making any changes. Later steps must
follow those skills:

- `frontend-specialist` — React, TypeScript, PatternFly standards
- `frontend-coding-standards` — patterns and conventions
- `frontend-patternfly-ux` — UX and component selection
- `frontend-testing-guidelines` — Vitest, Testing Library, coverage
- `frontend-playwright-e2e` — E2E test patterns
- `backend-fix-api-spec-drift` — if the PR touches API contracts

---

## Step 1 — Rebase

Rebase the PR branch onto the latest `origin/devel`. Resolve conflicts while
preserving the PR's intent. Do not push yet.

---

## Step 2 — Regression check

Verify the PR does not introduce regressions:

- Run frontend typecheck, lint, and unit tests scoped to changed files
- If E2E tests exist for the affected area, run them
- If visual regression entries exist, verify they still pass or note that
  baselines may need updating

---

## Step 3 — Expand changes to align with new devel code

Compare the PR diff against the latest `devel` and identify:

- New patterns, components, or utilities in `devel` the PR should adopt
- Duplicate logic now in `devel` that the PR can reuse
- API contract changes in `frontend/packages/syntara-contracts/` that require
  the PR to be updated

Apply any necessary expansions or updates and commit them.

---

## Step 4 — Acceptance criteria

If the PR description lists acceptance criteria or linked public issues:

- Read each item
- Review the PR diff against it
- If something is missing, implement it or document in the PR why it is out of
  scope

Do not fetch or cite org-only trackers from this skill.

---

## Step 5 — Visual regression coverage

- If the PR adds or changes UI screens, verify a visual regression entry exists
  — add one if missing
- If existing baselines are stale after the rebase, note that they need to be
  regenerated

---

## Step 6 — Push and monitor CI

After all changes are committed and verified locally:

1. Push the branch (`--force-with-lease` only if a rebase rewrote history)
2. Poll CI every 2–3 minutes with
   `gh run list --repo syntara-orchestration/syntara --branch <branch> --limit 1`
   until the run completes
3. If CI is green — done, move to the next PR
4. If CI fails:
   - Fetch failing logs:
     `gh run view --repo syntara-orchestration/syntara --log-failed`
   - Diagnose and fix the root cause (do not skip hooks or bypass checks)
   - Commit the fix, push again, and resume monitoring from step 6

---

## Constraints

- Always load skills from `devel`, never from the PR branch
- Commit changes in focused, incremental commits scoped to each step
- Never force-push without `--force-with-lease`
- Never use `--no-verify` or bypass hooks
- Never mention other clones, internal systems, or personal machine paths in
  PR text

---

## Backend — when and how to run it

**Needed when the PR:**

- Touches real API integration (not mock API)
- Requires E2E tests against a live API
- Changes or validates contract types in `frontend/packages/syntara-contracts/`

**Not needed when the PR:**

- Only changes UI, styles, or PatternFly components testable via the mock API
- Only changes unit tests, Storybook, or documentation

**Before starting the backend:**

1. Check if it is already running: `lsof -i :8000 | grep LISTEN`
2. If it is running, use it as-is — do not restart it; another session may own it
3. If it is not running, start it from the repo root: `make dev`
4. Wait for the API to be healthy: `curl -sk https://localhost:8000/api/v1/health`
5. When done, do not stop the backend — leave it running for other sessions
