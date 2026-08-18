# Contributing

This is a monorepo with two components. General guidelines apply to both; component-specific details are in their respective CONTRIBUTING files:

- **Backend**: [backend/CONTRIBUTING.md](backend/CONTRIBUTING.md)
- **Frontend**: [frontend/CONTRIBUTING.md](frontend/CONTRIBUTING.md)

How maintainers evaluate, accept, and maintain external contributions (including
what is in or out of scope for custom node types and custom agents) is documented
in [GOVERNANCE.md](GOVERNANCE.md).

## Prerequisites

- **Python 3.12+** and [uv](https://docs.astral.sh/uv/)
- **Node.js 22+** and npm
- **Podman** or Docker
- **Make**

## Development Setup

```bash
make setup      # First-time: install deps, generate secrets + TLS certs, build images, start services, run migrations, seed DB
make dev        # Start backend API (port 8000) + frontend dev server (port 5173)
```

## Running Tests

```bash
make test       # Run backend + frontend unit tests
make test-all   # Run all tests including integration (requires running services)
```

See [backend/CONTRIBUTING.md](backend/CONTRIBUTING.md) and [frontend/CONTRIBUTING.md](frontend/CONTRIBUTING.md) for component-specific test commands and options.

## AI Contributions

AI-assisted contributions are welcome and held to the same review and quality standards as any other contribution. Contributors take full responsibility for AI-assisted work and MUST disclose significant use of AI tools via a commit trailer, for example: `Assisted-by: Opus 4.6`. Grammar and stylistic corrections do not need disclosure.

See [AI_POLICY.md](.github/AI_POLICY.md) for the full policy.

## Submitting a PR

1. [Fork the repository](https://github.com/syntara-orchestration/syntara/fork)
2. Create a feature branch from `devel`
3. Make your changes and ensure all checks pass:
   ```bash
   make format     # Format both codebases
   make lint       # Lint both codebases
   make test       # Run all tests
   make typecheck  # Type-check both codebases
   ```
4. Open a pull request targeting `devel` — the PR template will guide you through the checklist
5. Link any related issues in the PR description

## CI Checks

Pull requests to `devel` run **GitHub Actions** and **Konflux**. Both are
expected to pass on this repository. Prefer reproducing GitHub Actions
failures locally with `make format`, `make lint`, `make test`, and
`make typecheck` (plus component docs linked above).

Branch protection is gated by **`(Backend) Required Checks`** and
**`(Frontend) Required Checks`**. Those jobs pass when their dependencies
succeed or are skipped (for example, doc-only PRs). Individual job names
below are what you will see on the PR checks list.

### GitHub Actions

Shared across the monorepo:

| Check | What it covers |
| --- | --- |
| `Pre-commit` | Formatting and pre-commit hooks |
| `Check Contract Drift` | Frontend TypeScript contracts stay in sync with backend OpenAPI |

Backend (when `backend/` changes; aggregated by `(Backend) Required Checks`):

| Check | What it covers |
| --- | --- |
| `(Backend) API Spec Validation` | OpenAPI sub-spec syntax |
| `(Backend) API Spec Bundle` | Bundled OpenAPI / CLI `openapi.yaml` sync |
| `(Backend) API Spec Drift` | Spec matches implementation |
| `(Backend) Generate API Client` | Generated Python client is committed |
| `(Backend) Check API Paths` | Snake_case API paths |
| `(Backend) Check Dead Code` | Vulture |
| `(Backend) Check Import Cycles` | Import cycle detection |
| `(Backend) Check Orphan Modules` | Orphan module detection |
| `(Backend) Check OpenAPI Breaking Changes` | Breaking OpenAPI diffs vs `devel` |
| `(Backend) Verify Test Structure` | Test layout matches source |
| `(Backend) mypy` | Type checking |
| `(Backend) Unit Tests` | Unit tests |
| `(Backend) CLI Tests` | CLI tests |
| `(Backend) Integration Tests` | Integration tests (needs services) |
| `(Backend) Test Podman Compose E2E` | Compose-based backend E2E |
| `(Backend) Shared Checks Gate` | Waits on shared jobs such as `Pre-commit` |
| Backend Snyk SAST / SCA jobs | Vulnerability scanning (needs `SNYK_TOKEN`) |

Frontend (when `frontend/` or `backend/` changes — backend so the UI is
checked when the API changes; aggregated by `(Frontend) Required Checks`):

| Check | What it covers |
| --- | --- |
| `(Frontend) Generate Contracts` | Regenerated contracts when needed |
| `(Frontend) Checks` | Lint / typecheck / static analysis |
| `(Frontend) Unit Tests` | Unit tests (sharded) |
| `(Frontend) Coverage Report` | Coverage merge/report |
| `(Frontend) Storybook Build` | Storybook build |
| `(Frontend) Test Container Build` | UI / mock-API image build (no push) |
| `(Frontend) Test Podman Compose E2E` | Compose-based frontend E2E |
| `(Frontend) Shared Checks Gate` | Waits on shared jobs such as `Pre-commit` |

SonarCloud analysis also runs on PRs for visibility; it is informational and does not block the Required Checks gates by itself.

### Konflux Checks

These include Konflux Pipelines-as-Code definitions under `.tekton/`.
Konflux pipeline secrets are handled inside the pipeline. Secret
classification for GitHub Actions is documented in
[docs/ci/secrets-inventory.md](docs/ci/secrets-inventory.md).

| Check | What it covers |
| --- | --- |
| `(Backend) Konflux Gate` / `(Frontend) Konflux Gate` | Waits for Konflux build + Conforma on the PR |
| `Konflux kflux-prd-rh03 / ansible-automation-orchestrator-*-devel-on-pull-request` | Konflux container build for backend or UI |
| `Red Hat Konflux / conforma-on-pull-request-devel / …` | Conforma policy checks on the built image |
| `Konflux kflux-prd-rh03 / automation-orchestrator-api-tests-devel-pull-request` | Konflux API tests (when `backend/` changes) |
| `Konflux kflux-prd-rh03 / automation-orchestrator-ui-tests-devel-pull-request` | Konflux UI tests (when `frontend/` and/or `backend/` changes) |

Konflux pipelines use path filters in `.tekton/`. If those paths did not change,
the pipeline will not start and the matching Konflux Gate job skips after its
startup window.

### Fork PRs

Fork pull requests receive the same Konflux coverage as in-org PRs (container
build, Conforma, and Konflux API/UI tests), subject to the same `.tekton/` path
filters. Konflux pipeline secrets are handled **inside** the pipeline.

**GitHub Actions** jobs that read org/repo secrets can still behave differently
on fork PRs. Known examples (see
[docs/ci/secrets-inventory.md](docs/ci/secrets-inventory.md)):

| Area | Secrets involved | What to expect on forks |
| --- | --- | --- |
| Snyk SAST / SCA | `SNYK_TOKEN` (org) | May skip, fail, or lack token access vs in-org PRs |
| Podman Compose E2E | `RH_REGISTRY_USER` / `RH_REGISTRY_TOKEN` (and related repo secrets such as Currents / OpenRouter where used) | Not fully verified from forks yet — registry login and compose steps are the main suspects if these jobs fail only on fork PRs |
| Maintainer comment commands | N/A | `/build-pr-image` (and similar) only run for org owners/members — see [backend/CONTRIBUTING.md](backend/CONTRIBUTING.md#ci-commands-for-maintainers) |

If you see **other** unexpected failures on a fork PR that look like missing
credentials or secret accessibility (especially outside Konflux), please note
them on the PR so maintainers can confirm and update this section.

**If you opened a fork PR:** keep GitHub Actions checks green. If a Konflux
check fails or you need a maintainer-only command, ask on the PR (for example:
“Could a maintainer please help with this Konflux / Required Checks failure?”).

**How results show up:** Konflux pipelines appear as GitHub Checks on the PR
(names like `Konflux kflux-prd-rh03 / …` and `Red Hat Konflux / …`). The
`(Backend)/(Frontend) Konflux Gate` jobs wait on the **container build +
Conforma** checks and feed into `(Backend)/(Frontend) Required Checks`. Konflux
API/UI test pipelines are separate checks (and may post a summary comment);
they are not what the Konflux Gate waits on.

Visual baseline updates via `/update-screenshots` are documented separately in
[frontend/packages/syntara-ui/VISUAL_REGRESSION.md](frontend/packages/syntara-ui/VISUAL_REGRESSION.md)
(that command refuses fork PRs).


## Reporting Bugs

Report bugs and feature requests via
[GitHub Issues](https://github.com/syntara-orchestration/syntara/issues)
(same as [GOVERNANCE.md](GOVERNANCE.md)). Security vulnerabilities must follow
[`.github/SECURITY.md`](.github/SECURITY.md) instead of public issues.

## Contract Generation

When backend API schemas change, regenerate the frontend TypeScript types:

```bash
make gen-contracts
```

This reads OpenAPI specs from `backend/src/syntara/schemas/` and generates types in `frontend/packages/syntara-contracts/src/`. Include the regenerated types in the same PR as the schema changes.

## Commit Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

## Developer Certificate of Origin

All contributions MUST include a `Signed-off-by` line in the commit message, certifying that you wrote or have the right to submit the code under the project's license. Add it automatically with:

```bash
git commit -s
```

By signing off, you agree to the [Developer Certificate of Origin](https://developercertificate.org/).

## Code Review

All changes require review before merging. Backend-only changes need backend reviewer approval; frontend-only changes need frontend reviewer approval. Cross-cutting changes need both.

## Getting Help

Have a question or need guidance? Start a conversation in [GitHub Discussions](https://github.com/orgs/syntara-orchestration/discussions) before opening an issue. For bugs and feature requests, use [GitHub Issues](https://github.com/syntara-orchestration/syntara/issues).
