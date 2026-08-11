# Orchestrator CLI

The `orchestrator` command-line client provides access to the Orchestrator API from the terminal. It dynamically builds commands at runtime from the OpenAPI spec and ships as a standalone `orchestrator-cli` Python package (separate from the auto-generated `syntara-api-client`).

## Installation

Build and install from this monorepo (recommended for a working CLI):

```bash
cd backend/src/api_client && uv build
cd ../cli && uv build
uv pip install \
  ../api_client/dist/syntara_api_client-*.whl \
  ./dist/orchestrator_cli-*.whl
```

`orchestrator-cli` bundles `openapi.yaml` so `from orchestrator_cli import app` works outside the source tree. Dynamic commands still require the **monorepo** `syntara-api-client` wheel (tag-module layout under `syntara_api_client/api/…`). The PyPI distribution with the same name is a different package and yields zero command groups.

You can also run it as a Python module:

```bash
python -m orchestrator_cli
```

## Authentication

### Login (recommended)

```bash
orchestrator authentication login --username admin --password <password>
```

On success, the token is **automatically saved** to `~/.orchestrator/` and used for all subsequent commands — no need to pass `--token` or set environment variables.

Tokens are stored per-instance, so you can work with multiple servers without conflicts. Expired tokens are automatically purged.

### Environment variables

```bash
export APP_CLI_URL=http://localhost:8000
export APP_CLI_TOKEN=<your-jwt-token>
```

### CLI flags

```bash
orchestrator --base-url http://localhost:8000 --token <token> users list
```

### Resolution order

The CLI resolves the token in this order (first match wins):

1. `--token` flag
2. `APP_CLI_TOKEN` environment variable
3. Cached token from `~/.orchestrator/` (saved by `login`)

If neither is set, `--base-url` defaults to `http://localhost:8000`.

### Extracting the token (scripting)

If you need the raw token for scripting:

```bash
export APP_CLI_TOKEN=$(orchestrator authentication login \
  --username admin --password secret | jq -r .access_token)
```

## Command structure

Commands follow a `<resource> <action>` pattern:

```
orchestrator <resource-group> <command> [ARGUMENTS] [OPTIONS]
```

- **Resource groups** map to API tags: `users`, `groups`, `projects`, `workflows`, `roles`, `policies`, `role_assignments`, `credentials`, etc.
- **Commands** map to API operations: `list`, `create`, `get`, `update`, `delete`, plus resource-specific actions like `add_member`, `list_role_assignments`, etc.
- **Arguments** are positional (path parameters like IDs).
- **Options** are named flags (`--name`, `--email`, etc.).

### Examples

```bash
# Login (token is saved automatically)
orchestrator authentication login --username admin --password secret

# User management
orchestrator users list
orchestrator users create --username alice --email alice@example.com \
  --full-name "Alice" --password secret
orchestrator users get <user-id>
orchestrator users update <user-id> --full-name "Alice Smith"
orchestrator users delete <user-id>

# Groups
orchestrator groups create --name backend-eng --description "Backend team"
orchestrator groups list
orchestrator groups add_member <group-id> --user-id <user-id>
orchestrator groups list_members <group-id>

# Projects
orchestrator projects create --name staging --description "Staging environment"
orchestrator projects list

# Role assignments
orchestrator role_assignments create --principal-type user \
  --principal-id <user-id> --role-name admin
orchestrator users create-role_assignment <user-id> --role-name viewer
orchestrator users create-role_assignment <user-id> --role-name project-admin \
  --project-id <project-id>

# Workflows
orchestrator workflows create --name my-workflow \
  --workflow-definition @workflow.json --project-id <project-id>
orchestrator workflows list
orchestrator workflows get <workflow-id>

# Authorization checks
orchestrator authorization can-i --action read --resource-type workflow
orchestrator authorization what-can-i

# Credentials
orchestrator credentials create --name "my-aap" --credential-type-id <type-id> \
  --project-id <project-id> --inputs '{"host": "https://aap.example.com", "token": "..."}'

# Audit
orchestrator audit-events list --limit 50 --event-category authorization
```

## Output format

All commands output JSON to stdout. Errors are printed to stderr with a non-zero exit code.

Successful response:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "alice",
  "email": "alice@example.com",
  "full_name": "Alice",
  "is_active": true,
  "created_at": "2025-01-15T10:30:00Z"
}
```

Error response (stderr):

```json
{
  "error": {
    "type": "https://example.com/errors/not-found",
    "title": "Not Found",
    "detail": "User not found"
  },
  "status": 404
}
```

### Piping and scripting

The JSON output is designed for piping with `jq`:

```bash
# Get all usernames
orchestrator users list | jq -r '.resources[].username'

# Get a project ID by name
PROJECT_ID=$(orchestrator projects list | jq -r '.resources[] | select(.name=="staging") | .id')

# Create a user and capture the ID
USER_ID=$(orchestrator users create --username bob --email bob@example.com \
  --full-name "Bob" --password secret | jq -r .id)
```

## Complex fields

Some commands accept complex values (objects, arrays). These can be passed as:

1. **Inline JSON string**: `--inputs '{"host": "https://example.com"}'`
2. **File reference**: `--workflow-definition @path/to/workflow.json`

The `@` prefix reads the file contents and parses it as JSON.

## Discovering commands

Every command supports `--help`:

```bash
orchestrator --help                    # list all resource groups
orchestrator users --help              # list all user commands
orchestrator users create --help       # show all options for user creation
```

Help text includes parameter descriptions, default values, and enum choices where applicable.

## How the CLI works

The CLI is built dynamically at runtime from the OpenAPI specification — there are no generated CLI source files to maintain. When you run any `orchestrator` command:

1. The CLI locates the schema sources under `src/syntara/schemas/`
2. It hashes all source files and compares against a saved manifest in `~/.orchestrator/spec-hashes.json`
3. If anything changed (or no cache exists), the spec is re-bundled and cached to `~/.orchestrator/openapi.json`
4. Commands, arguments, and options are constructed from the cached spec at runtime

When the API spec changes, the CLI automatically picks up the changes on the next invocation — no code generation step required.

### File layout

```
src/
├── cli/                         # hand-written CLI package (never auto-generated)
│   ├── pyproject.toml           # CLI package metadata, deps, and entrypoint
│   └── orchestrator_cli/
│       ├── __init__.py          # app entrypoint, global options (--base-url, --token)
│       ├── __main__.py          # python -m support
│       ├── auth.py              # token persistence (~/.orchestrator/)
│       ├── commands.py          # dynamic command builder (spec → Typer commands)
│       └── spec.py              # spec caching and auto-bundling
├── api_client/                  # auto-generated API client (regenerated by make)
│   ├── pyproject.toml           # generated package metadata
│   └── syntara_api_client/
│       ├── api/                 # generated endpoint modules
│       ├── models/              # generated model classes
│       ├── client.py            # Client / AuthenticatedClient
│       └── ...
```

### Local data (`~/.orchestrator/`)

| File | Purpose |
|------|---------|
| `openapi.json` | Cached bundled OpenAPI spec |
| `spec-hashes.json` | SHA-256 manifest of schema source files |
| `<instance>.json` | Saved auth token (one per server instance) |

### Benchmarking CLI overhead

Set `APP_CLI_BENCHMARK=1` to print a timing breakdown to `stderr` for one CLI invocation:

```bash
APP_CLI_BENCHMARK=1 orchestrator --base-url http://localhost:8000 groups list --limit 1
```

The summary includes startup phases such as spec loading and dynamic command construction, plus request phases such as client creation, model import, endpoint import, API call, and response formatting.
