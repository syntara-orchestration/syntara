# Contributing

This is a monorepo with two components. General guidelines apply to both; component-specific details are in their respective CONTRIBUTING files:

- **Backend**: [backend/CONTRIBUTING.md](backend/CONTRIBUTING.md)
- **Frontend**: [frontend/CONTRIBUTING.md](frontend/CONTRIBUTING.md)

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

The use of AI tools MUST be explicitly disclosed by the author when a significant part of the contribution is taken from the AI tools output without significant changes. Grammar, spelling, and stylistic corrections do not need disclosure.

We recommend using the following statement as a disclosure: `Assisted-by:` followed by any information about the contributor’s use of AI tools that they consider relevant, for example:

      i. `Assisted-by: gpt-5.4`
      ii. `Assisted-by: Opus 4.6`
      iii. `Assisted-by: locally trained model`


See [AI_POLICY.md](.github/AI_POLICY.md) for more details.

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

## Code Review

All changes require review before merging. Backend-only changes need backend reviewer approval; frontend-only changes need frontend reviewer approval. Cross-cutting changes need both.
