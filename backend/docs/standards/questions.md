# Standards: Open Items

## Decisions Needed

### Coverage threshold

`pyproject.toml` enforces 80%. Constitution targets 90%. Need to check actual coverage and decide which number to enforce.

### README API examples use camelCase

The API is snake_case everywhere. README.md examples (`createdBy`, `sessionId`, `contextData`) are outdated and should be updated.

### Workflow and contribution process documentation

Constitution mandates: pull requests required for all changes, minimum two approvals before merge, squash and merge preferred for clean history. These belong in CONTRIBUTING.md or a workflow standard, but neither fully covers them. Need to decide: create a new `workflow.md` standard, add to CONTRIBUTING.md, or both?

## Standards to Draft

### Structured logging output format

No standard for expected JSON field names, required fields per event type, or correlation ID propagation. Should be based on observed patterns in `src/syntara/core/logging/logging.py`.

### Architecture principles (dependency injection, composition, SOLID)

Constitution mandates dependency injection (constructor injection as primary pattern), composition over inheritance, separation of concerns between layers, and SOLID principles. No domain standard documents the Syntara-specific patterns, examples, or enforcement strategy for these.

### API security and schema management

Constitution mandates: all authenticated endpoints must document security schemes in the specification, schema changes must be validated for backward compatibility before release, deprecated fields must be marked with removal timeline. None of these are covered in any existing domain standard.

### Documentation requirements (docstrings, API docs)

Constitution mandates: every class must have a docstring describing its purpose, every public function/method must document parameters with types, return value, exceptions, and usage examples for complex functions, API changes must update corresponding documentation in the same PR. No domain standard documents these conventions or shows compliant examples.

### Linter/typecheck ignore justification

Constitution mandates: "When ignoring a rule for linters or typecheckers a justification must be provided." No domain standard documents the expected format (inline comment? linked issue?) or enforcement mechanism.

### Security scanning

Constitution mandates: "Security scanning must pass without high/critical vulnerabilities." No domain standard documents which tools are used, what thresholds apply, or how this integrates with CI. Related to the deferred "Security standards" item below but more specific.

### TDD workflow

Constitution mandates Red-Green-Refactor cycle for all new features and bug fixes. `testing.md` covers test structure, naming, fixtures, and infrastructure but does not document the TDD workflow itself (write test first, see it fail, implement, refactor).

## Deferred

- **OpenTelemetry / distributed tracing** — system still being built
- **Security standards** — scope unclear (scanning vs implementation)
- **Database migration review process** — insufficient context to document
