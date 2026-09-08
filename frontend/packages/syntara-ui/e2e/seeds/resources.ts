/**
 * Resource seed helpers for E2E tests running against a real backend.
 *
 * Creates integrations, workflows, executions, credentials, and identity
 * providers via API. Falls back to mock credentials (password: "mock") when
 * SYNTARA_E2E_PASSWORD is not set.
 *
 * Each spec file should use a unique prefix (via buildUniqueName) to avoid
 * conflicts with parallel Playwright workers.
 */
import { type Page } from '../fixtures'
import { apiRequest, createCredentialViaApi, deleteCredentialViaApi, ensureProject, getAuthToken } from '../utils/api'

function seedError(fn: string, param: string, detail: string): Error {
  return new Error(`${fn}: ${detail} for ${param}`)
}

export type SeededIntegration = {
  id: string
  name: string
}

export async function createIntegrationViaApi(
  page: Page,
  options: {
    name: string
    token?: string
    /** Tools to seed with the MCP integration (enables agent tool selection in E2E). */
    discoveredTools?: Array<{ name: string; enabled?: boolean }>
  }
): Promise<SeededIntegration> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw seedError('createIntegrationViaApi', options.name, 'could not obtain auth token')

  const data: Record<string, unknown> = {
    name: options.name,
    integration_type: 'mcp_server',
    configuration: {
      integration_type: 'mcp_server',
      base_url: `https://example.com`,
    },
    scope: 'global',
  }
  if (options.discoveredTools?.length) {
    data.discovered_tools = options.discoveredTools.map((tool) => ({
      name: tool.name,
      enabled: tool.enabled ?? true,
    }))
  }

  const resp = await apiRequest(page, 'post', '/integrations', {
    token,
    data,
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '')
    throw seedError('createIntegrationViaApi', options.name, `HTTP ${resp.status()} ${body}`)
  }
  const integration = (await resp.json()) as { id: string; name: string }
  return { id: integration.id, name: integration.name }
}

export async function deleteIntegrationViaApi(page: Page, integrationId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    const token = await getAuthToken(page)
    if (token) {
      await apiRequest(page, 'delete', `/integrations/${integrationId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

export type SeededWorkflow = {
  id: string
  name: string
}

export async function createWorkflowViaApi(
  page: Page,
  options: { name: string; projectId?: string; token?: string }
): Promise<SeededWorkflow> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw seedError('createWorkflowViaApi', options.name, 'could not obtain auth token')

  const projectId = options.projectId ?? (await ensureProject(page))?.id
  if (!projectId) throw seedError('createWorkflowViaApi', options.name, 'could not ensure project')

  const data: Record<string, unknown> = {
    name: options.name,
    description: `E2E seed workflow: ${options.name}`,
    is_enabled: false,
    project_id: projectId,
    workflow_definition: {
      schema_version: '2.0.0',
      name: options.name,
      description: `E2E seed workflow: ${options.name}`,
      triggers: [
        {
          id: 'trigger_1',
          name: 'Manual trigger',
          type: 'manual_trigger',
          parameters: {},
        },
      ],
      nodes: [],
      edges: [],
    },
  }

  const resp = await apiRequest(page, 'post', '/workflows', { token, data })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '')
    throw seedError('createWorkflowViaApi', options.name, `HTTP ${resp.status()} ${body}`)
  }
  const workflow = (await resp.json()) as { id: string; name: string }
  return { id: workflow.id, name: workflow.name }
}

export async function deleteWorkflowViaApi(page: Page, workflowId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    const token = await getAuthToken(page)
    if (token) {
      await apiRequest(page, 'delete', `/workflows/${workflowId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

export type CreatedExecution = {
  id: string
  status: string
}

/**
 * Create an execution via POST /executions.
 *
 * Against the mock API, an optional `status` is honored so tests can seed
 * mixed statuses without changing the handler's default (`completed`).
 * The real backend ignores unknown fields and always starts executions as pending.
 */
export async function createExecutionViaApi(
  page: Page,
  options: { workflowId: string; status?: string; token?: string }
): Promise<CreatedExecution> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw seedError('createExecutionViaApi', options.workflowId, 'could not obtain auth token')

  const data: Record<string, unknown> = { workflow_id: options.workflowId }
  if (options.status) data.status = options.status

  const resp = await apiRequest(page, 'post', '/executions', { token, data })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '')
    throw seedError('createExecutionViaApi', options.workflowId, `HTTP ${resp.status()} ${body}`)
  }
  const body = (await resp.json()) as { id: string; status: string }
  return { id: body.id, status: body.status }
}

export type SeededIdentityProvider = {
  id: string
  name: string
}

export async function createIdentityProviderViaApi(
  page: Page,
  options: { name: string; token?: string }
): Promise<SeededIdentityProvider> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw seedError('createIdentityProviderViaApi', options.name, 'could not obtain auth token')

  const resp = await apiRequest(page, 'post', '/identity_providers', {
    token,
    data: {
      name: options.name,
      description: `E2E seed IdP: ${options.name}`,
      configuration: {
        provider_type: 'oidc',
        issuer_url: `https://${options.name}.example.com`,
        client_id: 'e2e-client-id',
        client_secret: 'e2e-client-secret',
        redirect_uri: `https://${options.name}.example.com/callback`,
      },
    },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '')
    throw seedError('createIdentityProviderViaApi', options.name, `HTTP ${resp.status()} ${body}`)
  }
  const idp = (await resp.json()) as { id: string; name: string }
  return { id: idp.id, name: idp.name }
}

export async function deleteIdentityProviderViaApi(page: Page, idpId: string): Promise<void> {
  if (page.isClosed()) return
  try {
    const token = await getAuthToken(page)
    if (token) {
      await apiRequest(page, 'delete', `/identity_providers/${idpId}`, { token })
    }
  } catch {
    // Best-effort cleanup
  }
}

/**
 * Create a credential appropriate for a given integration type.
 *
 * Looks up the correct credential type by name via the API (not hardcoded IDs),
 * then creates a credential with sensible defaults. The optional `apiKey` allows
 * callers to supply real secrets (e.g. OpenRouter API key for LLM tests).
 */
export async function createCredentialForIntegrationType(
  page: Page,
  options: {
    name: string
    integrationType: 'mcp_server' | 'llm_provider' | 'aap_gateway'
    apiKey?: string
    token?: string
  }
): Promise<SeededCredential> {
  const token = options.token ?? (await getAuthToken(page))
  if (!token) throw seedError('createCredentialForIntegrationType', options.name, 'could not obtain auth token')

  const project = await ensureProject(page)
  if (!project) throw seedError('createCredentialForIntegrationType', options.name, 'could not obtain project')

  const typesResp = await apiRequest(page, 'get', '/credential_types', { token })
  if (!typesResp.ok()) {
    const typesBody = await typesResp.text().catch(() => '')
    throw seedError(
      'createCredentialForIntegrationType',
      options.name,
      `credential types HTTP ${typesResp.status()} ${typesBody}`
    )
  }
  const types = (await typesResp.json()) as { resources?: Array<{ id: string; name: string }> }
  if (!types.resources?.length) {
    throw seedError('createCredentialForIntegrationType', options.name, 'no credential types returned')
  }

  const typeNameMap: Record<string, string> = {
    mcp_server: 'HTTP Bearer Token',
    llm_provider: 'LLM Provider',
    aap_gateway: 'Ansible Automation Platform',
  }
  const targetTypeName = typeNameMap[options.integrationType]
  const credType = types.resources.find((t) => t.name === targetTypeName)
  if (!credType) {
    throw seedError('createCredentialForIntegrationType', options.name, `credential type "${targetTypeName}" not found`)
  }

  const inputsMap: Record<string, Record<string, string>> = {
    mcp_server: { token: options.apiKey ?? 'e2e-bearer-token' },
    llm_provider: { api_key: options.apiKey ?? 'sk-e2e-test-key' },
    aap_gateway: { oauth_token: options.apiKey ?? 'e2e-aap-oauth-token' },
  }

  const createResp = await apiRequest(page, 'post', '/credentials', {
    token,
    data: {
      name: options.name,
      credential_type_id: credType.id,
      project_id: project.id,
      inputs: inputsMap[options.integrationType],
    },
  })
  if (!createResp.ok()) {
    const createBody = await createResp.text().catch(() => '')
    throw seedError('createCredentialForIntegrationType', options.name, `HTTP ${createResp.status()} ${createBody}`)
  }
  const cred = (await createResp.json()) as { id: string; name: string }
  return { id: cred.id, name: cred.name }
}

/** Re-export credential helpers from utils/api for convenience. */
export type SeededCredential = {
  id: string
  name: string
}

export async function createCredentialSeed(
  page: Page,
  options: { name: string; projectId?: string; token?: string }
): Promise<SeededCredential> {
  const projectId = options.projectId ?? (await ensureProject(page))?.id
  if (!projectId) throw seedError('createCredentialSeed', options.name, 'could not ensure project')

  const id = await createCredentialViaApi(page, { name: options.name, projectId })
  if (!id) throw seedError('createCredentialSeed', options.name, 'createCredentialViaApi returned no id')
  return { id, name: options.name }
}

export async function patchIntegrationScopeViaApi(
  page: Page,
  integrationId: string,
  scope: 'global' | 'project',
  token?: string
): Promise<boolean> {
  try {
    const t = token ?? (await getAuthToken(page))
    if (!t) return false
    const resp = await apiRequest(page, 'patch', `/integrations/${integrationId}`, {
      token: t,
      data: { scope },
    })
    return resp.ok()
  } catch {
    return false
  }
}

export async function assignIntegrationProjectViaApi(
  page: Page,
  integrationId: string,
  projectId: string,
  token?: string
): Promise<boolean> {
  try {
    const t = token ?? (await getAuthToken(page))
    if (!t) return false
    const resp = await apiRequest(page, 'post', `/integrations/${integrationId}/projects/${projectId}`, {
      token: t,
    })
    return resp.ok()
  } catch {
    return false
  }
}

export { deleteCredentialViaApi }
