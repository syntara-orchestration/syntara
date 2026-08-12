# OpenAPI Validation Scripts

This directory contains standalone scripts for validating OpenAPI spec changes. These scripts are used by GitHub Actions workflows but can also be run locally for development and debugging.

## Scripts Overview

### Core Scripts

#### `install-oasdiff.sh`
Installs the `oasdiff` tool with checksum verification to prevent supply chain attacks.

```bash
# Install to /usr/local/bin (default)
./install-oasdiff.sh

# Install to custom directory
./install-oasdiff.sh ~/bin
```

**Environment Variables:**
- `OASDIFF_VERSION` - Version to install (default: 1.18.5)
- `EXPECTED_CHECKSUM` - Expected SHA256 checksum (pinned for version)

#### `check-breaking-changes.py`
Checks for breaking changes in OpenAPI spec using `oasdiff`. Automatically resolves the spec path relative to the git root, so it works from any subdirectory (e.g., `backend/` in the monorepo).

```bash
# Compare current branch against devel
./check-breaking-changes.py --base devel --head HEAD

# Compare specific spec files
./check-breaking-changes.py --base-spec old.yaml --head-spec new.yaml

# Include PR body for acknowledgment check
./check-breaking-changes.py --base devel --head HEAD --pr-body "$(cat pr_description.txt)"

# Output as text instead of JSON
./check-breaking-changes.py --base devel --head HEAD --format text
```

**Exit Codes:**
- `0` - No breaking changes OR breaking changes acknowledged
- `1` - Breaking changes detected and not acknowledged
- `2` - Error running oasdiff or processing specs

**Output (JSON):**
```json
{
  "has_breaking_changes": bool,
  "breaking_changes": "oasdiff output...",
  "all_changes": "full changelog...",
  "acknowledged": bool,
  "justification": "justification text",
  "ack_insufficient": bool
}
```

#### `check-contract-regeneration.py`
Checks that frontend contracts are regenerated when the OpenAPI spec changes. In the monorepo, when `backend/src/syntara/schemas/openapi.yaml` changes, the TypeScript types in `frontend/packages/syntara-contracts/src/` should also be updated via `make gen-contracts`. If the bundled spec is unchanged, the check is skipped.

```bash
# Check against devel branch (auto-detects changed files)
./check-contract-regeneration.py --changed-files-from devel

# Check with explicit file list
./check-contract-regeneration.py --changed-files backend/src/syntara/schemas/openapi.yaml frontend/packages/syntara-contracts/src/index.ts

# Include PR body for exception justification
./check-contract-regeneration.py --changed-files-from devel --pr-body "no-contract-regen: description-only change"

# Output as text instead of JSON
./check-contract-regeneration.py --changed-files-from devel --format text
```

**Exit Codes:**
- Always exits `0` (contract check is informational, not blocking)

**Output (JSON):**
```json
{
  "spec_changed": bool,
  "contracts_updated": bool,
  "has_exception": bool,
  "exception_justification": "text" | null,
  "exception_valid": bool,
  "severity": "notice" | "warning",
  "message": "formatted markdown message"
}
```

### GitHub Integration Scripts

#### `post-breaking-changes-comment.py`
Posts or updates GitHub PR comment with breaking changes check results.

```bash
# Post results to PR
./post-breaking-changes-comment.py \
  --results results.json \
  --pr-number 123

# Specify repository explicitly
./post-breaking-changes-comment.py \
  --results results.json \
  --pr-number 123 \
  --repo syntara-orchestration/syntara
```

**Requirements:**
- `gh` CLI must be installed and authenticated
- Results file from `check-breaking-changes.py`

#### `post-contract-regeneration-comment.py`
Posts or updates GitHub PR comment with contract regeneration check results.

```bash
# Post results to PR
./post-contract-regeneration-comment.py \
  --results results.json \
  --pr-number 123

# Specify repository explicitly
./post-contract-regeneration-comment.py \
  --results results.json \
  --pr-number 123 \
  --repo syntara-orchestration/syntara
```

**Requirements:**
- `gh` CLI must be installed and authenticated
- Results file from `check-contract-regeneration.py`

## Local Development Workflow

### 1. Install Dependencies

```bash
# Install oasdiff
./scripts/openapi/install-oasdiff.sh

# Verify installation
oasdiff --version
```

### 2. Check for Breaking Changes

```bash
# Using make (recommended)
make check-openapi-breaking

# Or directly
./scripts/openapi/check-breaking-changes.py \
  --base devel \
  --head HEAD \
  --format text
```

### 3. Check Contract Regeneration

```bash
# Using make (recommended) — skips when openapi.yaml is unchanged vs devel
make check-openapi-contracts

# Or directly — auto-detects changed files vs devel
./scripts/openapi/check-contract-regeneration.py \
  --changed-files-from devel \
  --format text

# Simulate spec change without contract regen (expect warning)
./scripts/openapi/check-contract-regeneration.py \
  --changed-files backend/src/syntara/schemas/openapi.yaml \
  --format text

# Simulate spec + contract update (expect success)
./scripts/openapi/check-contract-regeneration.py \
  --changed-files backend/src/syntara/schemas/openapi.yaml \
    frontend/packages/syntara-contracts/src/index.ts \
  --format text

# Spec change with no-contract-regen exception in PR body
./scripts/openapi/check-contract-regeneration.py \
  --changed-files backend/src/syntara/schemas/openapi.yaml \
  --pr-body "no-contract-regen: description-only change, no type impact" \
  --format text
```

### 4. Test Full Workflow Locally

```bash
# 1. Check for breaking changes with PR body
PR_BODY="breaking-change-ack: This change is necessary for the new feature"

./scripts/openapi/check-breaking-changes.py \
  --base devel \
  --head HEAD \
  --pr-body "$PR_BODY" \
  --output /tmp/breaking-results.json

# 2. Check contract regeneration
./scripts/openapi/check-contract-regeneration.py \
  --changed-files-from devel \
  --pr-body "$PR_BODY" \
  --output /tmp/contract-regeneration-results.json

# 3. View results
cat /tmp/breaking-results.json | jq
cat /tmp/contract-regeneration-results.json | jq
```

## Makefile Targets

### `make check-openapi-breaking-pre-commit`
Pre-commit hook target: skips when `openapi.yaml` is unchanged vs `devel`, otherwise runs `check-openapi-breaking`.

### `make check-openapi-breaking`
Checks OpenAPI spec for breaking changes against the devel branch. Auto-installs `oasdiff` if not present.

```bash
make check-openapi-breaking
```

### `make check-openapi-contracts`
Checks if frontend contracts were regenerated when the OpenAPI spec changed.

```bash
make check-openapi-contracts
```

### `make check-openapi`
Runs all OpenAPI checks (breaking changes + contract regeneration).

```bash
make check-openapi
```

## Integration with CI

These scripts are used by the monorepo CI workflow (`.github/workflows/ci-backend.yml`):

- **Breaking changes (blocking):** `check-openapi-breaking-pre-commit` pre-commit hook, enforced by the CI `pre-commit` job
- **PR comments (informational):** `openapi-breaking-changes` CI job posts breaking-change and contract regeneration results on pull requests when `backend/src/syntara/schemas/openapi.yaml` changes

The CI `pre-commit` job:
1. Fetches `devel` for OpenAPI baseline comparison
2. Passes `OPENAPI_PR_BODY` from the pull request for breaking-change acknowledgment

The `openapi-breaking-changes` job:
1. Detects changes to `backend/src/syntara/schemas/openapi.yaml`
2. Runs `check-breaking-changes.py` and posts results via `post-breaking-changes-comment.py`
3. Runs `check-contract-regeneration.py` to verify contracts are regenerated and posts results via `post-contract-regeneration-comment.py`

## Security Features

All scripts include:
- **Markdown/HTML escaping** to prevent injection attacks in comments
- **Checksum verification** for downloaded binaries (oasdiff)
- **Input validation** for PR body content and justifications

## Troubleshooting

### `oasdiff` not found
```bash
# Install it
./scripts/openapi/install-oasdiff.sh

# Or use make which auto-installs
make check-openapi-breaking
```

### Checksum verification failed
The pinned checksum doesn't match the downloaded file. This could indicate:
- Supply chain attack (binary was modified)
- Wrong version specified
- Network corruption

**DO NOT** bypass the check. Instead:
1. Verify you're using the correct version
2. Check the official checksums at https://github.com/oasdiff/oasdiff/releases
3. Update `EXPECTED_CHECKSUM` in the script if upgrading versions

### `gh` CLI not authenticated
```bash
# Login to GitHub CLI
gh auth login

# Verify
gh auth status
```

## Adding New Checks

To add a new OpenAPI validation:

1. Create a new script in this directory (e.g., `check-something.py`)
2. Follow the existing pattern:
   - Accept CLI arguments for input
   - Output JSON with structured results
   - Include `--format text` option for human-readable output
   - Exit with appropriate codes
3. Add a posting script if it needs PR comments
4. Wire into pre-commit and/or the CI `openapi-breaking-changes` job as appropriate
5. Add a Makefile target for local execution
6. Document in this README

## References

- [oasdiff documentation](https://github.com/oasdiff/oasdiff)
- [Breaking Changes Detection](../../docs/openapi-breaking-changes.md)
