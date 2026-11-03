/** Help popover body text for integration create/edit form fields. */

export const INTEGRATION_TYPE_HELP =
  'Registers a connection to an external service. MCP servers expose tools for agent workflows. LLM providers supply models. Automation platform integrations verify gateway connectivity.'

/** Shown on the disabled Execution plane infrastructure type option when one already exists. */
export const EXECUTION_PLANE_SINGLETON_HELP = 'Only one Execution plane infrastructure integration is supported.'

export const NAME_HELP =
  'A unique name that identifies this integration. Use a name that describes the service or environment, such as "Production MCP" or "Dev LLM Gateway."'

export const EXECUTION_PLANE_CONNECTION_NAME_HELP =
  'A short identifier used in pool names and the execution plane topology view.'

export const PROVIDER_TYPE_HELP =
  'Pre-configured defaults for known LLM providers. Some providers use a fixed API base URL; others require you to enter one. Custom always requires a base URL.'

export const API_URL_HELP =
  'Admin-managed connection endpoint. For MCP servers, the MCP server URL. For LLM providers, the API base URL used to reach the provider.'

export const EXECUTION_PLANE_API_ENDPOINT_HELP =
  'OpenShift/Kubernetes API server URL for this cluster, for example https://api.prod.example.com:6443. The execution plane connects outbound to this endpoint — no inbound firewall rules are required.'

export const AAP_URL_HELP =
  'Base URL of the automation platform gateway. Health checks call GET /api/gateway/v1/me/ to confirm reachability and that the management credential is valid.'

export const SCOPE_HELP =
  'When Global is enabled, this integration is available to workflows in every project. When Global is off, only the selected projects can use it.'

export const EXECUTION_PLANE_SCOPE_HELP =
  'Execution plane infrastructure integrations are always globally scoped and available to all projects.'

export const PROJECTS_HELP =
  'Projects that may use this integration. Resources belong to a single project; a project-scoped integration is only available when working in those projects.'

export const HEALTH_CHECK_CREDENTIAL_HELP =
  'Management credential used for health checks, connection testing, and resource discovery only. Workflow nodes use separate execution credentials configured per integration when a workflow runs.'

export const SERVICE_ACCOUNT_TOKEN_HELP =
  'Bearer token for a service account with access to the OpenShift cluster. Stored encrypted in the platform credential store.'
