# Contributing to Nexus

Thank you for your interest in contributing to the Nexus project!

This document outlines the guidelines and best practices for contributing to this system.

## Ways to Contribute

There are many ways you can help make the project better:

- **Report bugs** - Help us identify and fix issues
- **Submit feature requests** - Suggest new functionality
- **Contribute code** - Fix bugs or implement new features
- **Improve documentation** - Help make our docs clearer and more comprehensive
- **Review pull requests** - Help maintain code quality

Visit our issue tracker for tracking issues and contributions.

## Getting Started

### Before You Begin

1. **Check existing issues** - Before reporting a bug or requesting a feature, search existing issues to avoid duplicates
2. **Discuss major changes** - For significant modifications, please open an issue first to discuss your approach and avoid duplicate efforts
3. **Review the codebase** - Familiarize yourself with the project structure and coding conventions

### Setting Up Your Development Environment

#### Prerequisites

- Python 3.12 or higher
- `uv` package manager

#### Installation

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Fork the repository on GitHub

3. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/syntara.git
   cd syntara/backend
   ```

4. Set up the upstream remote:
   ```bash
   git remote add upstream https://github.com/syntara-orchestration/syntara.git
   ```

5. **Install dependencies and setup the project**:
   ```bash
   make install
   ```

This project uses `uv` for dependency management and provides a comprehensive Makefile for development tasks.

## Development Workflow

### Creating a Branch

1. Ensure your main branch is up to date:
   ```bash
   git checkout main
   git pull upstream main
   ```

2. Create a new branch for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

### Making Changes

1. **Follow coding conventions** - Maintain consistency with the existing codebase
2. **Write clear commit messages** - Use descriptive commit messages that explain what and why
3. **Add tests** - Include appropriate tests for new functionality
4. **Update documentation** - Update relevant documentation for your changes

### Commit Message Guidelines

This project requires [Conventional Commits](https://www.conventionalcommits.org/) format, enforced by pre-commit hook.

```
feat: add user authentication system
fix: resolve database connection timeout
docs: update API documentation
refactor: simplify error handling logic
test: add integration tests for workflow engine
chore: update dependencies
```

**Rules:**
- Use the imperative mood ("add feature" not "added feature")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

### Development Commands

This project provides a comprehensive Makefile for development tasks.

For a complete list of available commands and their descriptions, see the [Development Commands section in README.md](README.md#development-commands).

### Testing

Before submitting your changes:

1. **Run the full test suite**:
   ```bash
   make test
   ```

2. **Run tests with coverage** (recommended):
   ```bash
   make test-coverage
   ```

3. **Add tests for new functionality** - All new code should include appropriate tests

4. **Verify that your changes don't break existing functionality**

#### Test Types

- **Unit tests**: `make test-unit` - Test individual components in isolation
- **Integration tests**: `make test-integration` - Test component interactions
- **Coverage reports**: `make test-coverage` - Ensure adequate test coverage

### Pre-commit

The project uses `pre-commit`.

`pre-commit` is installed by the `make install` target.

`pre-commit` is set up to run each time you create a new commit.

If you want to run pre-commit against all tracked files without committing, use:
```bash
pre-commit run --all
```

The pre-commit configuration file is located at `.pre-commit-config.yaml` in the repository.

### OpenAPI Spec Changes

**If your PR modifies `src/syntara/schemas/openapi.yaml`**, two automated checks apply:

#### Local Validation (Before Pushing)

Pre-commit runs OpenAPI checks automatically when `openapi.yaml` changes. You can also run them manually:

```bash
# Check for breaking changes against devel branch
make check-openapi-breaking

# Or run the script directly with custom options
./scripts/openapi/check-breaking-changes.py --base devel --head HEAD --format text
```

This helps you catch issues before pushing to GitHub and speeds up your development workflow.

#### 1. Regenerate Frontend Contracts

Since backend and frontend live in the same monorepo, include the regenerated TypeScript contracts in the same PR:

```bash
make gen-contracts
```

This updates `frontend/packages/syntara-contracts/src/` with types matching your schema changes.

CI posts an informational warning if the spec changed but contracts were not regenerated. For spec-only changes with no type impact (descriptions, examples, metadata), add to the PR description: `no-contract-regen: <justification>`.

#### 2. Breaking Changes Check

The pre-commit hook (enforced in CI) compares your spec against `devel` to detect breaking changes (removed fields, type changes, deleted endpoints).

**If breaking changes are detected**, you must acknowledge them in the PR description:

- Add to PR description: `breaking-change-ack: <detailed justification>`
- Minimum 20 characters explaining why necessary, migration path, and how the frontend is updated
- Example: `breaking-change-ack: Removing deprecated created_by_id field in favor of created_by object. Regenerated contracts and updated UI references in this PR. Migration guide added to API docs.`

**This check blocks merge** until breaking changes are acknowledged. See [OpenAPI Breaking Changes](docs/openapi-breaking-changes.md) for details.

### Submitting a Pull Request

1. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Open a pull request against the `devel` branch of the upstream repository

3. **Fill out the pull request template** with:
   - A clear description of the changes
   - The motivation for the changes
   - Any breaking changes
   - Testing instructions

4. **Link related issues** - Reference any related issues in your pull request

5. **For OpenAPI changes** - See [OpenAPI Spec Changes](#openapi-spec-changes) above

## CI Commands for Maintainers

Maintainers (organization owners and members) can trigger CI actions via PR comments:

| Command | Description |
|---------|-------------|
| `/build-pr-image` | Builds the container image for the PR and pushes it to the container registry. |

## Code Guidelines

### General Principles

- **Keep it simple** - Prefer simple, readable solutions
- **Be consistent** - Follow existing patterns and conventions
- **Document your code** - Add comments for complex logic
- **Think about maintainability** - Write code that others can easily understand and modify

### Python-Specific Requirements

This is a Python project with strict code quality standards. For detailed information about:

- **Project structure** - See [Project Structure in README.md](README.md#project-structure)
- **Code quality standards** - See [Code Quality in README.md](README.md#code-quality)  
- **Development workflow** - See [Developer Workflow in README.md](README.md#developer-workflow)

#### Key Requirements
- **Type checking is mandatory** - All code must pass mypy type checking
- **Code formatting** - Code is automatically formatted using Ruff
- **Testing** - All new code should include appropriate tests

#### Quality Checks
Before submitting code, ensure it passes all quality checks:
```bash
make format  # Format code
make lint    # Check linting and types  
make test    # Run all tests
```

### Code Review Process

1. All code changes require review before merging
2. Address reviewer feedback promptly and respectfully
3. Be open to suggestions and alternative approaches
4. Ensure CI/CD checks pass before requesting review

## Reporting Issues

When reporting bugs or issues:

1. **Use a clear, descriptive title**
2. **Provide steps to reproduce** the issue
3. **Include relevant details** such as:
   - Operating system and version
   - Software versions
   - Error messages and logs
   - Expected vs. actual behavior

## Feature Requests

When requesting new features:

1. **Explain the use case** - Why is this feature needed?
2. **Describe the desired behavior** - What should the feature do?
3. **Consider alternatives** - Are there other ways to achieve the same goal?

## Community Guidelines

- **Be respectful** - Treat all community members with respect
- **Be constructive** - Provide helpful feedback and suggestions
- **Be patient** - Remember that everyone is volunteering their time
- **Follow the code of conduct** - Maintain a welcoming environment for all

## Getting Help

If you need help or have questions:

1. Check the documentation
2. Search existing issues
3. Open a new issue with the "question" label
4. Reach out to maintainers


## Recognition

Contributors who make significant improvements to the project will be recognized in our contributors list and release notes.

Thank you for contributing to Nexus!
