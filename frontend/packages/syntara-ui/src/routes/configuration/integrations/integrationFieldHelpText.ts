/** Help popover body text for integration create/edit form fields. */

export const INTEGRATION_TYPE_HELP =
  'Registers a connection to an external service. MCP servers expose tools for agent workflows. LLM providers supply models. Automation platform integrations verify gateway connectivity.'

export const NAME_HELP =
  'A unique name that identifies this integration. Use a name that describes the service or environment, such as "Production MCP" or "Dev LLM Gateway."'

export const PROVIDER_TYPE_HELP =
  'Pre-configured defaults for known LLM providers. Some providers use a fixed API base URL; others require you to enter one. Custom always requires a base URL.'

export const API_URL_HELP =
  'Admin-managed connection endpoint. For MCP servers, the MCP server URL. For LLM providers, the API base URL used to reach the provider.'

export const AAP_URL_HELP =
  'Base URL of the automation platform gateway. Health checks call GET /api/gateway/v1/me/ to confirm reachability and that the management credential is valid.'

export const SCOPE_HELP =
  'When Global is enabled, this integration is available to workflows in every project. When Global is off, only the selected projects can use it.'

export const PROJECTS_HELP =
  'Projects that may use this integration. Resources belong to a single project; a project-scoped integration is only available when working in those projects.'

export const HEALTH_CHECK_CREDENTIAL_HELP =
  'Management credential used for health checks, connection testing, and resource discovery only. Workflow nodes use separate execution credentials configured per integration when a workflow runs.'
