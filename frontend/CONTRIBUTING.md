# Contributing to Syntara UI

## Welcome Contributors!

We're excited that you're interested in contributing to the Syntara UI project. This document provides guidelines to help you contribute effectively.

All pull requests must pass the `(Frontend) Required Checks` CI gate before merging. This includes unit tests, type-checking, linting, and builds. SonarCloud analysis runs on PRs but is informational only and does not block merges.

## AI-Assisted Development

This project ships with AI agent skills (in `.claude/skills/`) that handle the repetitive parts of the development workflow — implementing features, reviewing code, and writing tests — while enforcing the project's standards automatically. These skills work with Claude Code, Cursor, or any tool that reads the skill files.

**New contributors should read [`docs/ai-assisted-development.md`](docs/ai-assisted-development.md) before writing any code.** It explains:

- How to use the **Frontend Specialist** agent to implement a feature using PatternFly, typed API clients, and Zod + react-hook-form
- How to use the **PR Review** skill to check your code against the quality checklist before opening a PR
- How to use the **Playwright E2E** skill to write end-to-end tests that work in both mock-API and real-backend mode
- How to apply the **UX Design System** skill to match the project design language
- How to review your implementation locally (dev server, browser states, keyboard/accessibility)
- How to fix common guideline violations flagged during review
- How to use `/frontend-build-ui-feature` to walk through the full workflow step by step

The guide includes copy-ready prompt templates, a workflow diagram, and worked examples.

---

## Prerequisites

- Node.js 22+ (see package.json for exact requirements)
- npm (comes with Node.js)
- Familiarity with React, TypeScript, and modern web development practices

## Getting Started

### 1. Fork and Clone the Repository

1. Fork the repository on GitHub
2. Clone your forked repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/syntara.git
   cd syntara/frontend
   ```

### 2. Set Up Development Environment

```bash
# Install dependencies
npm ci

# Set up git hooks (Husky) — required because ignore-scripts is enabled in .npmrc
npm run prepare

# Start development services
npm start
```

The application will be available at:

- UI: http://localhost:5173
- Mock API: http://localhost:3000

## Development Workflow

### Branch Strategy

- Create a new branch for each feature or bugfix
- Branch naming convention:
  - `feature/short-description` — new features
  - `bugfix/short-description` or `fix/short-description` — bug fixes
  - `docs/short-description` — documentation updates

### Making Changes

1. Create a new branch

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes
   - Follow existing code style
   - Add/update tests for your changes
   - Ensure all tests pass

3. Run tests and linting

   ```bash
   # Run all tests
   npm test

   # Format code
   npm run format
   ```

### Commit Guidelines

- Use meaningful commit messages
- Follow conventional commits format:

  ```
  type(scope): short description

  [optional detailed description]
  ```

  Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Pull Request Process

1. Ensure your code passes all tests and linting
2. Update documentation if necessary
3. Create a pull request with:
   - Clear title
   - Description of changes
   - Link to any related issues

### Code Review Process

- All submissions require review
- Maintainers will provide feedback
- Be prepared to make requested changes

### Manual CI Triggers

Some CI jobs can be manually triggered via slash commands in PR comments. Only repository owners and members can use these commands.

#### Manual E2E UI Test Runs

The Podman Compose E2E UI tests automatically run when frontend-relevant changes are detected. For backend-only PRs or other workflow changes, you can manually trigger these tests by commenting:

```
/run-e2e-ui-tests
```

## Code Readability Rules

We enforce code readability through ESLint rules that keep functions small, files focused, and logic simple. The size/readability thresholds below are generally configured as `warn` so they guide refactoring without blocking every PR, but new code should still respect them.

These thresholds are based on industry standards (Code Complete, SonarQube, BiomeJS):

| Rule                     | Limit              | What it enforces                                             |
| ------------------------ | ------------------ | ------------------------------------------------------------ |
| `max-lines`              | 500 lines/file     | Keep files focused on a single responsibility                |
| `max-lines-per-function` | 200 lines/function | Extract helpers instead of writing monoliths                 |
| `complexity`             | 20 (cyclomatic)    | Break complex branching into smaller functions               |
| `max-depth`              | 4 levels           | Use early returns instead of deep nesting                    |
| `max-params`             | 5 parameters       | Use an options object for functions with many inputs         |
| `max-nested-callbacks`   | 4 levels           | Flatten nested callbacks with named functions or async/await |

We also enforce modern TypeScript, React, and import hygiene rules as CI-blocking `error`s:

- **`prefer-optional-chain`** / **`prefer-nullish-coalescing`** — Use `?.` and `??` for safer, cleaner code
- **`require-array-sort-compare`** — Prevent subtle `Array.sort()` bugs
- **`switch-exhaustiveness-check`** — Handle all enum/union cases
- **`prefer-includes`** — Use `.includes()` instead of `.indexOf() !== -1`
- **`jsx-no-useless-fragment`** / **`self-closing-comp`** — Cleaner JSX
- **`sonarjs/no-nested-conditional`** — Prevent nested ternaries (Sonar S3358; aligns with SonarCloud)
- **`no-cycle`** / **`no-self-import`** — Catch circular dependencies

Blank lines and comments are excluded from line counts. Test files (`*.test.*`, `*.spec.*`) are exempt from size limits and complexity.

**If a rule blocks your work**, don't disable it inline. Instead, refactor:

- Long component? Extract sub-components or custom hooks.
- Deep nesting? Use early returns or guard clauses.
- Many parameters? Group them into a typed options object.

## Testing

### Running Tests

```bash
# Run all tests
npm test

# Run UI package tests
npm run test:ui

npm run test:coverage
```

### Test Coverage

- Aim to maintain or improve test coverage
- Write unit and integration tests for new features

## Reporting Issues

### Bug Reports

- Use GitHub Issues
- Include:
  - Steps to reproduce
  - Expected behavior
  - Actual behavior
  - Environment details (OS, Node version, etc.)

### Feature Requests

- Describe the proposed feature
- Provide context and use cases
- Be open to discussion

## Code of Conduct

- Be respectful and inclusive
- Collaborate constructively
- Focus on technical merit

## Questions?

If you have questions, please:

- Check existing documentation
- Open an issue for discussion
- Reach out to maintainers

Thank you for contributing to Syntara UI!
