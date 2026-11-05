import { createFieldHelp } from '../../../components/createFieldHelp'

import * as T from './integrationFieldHelpText'

/** Pre-built labelHelp elements for integration forms. */
export const integrationHelp = {
  integrationType: createFieldHelp('Integration type', T.INTEGRATION_TYPE_HELP),
  name: createFieldHelp('Name', T.NAME_HELP),
  /** MCP / non-LLM create+edit use this visible label; body matches Name help. */
  serverName: createFieldHelp('Server name / ID', T.NAME_HELP),
  /** Form label is Connection name for execution plane infrastructure. */
  executionPlaneConnectionName: createFieldHelp('Connection name', T.EXECUTION_PLANE_CONNECTION_NAME_HELP),
  providerType: createFieldHelp('Provider type', T.PROVIDER_TYPE_HELP),
  /** Form label is API URL (covers plan Base URL copy). */
  apiUrl: createFieldHelp('API URL', T.API_URL_HELP),
  /** Same form label for AAP integrations; body is gateway-specific. */
  aapUrl: createFieldHelp('API URL', T.AAP_URL_HELP),
  /** Form label is API endpoint for execution plane infrastructure. */
  executionPlaneApiEndpoint: createFieldHelp('API endpoint', T.EXECUTION_PLANE_API_ENDPOINT_HELP),
  scope: createFieldHelp('Scope', T.SCOPE_HELP),
  projects: createFieldHelp('Projects', T.PROJECTS_HELP),
  healthCheckCredential: createFieldHelp('Health check credential', T.HEALTH_CHECK_CREDENTIAL_HELP),
  serviceAccountToken: createFieldHelp('Service account token', T.SERVICE_ACCOUNT_TOKEN_HELP),
} as const
