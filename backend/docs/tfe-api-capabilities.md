# Terraform Enterprise API capabilities and prerequisites

Source: [Terraform Enterprise API documentation](https://developer.hashicorp.com/terraform/enterprise/api-docs)

## Scope

This page summarizes:

- The official Terraform Enterprise (TFE) API capability areas.
- The TFE operations currently exposed by Syntara workflow nodes.
- The prerequisites needed to access TFE endpoints.
- The requirements for running TFE workspaces.
- The workspace creation and VCS configuration options.

## Official TFE API capability areas

The official TFE API covers a subset of Terraform Enterprise product features. Its major endpoint families are:

- **Identity and account:** account details, users, user tokens.
- **System and administration:** ping, readiness, diagnostics, usage bundles, support bundles, nodes, admin organizations/runs/workspaces/users/versions/settings, SCIM administration.
- **Organizations:** organizations, memberships, tags, organization tokens.
- **Projects and access:** projects, project team access, teams, team memberships, team access, team tokens.
- **Workspaces:** create, update, list, show, delete, lock, unlock, tags, SSH keys, remote-state consumers, workspace resources, workspace transfers, retention policies.
- **Variables:** workspace variables and variable sets.
- **Run lifecycle:** configuration versions, runs, plans, applies, comments, run triggers, run tasks, cost estimates, plan exports.
- **State:** state versions, state outputs, rollback, garbage collection.
- **VCS:** OAuth clients, OAuth tokens, GitHub App installations, VCS events.
- **Agents:** agent pools, agents, agent tokens.
- **Policy enforcement:** policies, policy sets, policy checks, policy evaluations, policy parameters.
- **Private registry:** modules, providers, provider versions, GPG keys, module tests.
- **Notifications:** organization, project, team, and workspace notification configurations.
- **Other product capabilities:** no-code provisioning, Stacks, Explorer, assessments, change requests, IP allowlists, data retention policies, reserved tags.

## Syntara-supported TFE operations

Syntara currently exposes 28 TFE workflow operations:

| Area | Supported operations |
| --- | --- |
| Workspaces | Create, list, update settings, delete/safe-delete, fetch state outputs |
| Variables | Add, list, update, delete |
| Configuration | Create/upload configuration version |
| Runs | Trigger, get status with optional wait, apply, discard, cancel, force-cancel, list, add comment |
| VCS/GitHub | List installations, get installation, link VCS to workspace |
| Projects | Create, list, get, update, delete, move workspace into project, assign team permissions |

## General TFE API prerequisites

### Base URL and API paths

- Configure the TFE origin URL, for example `https://tfe.example.com` or `https://app.terraform.io`.
- Do **not** include `/api/v2` in the integration `base_url`; Syntara appends it automatically.
- Standard application endpoints use `/api/v2`.
- TFE system endpoints use `/api/v1` and may require a system API token or the admin-console port.

### Authentication

All standard TFE API requests require:

```http
Authorization: Bearer <token>
```

Valid token types are:

- **User tokens** — act as a specific user.
- **Team tokens** — intended for CI/CD plans and applies.
- **Organization tokens** — automate organization and workspace management, but cannot perform plans or applies.

For Syntara:

- Create an HTTP Bearer Token credential.
- Use it as the TFE integration’s management credential for validation.
- Select an execution credential on each TFE workflow step.
- Syntara does not support token refresh or OIDC.

### Organization and permissions

- Configure the default TFE organization name.
- Syntara validates access with `GET /api/v2/organizations/{organization}`.
- The execution credential must have the required TFE permissions for each operation.
- Missing permissions or entitlements can return `404`.

Relevant entitlements include:

- `operations` for runs, plans, and applies.
- `state-storage` for state outputs.
- `vcs-integrations` for VCS linking.
- `agents` for agent execution.
- `teams` for team and project access.

### TLS and network

- HTTPS is required by default.
- Configure a custom CA certificate if TFE uses a private certificate authority.
- Avoid disabling TLS verification unless absolutely necessary.
- For private or internal TFE hosts, allowlist the hostname with:

```bash
APP_INTEGRATION_URL_ALLOWED_HOSTS='["tfe.internal.example.com"]'
```

### API behavior

- Use JSON:API request and response formatting.
- Honor pagination.
- Respect the default limit of 30 requests per second.
- Treat TFE-provided blob or upload URLs as secrets.

## Run prerequisites

To use TFE runs:

1. Configure the TFE integration with `base_url`, `organization`, and TLS settings.
2. Use a **user or team token** as the execution credential.
3. Ensure the token has **Queue Plans** permission.
4. For apply operations, ensure the token also has **Apply Runs** permission.
5. Ensure the organization has the `operations` entitlement.
6. Provide an existing `workspace_id`.
7. Ensure the workspace has a usable configuration:
   - use its latest used configuration version,
   - pass a `configuration_version_id`, or
   - upload a configuration version before triggering the run.
8. Ensure the workspace is not blocked by another active run.
9. Ensure the workspace has the required execution setup:
   - VCS-backed workspace: valid VCS connection and repository.
   - Agent execution mode: configured agent pool and connected agent.

### Syntara Trigger Run fields

Required:

- `integration_id`
- `credential_id`
- `workspace_id`
- `mode`

Optional:

- `organization`
- `configuration_version_id`
- `target_resources`
- `replace_resources`
- `message`

Supported run modes:

- `plan-and-apply`
- `plan-only`
- `destroy`
- `refresh-only`
- `targeted-resource`
- `replace-resource`
- `allow-empty-apply`

### Typical run flow

```text
Upload Configuration Version
→ Trigger Run
→ Get Run Status / Wait for completion
→ Apply Run if confirmation is required
```

Control operations require the `run_id`:

- Apply only works when the run is confirmable.
- Discard, cancel, and force-cancel have their own run-state requirements.

## Workspace creation and VCS options

### Presets

| Goal | Syntara preset | Required fields | Result |
| --- | --- | --- | --- |
| Remote execution, no VCS | `remote_no_vcs` | None | `execution-mode: remote`; no VCS on create |
| Agent execution | `agent` | `agent_pool_id` | `execution-mode: agent`, `agent-pool-id` |
| OAuth-backed VCS | `remote_oauth_vcs` | `repository`, `oauth_token_id`; `branch` optional | `execution-mode: remote`, `vcs-repo` with OAuth token |
| GitHub App-backed VCS | `remote_github` | `repository`, `github_app_installation_id`; `branch` optional | `execution-mode: remote`, `vcs-repo` with GitHub App installation |

### VCS behavior

- To create a workspace without VCS, use `remote_no_vcs`; Syntara does not send `vcs-repo`.
- To remove VCS from an existing workspace, use **Update Workspace Settings** with `remote_no_vcs`. Syntara sends `vcs-repo: null`, which disconnects the repository.
- To add or replace OAuth VCS, use **Update Workspace Settings** with `remote_oauth_vcs`, `repository`, and `oauth_token_id`.
- To add or replace GitHub App VCS, use `remote_github`, or the dedicated **Link VCS** node. `Link VCS` patches only `vcs-repo` and preserves the current execution mode.
- If no preset is selected during an update, Syntara leaves the existing VCS configuration unchanged.
- If `agent` is selected, Syntara changes execution mode and agent pool but does not clear an existing VCS link.

### Field notes

- `repository` is the full VCS identifier, usually `owner/repository`.
- `oauth_token_id` is the TFE OAuth token resource ID, not the raw OAuth secret.
- `github_app_installation_id` is the installation ID, not the GitHub App ID.
- Do not set both OAuth and GitHub App fields; choose one VCS connection type.
- `execution_mode` is ignored when a preset is selected; the preset controls it.
- `project_id` is create-only. Use **Move Workspace to Project** for an existing workspace.

### Example OAuth configuration

```yaml
preset: remote_oauth_vcs
repository: my-org/my-repo
branch: main
oauth_token_id: ot-xxxxxxxx
```

### Example VCS removal

```yaml
workspace_id: ws-xxxxxxxx
preset: remote_no_vcs
```

## Validation

Use the following request to validate the TFE base URL, token, and organization access:

```bash
curl \
  -H "Authorization: Bearer $TFE_TOKEN" \
  -H "Accept: application/vnd.api+json" \
  "$TFE_BASE_URL/api/v2/organizations/$TFE_ORG"
```

## Implementation references

- `backend/src/syntara/terraform/presets.py`
- `backend/src/syntara/terraform/client.py`
- `backend/src/syntara/terraform/run_modes.py`
- `backend/src/syntara/workflows/workflow_engine/models/tfe_types.py`
- `backend/src/syntara/workflows/workflow_engine/activities/tfe_activities.py`
- `frontend/packages/syntara-ui/src/routes/builder/node-forms/TerraformNodeForm.tsx`
