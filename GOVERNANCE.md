# Contribution Governance

This document defines how maintainers evaluate, accept, and maintain external
contributions to this repository. Contributor how-to steps (setup, PR checklist,
DCO) live in [CONTRIBUTING.md](CONTRIBUTING.md).

Community conduct and vulnerability reporting live in
[`.github/CODE_OF_CONDUCT.md`](.github/CODE_OF_CONDUCT.md) and
[`.github/SECURITY.md`](.github/SECURITY.md) when those files are present in the
branch you are working from.

## Intent

We are **not** accepting new workflow node types or new agent implementations
until a platform extension framework is available. Improvements to **existing**
node types, agents, and MCP / tool-server integrations are welcome.

## Scope of welcome contributions

Today we welcome external contributions that improve the **existing** product
surface without requiring a plugin or extension framework, for example:

- Bug fixes and reliability improvements
- Documentation, examples, and developer-experience polish
- Tests and CI hardening that do not change product architecture
- Small, well-scoped enhancements to existing node types, UI, or APIs that
  follow established patterns
- Improvements to **MCP / tool-server** integrations and related tooling
  (bugs, docs, tests, and small enhancements). This is the current
  extensibility surface for connecting external tools — it is **not** a path
  for contributing new workflow node types or new agent implementations.

We do **not** currently accept contributions that add **new custom node types**
or **new custom agents**. See
[Custom node types and custom agents](#custom-node-types-and-custom-agents).

## Review criteria

Every external pull request is reviewed against the same bar as internal work,
plus community-specific clarity:

| Area | Expectation |
| --- | --- |
| **Code quality** | Matches existing patterns in the touched area. Passes `make format`, `make lint`, and `make typecheck` (or the frontend equivalents). No drive-by refactors unrelated to the change. |
| **Tests** | Behavior changes include automated tests at the appropriate layer (unit / integration / E2E). Bug fixes preferably include a regression test. |
| **Docs** | User- or contributor-facing behavior changes update the relevant docs in the same PR. |
| **Security & secrets** | No credentials, internal hostnames, or private Red Hat-only content. Follow `.github/SECURITY.md` (when present) for vulnerability reports. |
| **Contracts** | API schema changes regenerate contracts (`make gen-contracts`) in the same PR. Breaking OpenAPI changes need an explicit acknowledgment in the PR description. |
| **Scope fit** | Change fits [Scope of welcome contributions](#scope-of-welcome-contributions). Out-of-scope proposals are closed with a pointer to this document. |

Reviewers use the PR template checklists and the area coding standards under
`backend/docs/standards/` and `frontend/CLAUDE.md` / `.claude/skills/`.

## Acceptance process

1. **Open a PR** against `devel` following [CONTRIBUTING.md](CONTRIBUTING.md).
2. **Automated checks** must pass (or known flakes must be acknowledged by a
   maintainer).
3. **CODEOWNERS review**: GitHub requests reviews from the owners of touched
   paths (see [`.github/CODEOWNERS`](.github/CODEOWNERS)).
   - Backend paths → `@syntara-orchestration/syntara-backend`
   - Frontend paths → `@syntara-orchestration/ui-team`
   - Governance / architecture paths → `@syntara-orchestration/syntara-leads`
   - CI / release paths → the corresponding specialist teams
4. **Approvals required**: at least one approving review from a required
   CODEOWNER for each owned area touched. Cross-cutting PRs need both backend
   and frontend approval when both trees change.
5. **Maintainer merge**: only maintainers merge. Merge means the change is
   accepted into `devel` and becomes part of the project's maintained surface.

### What “accepted” means

Acceptance is not a one-time courtesy merge. Once merged:

- The contribution is owned by the **project maintainers** for day-to-day
  break/fix response in CI and releases.
- The original contributor is welcome (but not required) to help with follow-up
  fixes; maintainers may ping them when useful.
- Maintainers may revert, rewrite, or supersede the change if it later conflicts
  with architecture, security, or product direction.

There is no separate “community-maintained forever” tier inside this monorepo
until a plugin / marketplace model exists.

## Maintenance model

| Situation | Owner | Action |
| --- | --- | --- |
| Regression in merged external code on `devel` or a release branch | Area maintainers (CODEOWNERS) | Fix or revert; prefer fixing forward when safe. |
| Contributor unreachable after merge | Area maintainers | Proceed without waiting; optional courtesy ping. |
| Change proves architecturally incompatible | `@syntara-orchestration/syntara-leads` + area owners | Revert or redesign; document decision if it sets policy. |
| Security issue in contributed code | Follow `.github/SECURITY.md` when present; area maintainers + leads | Treat as any other vulnerability. |

Red Hat staff and community contributors are held to the same technical bar.
Staff PRs are not exempt from CODEOWNERS or CI.

## Custom node types and custom agents

**Status: not open for external contribution.**

New node types today require coordinated changes across a closed `NodeType`
enum, static dispatch maps, schemas, and frontend registration — typically many
files across backend and UI. There is no dynamic registration API. Custom agents
are similarly wired into a closed orchestration topology; the planned
external-agent / plugin path is not ready for outside contributors.

Until the platform extension / plugin framework lands:

1. Pull requests that add a new `NodeType`, a new agent class intended as a
   community extension, or parallel “plugin” packaging **will be declined**.
   Talk to the maintainers if you believe you have a special case; there is no
   open design-review path for new node or agent types at this time.
2. Improvements to **existing** node types (including the agentic node) and
   existing agents remain in scope under the general review criteria above.
3. Contributions that improve **MCP / tool-server** integrations (bugs, docs,
   tests, small enhancements) are welcome and are distinct from adding new node
   or agent types.

When the framework becomes available, this section will be replaced with
concrete submission, review, ownership, and break/fix rules for extension
packages.

## Document ownership

Changes to this file require review from `@syntara-orchestration/syntara-leads`.
For questions about this policy, open a
[GitHub Discussion](https://github.com/orgs/syntara-orchestration/discussions)
before sending a large PR. Report bugs via GitHub Issues. Report security
vulnerabilities to `secalert@redhat.com` (see
[`.github/SECURITY.md`](.github/SECURITY.md) when present).
