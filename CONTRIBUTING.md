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

Have a question or need guidance? Start a conversation in [GitHub Discussions](https://github.com/orgs/syntara-orchestration/discussions) before opening an issue.
