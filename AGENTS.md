# AI Agent Instructions

Syntara is a distributed multi-agent automation system. This monorepo contains a Python/FastAPI backend (`backend/`) and a React/TypeScript frontend (`frontend/`).

Upstream policy for AI agent configuration (no executable hooks; what may live
under `.claude/`; review expectations) is in
[`.github/AI_AGENT_POLICY.md`](.github/AI_AGENT_POLICY.md).

## Component-Specific Standards

- [backend/AGENTS.md](backend/AGENTS.md) — SQLModel, Alembic migrations, uv, pytest, mypy, domain standards
- [frontend/AGENTS.md](frontend/AGENTS.md) — React 19, TypeScript, PatternFly 6, Vitest, Playwright, PR checklist

## Key Commands

```bash
make setup          # First-time bootstrap (install, secrets, services, migrations, seed)
make dev            # Start backend API (port 8000) + frontend dev server (port 5173)
make test           # Run all tests
make lint           # Lint both codebases
make format         # Format both codebases
make typecheck      # Type-check both codebases
make gen-contracts  # Regenerate frontend TypeScript types from backend OpenAPI specs
make services-up    # Start infrastructure (DB, Redis, Temporal, Temporal UI/worker, MCP)
```

## Rules

- Run `make install` before any checks or tests
- Backend API schema changes require `make gen-contracts` — include regenerated types in the same PR
- The root `podman-compose.yml` is the unified compose file; use `uv run podman-compose` to invoke it
- Backend-specific targets: `make -C backend help`

## Commit Messages and PR Titles

Commit subjects **and pull request titles** must follow [Conventional Commits](https://www.conventionalcommits.org/). The `conventional-pre-commit` hook enforces this for commit messages. PR titles become the squash-merge commit subject, so they must use the same format.

```
<type>(<scope>): <description>
```

- `type` is one of: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- `scope` is optional. If you include it, wrap it in **parentheses**, e.g. `fix(auth): handle expired tokens`. If you leave it out, leave out the parentheses too, e.g. `fix: handle expired tokens`. Never write empty `()`.
- **Never use square brackets** in the subject: `fix[auth]: …` and `[AAP-12345] fix: …` are invalid. Reference the Jira key in the PR description instead (see below).
- Add `!` before the colon for breaking changes, e.g. `feat(api)!: drop v1 endpoints`.
- Write the description in the imperative mood, lowercase, with no trailing period. Keep the whole subject to 72 characters or fewer.

Automated or agent-generated PRs (including bug-resolution pipelines) must check or normalize the title against this format before opening the PR.

**Enforced in CI** by the `PR title` check in the `PR Metadata` workflow (`.github/workflows/pr-metadata.yml`). Structural problems fail the check, and a suggested fix is posted when one is safe. Length, casing and trailing-period issues are warnings only.

## No Jira References in Code or Docs

Code and docs in this repo are read by people who can't open the internal Jira, so Jira references must not appear in source files or documentation.

- **Do not put** Jira issue keys (e.g. `AAP-12345`, `ANSTRAT-1934`), Jira URLs or phrases like "per the Jira ticket" in:
  - code comments, docstrings and `TODO`/`FIXME` notes
  - test names, test descriptions and `pytest.skip`/`test.skip` reasons
  - log, error and user-facing messages
  - Markdown docs, ADRs and skill files
- **Instead**, explain the *why* in plain language, e.g. `# Retry once: the upstream API returns 409 while the lock is released`, not `# Workaround for AAP-12345`.
- **The PR description must reference the Jira work item** the PR addresses **by its plain key**, e.g. `Related to AAP-12345` (see the General Checklist in the PR template). Never paste a Jira URL; the `PR description` check in the `PR Metadata` workflow fails when it finds one. PRs without one count as community contributions and get the `community` label. Jira keys are also fine in branch names and commit message bodies/footers (e.g. `Refs: AAP-12345`), but not in the commit subject or PR title (see above).

This applies to code written by hand, by agents, and by automated pipelines (including the agentic bug-resolution pipeline). Pipelines can keep tracking issues in Jira, but generated code and docs must contain no Jira references.

**Enforced in CI** by the `Jira References` workflow (`.github/workflows/jira-references.yml`). It scans only the PR diff, never the PR description, and fails when lines *added* by the PR contain `AAP-`/`ANSTRAT-` keys or Jira URLs (the hosts are listed in `JIRA_HOSTS` in `.github/scripts/src/lib/jira.ts`). Don't write Jira URLs anywhere in the repo, not even as examples. Existing references only need cleaning up when you touch those lines. Use a placeholder such as `PROJ-123` for examples. The few allowed paths are listed in `JIRA_CHECK_EXCLUDED_PATHS` in `.github/scripts/src/lib/jira.ts`.
