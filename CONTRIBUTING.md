# Contributing to Syntara

This is a monorepo with two components. General guidelines apply to both; component-specific details are in their respective CONTRIBUTING files:

- **Backend**: [backend/CONTRIBUTING.md](backend/CONTRIBUTING.md)
- **Frontend**: [frontend/CONTRIBUTING.md](frontend/CONTRIBUTING.md)

## Development Setup

```bash
make install    # Install all dependencies
make dev        # Start development servers
```

## Before Submitting a PR

```bash
make format     # Format both codebases
make lint       # Lint both codebases
make test       # Run all tests
make typecheck  # Type-check both codebases
```

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
