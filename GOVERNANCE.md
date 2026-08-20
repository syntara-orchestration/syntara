# Contribution Governance

This document defines how maintainers evaluate, accept, and maintain external
contributions to this repository. Contributor how-to steps (setup, PR checklist,
DCO) live in [CONTRIBUTING.md](CONTRIBUTING.md).

Community conduct and vulnerability reporting live in
[`.github/CODE_OF_CONDUCT.md`](.github/CODE_OF_CONDUCT.md) and
[`.github/SECURITY.md`](.github/SECURITY.md).

## Scope of welcome contributions

We are **not** accepting new workflow node types or new agent implementations
until a platform extension framework is available. Improvements to **existing**
node types, agents, and MCP / tool-server integrations are welcome.

Today we welcome external contributions that improve the **existing** project
surface without requiring a plugin or extension framework, for example:

- Bug fixes and reliability improvements
- Documentation, examples, and developer-experience polish
- Tests and CI hardening that do not change project architecture
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

| Area                   | Expectation                                                                                                                                                                          |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Code quality**       | Matches existing patterns in the touched area. Passes `make format`, `make lint`, and `make typecheck` (or the frontend equivalents). No drive-by refactors unrelated to the change. |
| **Tests**              | Behavior changes include automated tests at the appropriate layer (unit / integration / E2E). Bug fixes must include a regression test.                                              |
| **Docs**               | User- or contributor-facing behavior changes update the relevant docs in the same PR.                                                                                                |
| **Security & secrets** | No credentials, internal hostnames, or private content. Follow [`.github/SECURITY.md`](.github/SECURITY.md) for vulnerability reports.                                               |
| **Contracts**          | API schema changes regenerate contracts (`make gen-contracts`) in the same PR. Breaking OpenAPI changes must be called out in the PR description with a rationale for the break.     |
| **Scope fit**          | Change fits [Scope of welcome contributions](#scope-of-welcome-contributions). Out-of-scope proposals are closed with a pointer to this document.                                    |

Reviewers use the PR template checklists and the area coding standards under
`backend/docs/standards/` and `frontend/AGENTS.md` / `.claude/skills/`.

## Acceptance process

1. **Open a PR** against `devel` following [CONTRIBUTING.md](CONTRIBUTING.md).
2. **Automated checks** must pass (or known flakes must be acknowledged by a
   maintainer).
3. **CODEOWNERS review**: GitHub requests reviews from the owners of touched
   paths (see [`.github/CODEOWNERS`](.github/CODEOWNERS)).
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
  with architecture, security, or project direction.

There is no separate “community-maintained forever” tier inside this monorepo
until a plugin / marketplace model exists.

## Maintenance model

| Situation                                                         | Owner                                                                         | Action                                                   |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------- |
| Regression in merged external code on `devel` or a release branch | Area maintainers (CODEOWNERS)                                                 | Fix or revert; prefer fixing forward when safe.          |
| Contributor unreachable after merge                               | Area maintainers                                                              | Proceed without waiting; optional courtesy ping.         |
| Change proves architecturally incompatible                        | `@syntara-orchestration/syntara-leads` + area owners                          | Revert or redesign; document decision if it sets policy. |
| Security issue in contributed code                                | Follow [`.github/SECURITY.md`](.github/SECURITY.md); area maintainers + leads | Treat as any other vulnerability.                        |

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
   community extension, or parallel “plugin” packaging **will be closed**.
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

This file is maintained by `@syntara-orchestration/syntara-leads` (see
[`.github/CODEOWNERS`](.github/CODEOWNERS)) and reviewed when contribution
policy changes or quarterly, whichever comes first.

For questions about this policy, open a
[GitHub Discussion](https://github.com/orgs/syntara-orchestration/discussions)
before sending a large PR. Report bugs via GitHub Issues. Report security
vulnerabilities per [`.github/SECURITY.md`](.github/SECURITY.md).
