# Static Analysis

Three static analysis checks run in CI to catch dead code, import cycles, and orphan modules.

## Dead Code Detection (Vulture)

[Vulture](https://github.com/jendrikseipp/vulture) finds unused functions, classes, variables, and imports via AST analysis.

### How It Works

- Scans `src/syntara/` at 100% confidence (no speculative findings)
- Ignores test files, migrations, and `__pycache__`
- Skips code under framework decorators (`@router.*`, `@validator`, `@property`, etc.)
- Known false positives suppressed via `ignore_names` and `exclude` in `pyproject.toml`

### Running Locally

```bash
make check-dead-code
```

### Configuration

All config lives in `pyproject.toml` under `[tool.vulture]`:

- `exclude` — directory/file patterns to skip entirely (migrations, tests)
- `ignore_names` — variable/parameter names to suppress (Protocol params, callback args)
- `ignore_decorators` — decorator patterns whose decorated code is skipped

### Handling Failures

1. **Real dead code**: remove it
2. **False positive from excluded directory**: add pattern to `exclude` in `[tool.vulture]`
3. **False positive from parameter name**: add to `ignore_names` in `[tool.vulture]`
4. **False positive from decorator**: add pattern to `ignore_decorators` in `[tool.vulture]`

### Known False Positive Patterns

| Pattern | Example | Why Vulture Flags It |
|---------|---------|---------------------|
| Alembic callback parameters | `reflected`, `compare_to` in `include_object()` | Required by Alembic API contract, not read in body |
| Protocol method parameters | `whence` in `Seekable.seek()` | Required by interface, implementations provide the value |
| `@fastapi_exception` imports | Exception classes in `error_handlers.py` | Imported for decorator side-effect registration |

### Limitation

Vulture checks whether individual symbols are referenced, but it cannot detect an entire module that is internally self-referencing yet never imported from outside. The orphan module check (below) covers that gap.

## Import Cycle Detection (pyan3)

[pyan3](https://github.com/Technologicat/pyan) detects circular import dependencies at the module level.

### How It Works

- Runs `pyan3 --module-level --cycles` against `src/syntara/`
- Deduplicates cycle permutations into unique edges (A ↔ B pairs)
- Compares against baseline in `tools/ci/known_import_cycles.json`
- Fails if any new cycle edges appear

### Running Locally

```bash
make check-cycles
```

### Configuration

- **Checker script**: `tools/ci/check_import_cycles.py`
- **Baseline**: `tools/ci/known_import_cycles.json`

### Handling Failures

1. **Accidental cycle**: refactor to break the circular dependency (move shared types to a separate module, use TYPE_CHECKING imports, restructure `__init__.py` exports)
2. **Intentional structural pattern**: add the edge pair to `known_import_cycles.json` with a comment in the PR explaining why the cycle is by-design

### Known Cycle Patterns

| Pattern | Domains | Status |
|---------|---------|--------|
| `auth.__init__` ↔ `auth.dependencies` | auth | **Accepted** — auth re-exports (`get_current_user`) are actively consumed by 20+ modules across the codebase. This is intentional public API encapsulation. |

### Exception Handler Import Patterns

Two patterns exist in the codebase for wiring exceptions to error handlers:

| Pattern | How | Cycle? | Used By |
|---------|-----|--------|---------|
| **B** — string path | `@fastapi_exception(handler="syntara.X.error_handlers.handler_func")` | No | all domains |
| **C** — embedded | Handler functions defined in exceptions.py itself | No | authz |

Pattern B is the standard approach. String paths are resolved via `importlib` at registration time. See `src/syntara/core/exception_registry.py` line 59.

## Orphan Module Detection

Custom script that finds Python modules not imported by any other module in the codebase. Catches dead modules where all symbols reference each other internally (Vulture would miss these since all symbols appear "used").

### How It Works

- Scans all `.py` files in `src/syntara/` (excluding `__init__.py`, tests)
- Extracts all `import` and `from ... import` statements (absolute and relative)
- Identifies modules with zero incoming imports
- Compares against glob-pattern allowlist in `tools/ci/known_orphan_modules.json`
- Fails if any new orphan modules appear

### Running Locally

```bash
make check-orphans
```

### Configuration

- **Checker script**: `tools/ci/check_orphan_modules.py`
- **Allowlist**: `tools/ci/known_orphan_modules.json` (glob patterns with justifications)

### Handling Failures

1. **Genuinely dead module**: remove it
2. **New module using an existing pattern** (e.g., a new router): existing patterns like `syntara/*/router.py` already cover it — no allowlist change needed
3. **New discovery/registration pattern**: add a glob pattern to `known_orphan_modules.json` with a justification documenting the discovery mechanism. Every pattern must explain HOW the module is loaded at runtime
4. **False positive from package-style import**: modules imported via `from syntara.X import module_name` (not `from syntara.X.module_name import ...`) are invisible to the import scanner — add a specific pattern with the import mechanism documented

### Adding Allowlist Patterns

Each pattern in `known_orphan_modules.json` maps to a justification string. Before adding a new pattern:

1. **Verify the module is actually used** — grep for its function/class names across the entire repo, not just import paths. Checking import paths alone misses package-style imports (`from syntara.X import module_name`)
2. **Document the registration mechanism** — how does the module get loaded? (discovery scan, CLI entrypoint, `importlib`, package import, etc.)
3. **Prefer specific patterns over broad ones** — `syntara/files/validators.py` is better than `syntara/*/validators.py` unless the pattern genuinely applies to all domains
4. **Do not assume existing state is valid** — a module being in the repo does not mean it is used. Verify before allowlisting

## CI Integration

All three checks are pre-commit hooks in `.pre-commit-config.yaml`, following the same pattern as other local hooks (`ruff-format`, `api-spec-validation`, etc.). They run:

- **Locally**: on every commit via `pre-commit`
- **In CI**: via the existing `uv run pre-commit run --all-files` step in the `pre-commit` job

No separate CI steps needed — pre-commit handles both environments.

## Ad-Hoc Analysis Tools

Additional exploration scripts and artifacts in `scripts/explore/` (not in CI):

| File | Purpose |
|------|---------|
| `call-graph-module-level.dot` | Module dependency graph in Graphviz format |
| `call-graph-module-level-fdp.svg` | Rendered dependency graph (force-directed layout) |
| `extract_cycle_edges.py` | Extract unique cycle edges from pyan3 output as JSON |
| `verify_dead_code_suspects.py` | Cross-reference suspect modules against all repo files for usage |
| `list_pattern_matches.py` | Show which orphan modules match each allowlist pattern |

### Generating a Module Dependency Graph

Requires graphviz (`dot`) installed on the system.

```bash
# Generate dot file
uv run pyan3 --module-level --dot --colored --grouped --nested-groups --concentrate \
  --exclude 'test_*.py' --exclude '*/tests/*' --exclude '*_test.py' \
  --root src src/syntara/**/*.py \
  > scripts/explore/call-graph-module-level.dot

# Render to SVG (fdp layout handles large graphs better than dot)
uv run pyan3 --module-level --svg --colored --grouped --nested-groups --concentrate \
  --graphviz-layout fdp \
  --exclude 'test_*.py' --exclude '*/tests/*' --exclude '*_test.py' \
  --root src \
  -f scripts/explore/call-graph-module-level-fdp.svg \
  src/syntara/**/*.py
```
