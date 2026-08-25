import { http, HttpResponse } from 'msw'
import { v4 as uuidv4 } from 'uuid'
import { mockDate } from './resources/mockDates'
import { createMockJwt } from './mockJwt'
import type * as ApprovalsAPI from '@syntara/contracts/src/approvals-api.js'
import type * as ExecutionsAPI from '@syntara/contracts/src/executions-api.js'
import type * as ToolManagerAPI from '@syntara/contracts/src/tool-manager.js'
import type * as WorkflowAPI from '@syntara/contracts/src/workflow-api.js'
import type { Approval, Tool, WorkflowWithVersion, WorkflowsResponse } from '@syntara/contracts'
import {
  ExecutionStatusEnum,
  IntegrationStatusEnum,
  IntegrationTypeEnum,
  WorkflowVersionStatusEnum,
} from '@syntara/contracts'
import { credentials, credentialTypes, credentialWorkflows } from './resources/credentials'
import { integrations } from './resources/integrations'
import { models } from './resources/models'
import { workflows } from './resources/workflows'
import { tools } from './resources/tools'
import { executions } from './resources/executions'
import { getExecutionDetail } from './resources/executionDetails'
import { activityExecutions } from './resources/activityExecutions'
import { approvals } from './resources/approvals'
import { settings, settingsCategories } from './resources/settings'
import { revocationState } from './resources/revocation'
import { identityProviders, type IdentityProvider } from './resources/identityProviders'
import { validateGroupJmespathExpression } from './utils/jmespathValidation'
import { users, userIdentities, type UserRead, type UserIdentityRead } from './resources/users'
import { groups, userGroupMemberships, type GroupRead } from './resources/groups'
import {
  mockProjects,
  mockPolicies,
  mockRoles,
  mockProjectRoleAssignments,
  mockProjectGroupRoleAssignments,
  mockGroupRoleAssignments,
  mockUserRoleAssignments,
  mockServiceAccountRoleAssignments,
  mockUsers,
  mockGroups,
  getUserName,
  getGroupName,
  getRoleName,
  mockServiceAccounts,
  mockServiceAccountCredentials,
} from './resources/access'

import {
  organizations,
  jobTemplates,
  jobTemplateDetails,
  workflowTemplates,
  workflowTemplateDetails,
  inventories,
  executionEnvironments,
  aapCredentials,
  instanceGroups,
} from './resources/aap'

const MAX_CREDENTIALS_PER_SA = 10

// Define response types based on API contract
type ToolsResponse = ToolManagerAPI.paths['/tools']['get']['responses']['200']['content']['application/json']
type ApprovalsResponse = ApprovalsAPI.paths['/approvals']['get']['responses']['200']['content']['application/json']
type CreateWorkflowBody = WorkflowAPI.paths['/workflows']['post']['requestBody']['content']['application/json']
type UpdateWorkflowBody =
  WorkflowAPI.paths['/workflows/{workflow_id}']['patch']['requestBody']['content']['application/json']

type MutableWorkflowWithVersion = { -readonly [K in keyof WorkflowWithVersion]: WorkflowWithVersion[K] }

type MockVersionRecord = {
  id: string
  workflow_id: string
  version: number
  schema_version: string
  workflow_definition: unknown
  change_description: string
  status: string
  name: string | null
  created_by: string
  created_by_username: string
  created_at: string
  updated_at: string
  deleted_at: null
  deleted_by: null
}

const MOCK_VERSION_CREATED_BY = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
const MOCK_VERSION_CREATED_BY_USERNAME = 'demo'

/** Creates a 409 WORKFLOW_VERSION_CONFLICT response for save/publish mock handlers. */
function workflowVersionConflictResponse(
  workflowId: string,
  currentVersion: number,
  expectedVersion: number,
  instance: string,
  updatedAt: string
) {
  return HttpResponse.json(
    {
      type: 'https://api.example.com/errors/resource-conflict',
      title: 'Version Conflict',
      detail: 'A newer version of this workflow has been saved by another user',
      code: 'WORKFLOW_VERSION_CONFLICT',
      retryable: false,
      instance,
      current_version: currentVersion,
      current_version_name: null,
      expected_version: expectedVersion,
      expected_version_name: null,
      expected_created_at: updatedAt,
      created_by_username: 'demo',
      created_at: updatedAt,
    },
    { status: 409 }
  )
}

const workflowVersionStore = new Map<string, MockVersionRecord[]>()

function getOrCreateVersionStore(workflowId: string, workflow: WorkflowWithVersion): MockVersionRecord[] {
  if (!workflowVersionStore.has(workflowId)) {
    const now = mockDate.daysAgo1
    const versionId = (workflow.version as Record<string, unknown> | undefined)?.id as string | undefined
    const id = versionId ?? uuidv4()
    if (workflow.version && !versionId) {
      ;(workflow.version as Record<string, unknown>).id = id
    }
    workflowVersionStore.set(workflowId, [
      {
        id,
        workflow_id: workflowId,
        version: 1,
        schema_version: workflow.version?.schema_version ?? '2.0.0',
        workflow_definition: workflow.version?.workflow_definition,
        change_description: 'Initial version',
        status: 'draft',
        name: null,
        created_by: MOCK_VERSION_CREATED_BY,
        created_by_username: MOCK_VERSION_CREATED_BY_USERNAME,
        created_at: now,
        updated_at: now,
        deleted_at: null,
        deleted_by: null,
      },
    ])
  }
  return workflowVersionStore.get(workflowId)!
}

/** Mock seed data may use camelCase timestamps; API uses snake_case */
type ApprovalTimestamps = Approval & { createdAt?: string; updatedAt?: string }

function approvalCreatedAt(a: Approval): string | undefined {
  const row = a as ApprovalTimestamps
  return row.created_at ?? row.createdAt
}

function getUsernameFromRequest(request: Request): string {
  const auth = request.headers.get('Authorization') ?? ''

  // Try old-style mock token format first (backwards compatibility)
  const oldStyleMatch = /^Bearer .*mock-token-(.+)$/.exec(auth)
  if (oldStyleMatch) return oldStyleMatch[1]

  // Parse JWT token to extract username from preferred_username claim
  const jwtMatch = /^Bearer (.+)$/.exec(auth)
  if (jwtMatch) {
    try {
      const token = jwtMatch[1]
      const payload = token.split('.')[1]
      if (payload) {
        const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
        const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
        const decoded = JSON.parse(atob(padded)) as { preferred_username?: string }
        return decoded.preferred_username ?? 'admin'
      }
    } catch {
      // Fall through to default
    }
  }

  return 'admin'
}

const randomCharacters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
const randomCharactersLowercase = 'abcdefghijklmnopqrstuvwxyz0123456789'

function randomIntBelow(max: number): number {
  if (max <= 0) return 0
  const limit = Math.floor(0x100000000 / max) * max
  let val: number
  do {
    const buf = new Uint32Array(1)
    crypto.getRandomValues(buf)
    val = buf[0]!
  } while (val >= limit)
  return val % max
}

function base64EncodeJson(payload: unknown): string {
  const json = JSON.stringify(payload)
  const bytes = new TextEncoder().encode(json)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary)
}

function base64DecodeJson(cursor: string): unknown {
  const binary = atob(cursor)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const json = new TextDecoder().decode(bytes)
  return JSON.parse(json)
}

export function randomString(length: number, base = randomCharacters.length, options = { isLowercase: false }): string {
  // We'll use the default for options if it's not provided, which includes isLowercase set to false
  const randomChars = options.isLowercase ? randomCharactersLowercase : randomCharacters
  if (base > randomChars.length || base <= 0) {
    base = randomChars.length
  }
  let text = ''
  for (let i = 0; i < length; i++) {
    const index = randomIntBelow(base)
    text += randomChars.charAt(index)
  }
  return text
}

// Pagination helpers
function parseCursor(cursor: string | null): number {
  if (!cursor) return 0
  try {
    const cursorData = base64DecodeJson(cursor) as { index?: number }
    return cursorData.index ?? 0
  } catch {
    return 0
  }
}

function generateCursors(startIndex: number, limit: number, totalLength: number) {
  const hasNext = startIndex + limit < totalLength
  const hasPrev = startIndex > 0
  const next = hasNext ? base64EncodeJson({ index: startIndex + limit }) : null
  const prev = hasPrev ? base64EncodeJson({ index: Math.max(0, startIndex - limit) }) : null
  return { next, prev }
}

function paginate<T>(items: T[], cursor: string | null, limit: number, includeTotal: boolean) {
  const startIndex = parseCursor(cursor)
  const paginated = items.slice(startIndex, startIndex + limit)
  const { next, prev } = generateCursors(startIndex, limit, items.length)
  return {
    resources: paginated,
    next,
    prev,
    total: includeTotal ? items.length : null,
  }
}

/** Redact secret fields in a credential's inputs to match real API behavior */
function redactCredential(credential: (typeof credentials)[number]) {
  const credType = credentialTypes.find((t) => t.id === credential.credential_type_id)
  const fields = ((credType?.inputs as Record<string, unknown>)?.fields as { id: string; secret?: boolean }[]) ?? []
  const redactedInputs = { ...credential.inputs }
  for (const field of fields) {
    if (field.secret && field.id in redactedInputs) {
      ;(redactedInputs as Record<string, unknown>)[field.id] = '$encrypted$'
    }
  }
  const integration_count = integrations.filter((i) => i.management_credential_id === credential.id).length
  return { ...credential, inputs: redactedInputs, integration_count, workflow_count: 0 }
}

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Validates credential_id query parameter format.
 * Returns error response if invalid UUID, null if valid or not provided.
 */
function validateCredentialId(url: URL): ReturnType<typeof HttpResponse.json> | null {
  const credentialId = url.searchParams.get('credential_id')
  if (credentialId && !UUID_REGEX.test(credentialId)) {
    return HttpResponse.json(
      {
        type: 'https://api.example.com/errors/validation-error',
        title: 'Validation Error',
        detail: 'credential_id must be a valid UUID',
        code: 'VALIDATION_ERROR',
      },
      { status: 422 }
    )
  }
  return null
}

function filterByPolicyName<T extends { policies: string[] }>(items: T[], url: URL): T[] {
  const term = url.searchParams.get('policy_name[contains]')
  if (!term) return items
  const lower = term.toLowerCase()
  return items.filter((r) => r.policies.some((p) => p.toLowerCase().includes(lower)))
}

function createExecutionNotFoundResponse(executionId: string, subPath?: string) {
  const instance = subPath ? `/api/v1/executions/${executionId}/${subPath}` : `/api/v1/executions/${executionId}`
  return HttpResponse.json(
    {
      type: 'https://api.example.com/errors/execution-not-found',
      title: 'Execution Not Found',
      detail: 'Execution not found',
      code: 'EXECUTION_NOT_FOUND',
      retryable: false,
      instance,
    },
    { status: 404 }
  )
}

/** In-memory file store for mock upload → download round-trips (retains original filenames). */
const mockUploadedFiles = new Map<string, { filename: string; content: ArrayBuffer; mime_type: string }>()
const knownFileMetadata: Record<string, { filename: string; size_bytes: number; mime_type: string }> = {
  'a1b2c3d4-0001-0001-0001-000000000001': {
    filename: 'server-config.txt',
    size_bytes: 2048,
    mime_type: 'text/plain',
  },
  'a1b2c3d4-0001-0001-0001-000000000002': {
    filename: 'api-docs.md',
    size_bytes: 15360,
    mime_type: 'text/markdown',
  },
  'a1b2c3d4-0001-0001-0001-000000000003': {
    filename: 'deploy-runbook.txt',
    size_bytes: 4096,
    mime_type: 'text/plain',
  },
}

export const handlers = [
  http.get('/api/v1/tools', ({ request }) => {
    const url = new URL(request.url)
    const statusFilter = url.searchParams.get('status')
    const enabledParam = url.searchParams.get('enabled')
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'

    let filtered = tools
    if (statusFilter) filtered = filtered.filter((t) => t.status === statusFilter)
    if (enabledParam !== null) {
      const enabled = enabledParam === 'true'
      filtered = filtered.filter((t) => t.enabled === enabled)
    }
    const body: ToolsResponse = paginate(filtered, cursor, limit, includeTotal)
    return HttpResponse.json(body)
  }),

  http.get('/api/v1/integrations/:integration_id/tools', ({ request, params }) => {
    const integrationId = params.integration_id as string
    const integration = integrations.find((i) => i.id === integrationId)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }

    const url = new URL(request.url)
    const statusFilter = url.searchParams.get('status')
    const enabledParam = url.searchParams.get('enabled')
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'

    let filtered = tools.filter((t) => t.integration_id === integrationId)
    if (statusFilter) filtered = filtered.filter((t) => t.status === statusFilter)
    if (enabledParam !== null) {
      const enabled = enabledParam === 'true'
      filtered = filtered.filter((t) => t.enabled === enabled)
    }
    const body: ToolsResponse = paginate(filtered, cursor, limit, includeTotal)
    return HttpResponse.json(body)
  }),

  http.patch('/api/v1/integrations/:integration_id/tools/bulk_update', async (req) => {
    const integrationId = req.params.integration_id as string
    const integration = integrations.find((i) => i.id === integrationId)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }

    const reqData = (await req.request.json()) as { tool_ids?: string[]; enabled?: boolean }
    if (reqData?.tool_ids && reqData.tool_ids.length > 0 && typeof reqData.enabled === 'boolean') {
      const { enabled } = reqData
      tools.forEach((tool) => {
        if (reqData.tool_ids?.includes(tool.id)) tool.enabled = enabled
      })
    }
    return HttpResponse.json({}, { status: 201 })
  }),

  // ── Integrations ──────────────────────────────────────────────────────────

  http.get('/api/v1/integrations', ({ request }) => {
    const url = new URL(request.url)
    const nameContains = url.searchParams.get('name[contains]')
    const integrationType = url.searchParams.get('integration_type')
    const validationStatus = url.searchParams.get('validation_status')
    const enabledParam = url.searchParams.get('enabled')
    const sort = url.searchParams.get('sort')
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '20', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'

    let filtered = [...integrations]
    if (nameContains) {
      const lower = nameContains.toLowerCase()
      filtered = filtered.filter((i) => (i.name ?? '').toLowerCase().includes(lower))
    }
    if (integrationType) {
      filtered = filtered.filter((i) => i.integration_type === integrationType)
    }
    if (validationStatus) {
      filtered = filtered.filter((i) => i.validation_status === validationStatus)
    }
    if (enabledParam !== null) {
      const enabled = enabledParam === 'true'
      filtered = filtered.filter((i) => i.enabled === enabled)
    }
    const managementCredentialId = url.searchParams.get('management_credential_id')
    if (managementCredentialId) {
      filtered = filtered.filter((i) => i.management_credential_id === managementCredentialId)
    }
    const projectId = url.searchParams.get('project_id')
    if (projectId) {
      filtered = filtered.filter((i) => i.scope === 'global' || (i.project_ids && i.project_ids.includes(projectId)))
    }

    if (sort) {
      const isDesc = sort.startsWith('-')
      const field = isDesc ? sort.slice(1) : sort
      filtered.sort((a, b) => {
        let aVal = ''
        let bVal = ''
        switch (field) {
          case 'name':
            aVal = a.name ?? ''
            bVal = b.name ?? ''
            break
          case 'validation_status':
            aVal = a.validation_status ?? ''
            bVal = b.validation_status ?? ''
            break
          case 'integration_type':
            aVal = a.integration_type ?? ''
            bVal = b.integration_type ?? ''
            break
          case 'enabled':
            aVal = a.enabled ? '1' : '0'
            bVal = b.enabled ? '1' : '0'
            break
          case 'last_validated_at':
            aVal = a.last_validated_at ?? ''
            bVal = b.last_validated_at ?? ''
            break
          case 'created_at':
            aVal = a.created_at ?? ''
            bVal = b.created_at ?? ''
            break
          case 'updated_at':
            aVal = a.updated_at ?? ''
            bVal = b.updated_at ?? ''
            break
          default:
            aVal = a.name ?? ''
            bVal = b.name ?? ''
        }
        const cmp = aVal.localeCompare(bVal)
        return isDesc ? -cmp : cmp
      })
    }

    return HttpResponse.json(paginate(filtered, cursor, limit, includeTotal))
  }),

  http.get('/api/v1/integrations/:integration_id', ({ params }) => {
    const integration = integrations.find((i) => i.id === params.integration_id)
    if (!integration) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/not-found',
          title: 'Not Found',
          detail: `Integration ${params.integration_id as string} not found`,
          code: 'NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json(integration)
  }),

  http.post('/api/v1/integrations', async (req) => {
    const body = (await req.request.json()) as Record<string, unknown>
    const now = mockDate.now
    const integrationId = uuidv4()

    const discoveredTools = body.discovered_tools as
      | Array<{ name: string; description?: string; enabled?: boolean }>
      | undefined
    let enabledToolCount = 0
    if (discoveredTools && discoveredTools.length > 0) {
      for (const dt of discoveredTools) {
        const enabled = dt.enabled !== false
        if (enabled) enabledToolCount++
        tools.push({
          id: uuidv4(),
          name: dt.name,
          namespaced_name: dt.name,
          integration_id: integrationId,
          enabled,
          parameters: [],
          created_at: now,
          updated_at: now,
        } as Tool)
      }
    }

    const discoveredModels = body.discovered_models as
      | Array<{ model_id: string; name: string; description?: string; enabled?: boolean; is_default?: boolean }>
      | undefined
    let enabledModelCount = 0
    if (discoveredModels && discoveredModels.length > 0) {
      for (const dm of discoveredModels) {
        const enabled = dm.enabled !== false
        if (enabled) enabledModelCount++
        models.push({
          id: uuidv4(),
          integration_id: integrationId,
          model_id: dm.model_id,
          name: dm.name,
          description: dm.description ?? null,
          enabled,
          is_default: dm.is_default ?? false,
          last_refreshed_at: now,
          created_at: now,
          updated_at: now,
        })
      }
    }

    const newIntegration = {
      id: integrationId,
      name: body.name ?? '',
      description: body.description ?? null,
      integration_type: body.integration_type ?? IntegrationTypeEnum.MCP_SERVER,
      enabled: true,
      validation_status: IntegrationStatusEnum.UNKNOWN,
      scope: body.scope ?? 'global',
      configuration: body.configuration ?? { integration_type: IntegrationTypeEnum.MCP_SERVER, base_url: '' },
      management_credential_id: (body.management_credential_id as string) ?? null,
      last_validated_at: null,
      validation_error: null,
      refresh_status: null,
      last_refreshed_at: null,
      refresh_error: null,
      total_tool_count: discoveredTools?.length ?? 0,
      enabled_tool_count: enabledToolCount,
      total_model_count: discoveredModels?.length ?? 0,
      enabled_model_count: enabledModelCount,
      created_at: now,
      updated_at: now,
      created_by: 'user-1',
      updated_by: null,
      deleted_at: null,
      deleted_by: null,
      labels: {},
    }
    integrations.push(newIntegration as (typeof integrations)[number])
    return HttpResponse.json(newIntegration, { status: 201 })
  }),

  http.patch('/api/v1/integrations/:integration_id', async (req) => {
    const integration = integrations.find((i) => i.id === req.params.integration_id)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const body = (await req.request.json()) as Record<string, unknown>
    Object.assign(integration, body, { updated_at: mockDate.now })
    return HttpResponse.json(integration)
  }),

  http.delete('/api/v1/integrations/:integration_id', ({ params }) => {
    const index = integrations.findIndex((i) => i.id === params.integration_id)
    if (index === -1) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    integrations.splice(index, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/v1/integrations/:integration_id/projects', ({ params }) => {
    const integration = integrations.find((i) => i.id === params.integration_id)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const projectIds = integration.project_ids ?? []
    const resources = projectIds.map((pid) => {
      const project = mockProjects.find((p) => p.id === pid)
      return {
        project_id: pid,
        project_name: project?.name ?? 'Unknown Project',
        created_at: mockDate.weekAgo,
      }
    })
    return HttpResponse.json({ resources, next: null, prev: null, total: resources.length })
  }),

  http.post('/api/v1/integrations/:integration_id/projects/:project_id', ({ params }) => {
    const integration = integrations.find((i) => i.id === params.integration_id)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const projectId = params.project_id as string
    const project = mockProjects.find((p) => p.id === projectId)
    if (!integration.project_ids) integration.project_ids = []
    if (!integration.project_ids.includes(projectId)) {
      integration.project_ids.push(projectId)
    }
    return HttpResponse.json(
      {
        project_id: projectId,
        project_name: project?.name ?? 'Unknown Project',
        created_at: mockDate.now,
      },
      { status: 201 }
    )
  }),

  http.delete('/api/v1/integrations/:integration_id/projects/:project_id', ({ params }) => {
    const integration = integrations.find((i) => i.id === params.integration_id)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const projectId = params.project_id as string
    if (integration.project_ids) {
      integration.project_ids = integration.project_ids.filter((id) => id !== projectId)
    }
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/v1/integrations/discover', async (req) => {
    const body = (await req.request.json()) as { integration_type?: string }
    if (body.integration_type === IntegrationTypeEnum.LLM_PROVIDER) {
      return HttpResponse.json({
        success: true,
        checked_at: mockDate.now,
        error: null,
        discovered_models: [
          { id: 'granite-3.3-8b-instruct', name: 'granite-3.3-8b-instruct', description: '128k context' },
          { id: 'granite-3.3-2b-instruct', name: 'granite-3.3-2b-instruct', description: '128k context' },
          { id: 'granite-code-8b', name: 'granite-code-8b', description: '8k context' },
        ],
      })
    }
    return HttpResponse.json({
      success: true,
      checked_at: mockDate.now,
      error: null,
      discovered_tools: [
        { name: 'get_repo', description: 'Get repository details', parameters: [] },
        { name: 'create_pr', description: 'Create a pull request', parameters: [] },
        { name: 'list_issues', description: 'List repository issues', parameters: [] },
      ],
    })
  }),

  http.post('/api/v1/integrations/:integration_id/validate', ({ params }) => {
    const integration = integrations.find((i) => i.id === params.integration_id)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    integration.validation_status = IntegrationStatusEnum.AVAILABLE
    integration.last_validated_at = mockDate.now
    integration.validation_error = null
    return HttpResponse.json({ success: true, checked_at: mockDate.now, error: null })
  }),

  http.post('/api/v1/integrations/:integration_id/refresh', ({ params }) => {
    const integration = integrations.find((i) => i.id === params.integration_id)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    integration.refresh_status = IntegrationStatusEnum.AVAILABLE
    integration.last_refreshed_at = mockDate.now
    integration.refresh_error = null
    return HttpResponse.json({
      synced_count: 0,
      updated_count: 0,
      missing_count: 0,
      refreshed_at: mockDate.now,
    })
  }),

  http.get('/api/v1/integrations/:integration_id/models', ({ request, params }) => {
    const integrationId = params.integration_id as string
    const integration = integrations.find((i) => i.id === integrationId)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }

    const url = new URL(request.url)
    const nameContains = url.searchParams.get('name[contains]')
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'

    let filtered = models.filter((m) => m.integration_id === integrationId)
    if (nameContains) {
      const lower = nameContains.toLowerCase()
      filtered = filtered.filter((m) => m.name.toLowerCase().includes(lower))
    }
    const enabledParam = url.searchParams.get('enabled')
    if (enabledParam !== null) {
      const enabledValue = enabledParam === 'true'
      filtered = filtered.filter((m) => m.enabled === enabledValue)
    }

    return HttpResponse.json(paginate(filtered, cursor, limit, includeTotal))
  }),

  http.get('/api/v1/integrations/:integration_id/models/:model_id', ({ params }) => {
    const integrationId = params.integration_id as string
    const modelId = params.model_id as string
    const integration = integrations.find((i) => i.id === integrationId)
    if (!integration) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const model = models.find((m) => m.id === modelId && m.integration_id === integrationId)
    if (!model) {
      return HttpResponse.json(
        { type: 'https://api.example.com/errors/not-found', title: 'Not Found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    return HttpResponse.json(model)
  }),

  http.patch('/api/v1/integrations/:integration_id/models/:model_id', async (req) => {
    const integrationId = req.params.integration_id as string
    const modelId = req.params.model_id as string
    const integration = integrations.find((i) => i.id === integrationId)
    if (!integration) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/not-found',
          title: 'Not Found',
          detail: `Integration ${integrationId} not found`,
          code: 'INTEGRATION_NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }
    const index = models.findIndex((m) => m.id === modelId && m.integration_id === integrationId)
    if (index === -1) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/not-found',
          title: 'Not Found',
          detail: `Model ${modelId} not found in integration ${integrationId}`,
          code: 'MODEL_NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }

    const body = (await req.request.json()) as { enabled?: boolean | null; is_default?: boolean | null }

    // When setting is_default to true, clear is_default on all other models for the same integration
    if (body.is_default === true) {
      for (const m of models) {
        if (m.integration_id === integrationId && m.id !== modelId) {
          m.is_default = false
        }
      }
    }

    const model = models[index]
    if (body.enabled !== undefined && body.enabled !== null) model.enabled = body.enabled
    if (body.is_default !== undefined && body.is_default !== null) model.is_default = body.is_default
    model.updated_at = mockDate.now

    // Update counts on the integration (reuses `integration` from the guard above)
    const integrationModels = models.filter((m) => m.integration_id === integrationId)
    integration.enabled_model_count = integrationModels.filter((m) => m.enabled).length

    return HttpResponse.json(model)
  }),

  http.patch('/api/v1/integrations/:integration_id/models/bulk_update', async (req) => {
    const integrationId = req.params.integration_id as string
    const integration = integrations.find((i) => i.id === integrationId)
    if (!integration) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/not-found',
          title: 'Not Found',
          detail: `Integration ${integrationId} not found`,
          code: 'NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }

    const body = (await req.request.json()) as { model_ids: string[]; enabled: boolean }
    if (!body.model_ids || body.model_ids.length === 0) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/validation-error',
          title: 'Validation Error',
          detail: 'model_ids must contain at least one ID',
          code: 'VALIDATION_ERROR',
          retryable: false,
        },
        { status: 422 }
      )
    }
    let updatedCount = 0
    let skippedCount = 0

    for (const id of body.model_ids) {
      const model = models.find((m) => m.id === id && m.integration_id === integrationId)
      if (model) {
        model.enabled = body.enabled
        model.updated_at = mockDate.now
        updatedCount++
      } else {
        skippedCount++
      }
    }

    // Update counts on the integration
    const integrationModels = models.filter((m) => m.integration_id === integrationId)
    integration.enabled_model_count = integrationModels.filter((m) => m.enabled).length

    return HttpResponse.json({ updated_count: updatedCount, skipped_count: skippedCount })
  }),

  http.get('/api/v1/workflows', ({ request }) => {
    const url = new URL(request.url)
    const nameStartsWith = url.searchParams.get('name[starts_with]')
    const nameContains = url.searchParams.get('name[contains]')
    const isEnabled = url.searchParams.get('is_enabled')
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'

    const projectId = url.searchParams.get('project_id')

    let resources = workflows

    // Apply project filter
    if (projectId) {
      resources = resources.filter((w) => w.project_id === projectId)
    }

    // Apply name filters
    if (nameStartsWith) {
      const prefix = nameStartsWith.toLowerCase()
      resources = resources.filter((w) => (w.name ?? '').toLowerCase().startsWith(prefix))
    }
    if (nameContains) {
      const searchTerm = nameContains.toLowerCase()
      resources = resources.filter((w) => (w.name ?? '').toLowerCase().includes(searchTerm))
    }

    // Apply is_enabled filter
    if (isEnabled !== null) {
      const enabled = isEnabled === 'true'
      resources = resources.filter((w) => w.is_enabled === enabled)
    }

    // Paginate results
    const body: WorkflowsResponse = paginate(resources, cursor, limit, includeTotal)
    return HttpResponse.json(body)
  }),

  http.get('/api/v1/projects/:project_id/workflows', ({ request, params }) => {
    const projectId = String(params.project_id)
    const url = new URL(request.url)
    const nameStartsWith = url.searchParams.get('name[starts_with]')
    const nameContains = url.searchParams.get('name[contains]')
    const isEnabled = url.searchParams.get('is_enabled')
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'

    let resources = workflows.filter((w) => w.project_id === projectId)

    if (nameStartsWith) {
      const prefix = nameStartsWith.toLowerCase()
      resources = resources.filter((w) => (w.name ?? '').toLowerCase().startsWith(prefix))
    }
    if (nameContains) {
      const searchTerm = nameContains.toLowerCase()
      resources = resources.filter((w) => (w.name ?? '').toLowerCase().includes(searchTerm))
    }

    if (isEnabled !== null) {
      const enabled = isEnabled === 'true'
      resources = resources.filter((w) => w.is_enabled === enabled)
    }

    const body: WorkflowsResponse = paginate(resources, cursor, limit, includeTotal)
    return HttpResponse.json(body)
  }),
  http.post('/api/v1/workflows', async (req) => {
    const body = (await req.request.json()) as CreateWorkflowBody & {
      labels?: Record<string, string>
      project_id?: string
    }
    const now = new Date().toISOString()
    const workflowId = uuidv4()
    const labelRecord = body.labels ?? {}
    const projectId = typeof body.project_id === 'string' && body.project_id.length > 0 ? body.project_id : 'p-001'
    const versionId = uuidv4()
    const createdWorkflow: WorkflowWithVersion & { project_id: string } = {
      id: workflowId,
      name: body.name ?? 'new-workflow',
      description: body.description ?? body.name ?? 'New workflow',
      labels: labelRecord,
      is_enabled: body.is_enabled ?? false,
      published_version_id: null,
      published_version_number: null,
      current_version: 1,
      created_at: now,
      updated_at: now,
      created_by: 'user-1',
      updated_by: null,
      project_id: projectId,
      version: {
        id: versionId,
        version: 1,
        schema_version: body.workflow_definition?.schema_version ?? '2.0.0',
        workflow_definition: body.workflow_definition,
        created_by: 'user-1',
        created_at: now,
        change_description: 'Initial version',
        status: WorkflowVersionStatusEnum.DRAFT,
      },
    }

    workflows.push(createdWorkflow)
    return HttpResponse.json(createdWorkflow, { status: 201 })
  }),

  http.post('/api/v1/workflows/validate', async (req) => {
    const body = (await req.request.json()) as {
      workflow_definition?: {
        nodes?: Array<{ id?: string; type?: string; parameters?: Record<string, unknown> }>
        edges?: unknown[]
        triggers?: unknown[]
      }
    }
    const definition = body.workflow_definition
    if (!definition) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/validation-error',
          title: 'Validation Error',
          detail: 'workflow_definition is required',
          code: 'VALIDATION_ERROR',
          retryable: false,
        },
        { status: 400 }
      )
    }

    const errors: Array<{ message: string; node_id: string | null }> = []
    if (!Array.isArray(definition.triggers) || definition.triggers.length === 0) {
      errors.push({ message: 'Workflow must have at least one trigger', node_id: null })
    }
    if (!Array.isArray(definition.nodes) || definition.nodes.length === 0) {
      errors.push({ message: 'Workflow must have at least one node', node_id: null })
    }
    if (!Array.isArray(definition.edges) || definition.edges.length === 0) {
      errors.push({
        message: 'Workflow must have at least one edge connecting a trigger to a node',
        node_id: null,
      })
    }

    // Flag every node that has incomplete/empty configuration
    const nodes = definition.nodes ?? []
    for (const node of nodes) {
      if (!node.id) continue
      const params = node.parameters ?? {}
      const hasContent = Object.values(params).some((v) => v !== undefined && v !== null && v !== '')
      if (!hasContent) {
        errors.push({ message: 'Node configuration is incomplete', node_id: node.id })
      }
    }

    if (errors.length > 0) {
      const findings = errors.map((e) => ({
        severity: 'error' as const,
        category: 'schema_violation' as const,
        message: e.message,
        node_id: e.node_id,
        field_path: null,
      }))
      return HttpResponse.json({
        is_valid: false,
        error_count: findings.length,
        warning_count: 0,
        findings,
      })
    }

    return HttpResponse.json({ is_valid: true, error_count: 0, warning_count: 0, findings: [] })
  }),

  http.get('/api/v1/workflows/:workflowId', (request) => {
    const workflowId = request.params.workflowId
    const body = workflows.find((w) => w.id === workflowId)
    if (!body) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/workflow-not-found',
          title: 'Workflow Not Found',
          detail: `Workflow with id '${workflowId}' not found`,
          code: 'WORKFLOW_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/workflows/${workflowId}`,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json(body)
  }),
  http.patch('/api/v1/workflows/:workflowId', async (request) => {
    const workflowId = request.params.workflowId
    const workflow = workflows.find((w) => w.id === workflowId)
    if (!workflow) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/workflow-not-found',
          title: 'Workflow Not Found',
          detail: `Workflow with id '${workflowId}' not found`,
          code: 'WORKFLOW_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/workflows/${workflowId}`,
        },
        { status: 404 }
      )
    }

    const body = (await request.request.json()) as UpdateWorkflowBody & { expected_version?: number | null }
    const now = new Date().toISOString()
    const currentVersionNum = workflow.version?.version ?? workflow.current_version ?? 1

    if (body.expected_version != null && body.expected_version < currentVersionNum) {
      return workflowVersionConflictResponse(
        String(workflowId),
        currentVersionNum,
        body.expected_version,
        `/api/v1/workflows/${String(workflowId)}`,
        workflow.updated_at ?? now
      )
    }

    const nextVersion = currentVersionNum + 1

    const versions = getOrCreateVersionStore(String(workflowId), workflow)
    if (!versions.some((v) => v.version === currentVersionNum)) {
      versions.push({
        id: uuidv4(),
        workflow_id: String(workflowId),
        version: currentVersionNum,
        schema_version: workflow.version?.schema_version ?? '2.0.0',
        workflow_definition: JSON.parse(JSON.stringify(workflow.version?.workflow_definition)),
        change_description: workflow.version?.change_description ?? `Version ${currentVersionNum}`,
        status: 'draft',
        name: null,
        created_by: workflow.version?.created_by ?? MOCK_VERSION_CREATED_BY,
        created_by_username: MOCK_VERSION_CREATED_BY_USERNAME,
        created_at: workflow.version?.created_at ?? now,
        updated_at: workflow.version?.created_at ?? now,
        deleted_at: null,
        deleted_by: null,
      })
    }

    const mutableWorkflow = workflow as MutableWorkflowWithVersion
    mutableWorkflow.name = body.name ?? workflow.name
    mutableWorkflow.description = body.description ?? workflow.description
    mutableWorkflow.is_enabled = body.is_enabled ?? workflow.is_enabled
    mutableWorkflow.labels = body.labels ?? workflow.labels
    mutableWorkflow.updated_at = now
    mutableWorkflow.updated_by = 'user-1'
    mutableWorkflow.current_version = nextVersion
    // Tags live only in workflow.labels (above). Keep existing definition when PATCH omits workflow_definition (e.g. details-only edit).
    const nextDefinition = body.workflow_definition ?? workflow.version?.workflow_definition
    const nextVersionId = uuidv4()
    mutableWorkflow.version = {
      id: nextVersionId,
      version: nextVersion,
      schema_version: nextDefinition?.schema_version ?? workflow.version?.schema_version ?? '2.0.0',
      workflow_definition: nextDefinition,
      created_by: mutableWorkflow.updated_by ?? workflow.version?.created_by ?? 'user-1',
      created_at: now,
      change_description: body.change_description ?? 'Updated via mock API',
    }

    versions.push({
      id: nextVersionId,
      workflow_id: String(workflowId),
      version: nextVersion,
      schema_version: mutableWorkflow.version.schema_version ?? '2.0.0',
      workflow_definition: JSON.parse(JSON.stringify(nextDefinition)),
      change_description: mutableWorkflow.version.change_description ?? '',
      status: 'draft',
      name: null,
      created_by: mutableWorkflow.version.created_by ?? MOCK_VERSION_CREATED_BY,
      created_by_username: MOCK_VERSION_CREATED_BY_USERNAME,
      created_at: now,
      updated_at: now,
      deleted_at: null,
      deleted_by: null,
    })

    return HttpResponse.json(workflow)
  }),
  http.delete('/api/v1/workflows/:workflowId', (request) => {
    const workflowId = request.params.workflowId
    const workflowIndex = workflows.findIndex((w) => w.id === workflowId)
    if (workflowIndex === -1) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/workflow-not-found',
          title: 'Workflow Not Found',
          detail: `Workflow with id '${workflowId}' not found`,
          code: 'WORKFLOW_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/workflows/${workflowId}`,
        },
        { status: 404 }
      )
    }

    workflows.splice(workflowIndex, 1)

    // Cascade: remove executions associated with the deleted workflow
    for (let i = executions.length - 1; i >= 0; i--) {
      if (executions[i].workflow_id === workflowId) {
        executions.splice(i, 1)
      }
    }

    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/v1/workflows/:workflowId/test', async ({ request, params }) => {
    const workflowId = params.workflowId as string
    const workflow = workflows.find((w) => w.id === workflowId)

    if (!workflow) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/workflow-not-found',
          title: 'Workflow Not Found',
          detail: `Workflow with id '${workflowId}' not found`,
          code: 'WORKFLOW_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/workflows/${workflowId}/test`,
        },
        { status: 404 }
      )
    }

    const body = (await request.json()) as ExecutionsAPI.components['schemas']['TestExecutionCreate']

    // Create a test execution
    const execution = {
      id: uuidv4(),
      created_at: mockDate.now,
      updated_at: mockDate.now,
      workflow_id: workflowId,
      status: 'completed' as const,
      started_at: mockDate.now,
      completed_at: mockDate.now,
      started_by: 'user-1',
      input_data: body.trigger_inputs ?? {},
      mode: 'test' as ExecutionsAPI.components['schemas']['ExecutionMode'],
    }

    executions.push(execution)

    return HttpResponse.json({ id: execution.id }, { status: 201 })
  }),

  http.post('/api/v1/workflows/validate', async (request) => {
    const body = await request.request.json()
    const nodes: unknown[] = body?.workflow_definition?.nodes ?? []
    if (nodes.length === 0) {
      const findings = [
        {
          severity: 'error',
          category: 'missing_field',
          message: 'Workflow must have at least one trigger step',
          node_id: null,
          field_path: null,
        },
        {
          severity: 'error',
          category: 'missing_field',
          message: 'No steps have been added to the workflow',
          node_id: null,
          field_path: null,
        },
        {
          severity: 'error',
          category: 'missing_field',
          message: 'Workflow cannot be saved without any steps',
          node_id: null,
          field_path: null,
        },
      ]
      return HttpResponse.json({
        is_valid: false,
        error_count: findings.length,
        warning_count: 0,
        findings,
      })
    }
    return HttpResponse.json({
      is_valid: false,
      error_count: 1,
      warning_count: 0,
      findings: [
        {
          severity: 'error',
          category: 'schema_violation',
          message: 'Step is missing required configuration',
          node_id: 'check_temperature',
          field_path: null,
        },
      ],
    })
  }),

  http.post('/api/v1/workflows/:workflowId/versions/:version/publish', async (request) => {
    const workflowId = request.params.workflowId
    const workflow = workflows.find((w) => w.id === workflowId)
    if (!workflow) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/workflow-not-found',
          title: 'Workflow Not Found',
          detail: `Workflow with id '${workflowId}' not found`,
          code: 'WORKFLOW_NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }
    const body = (await request.request.json()) as {
      name?: string | null
      change_description?: string | null
      expected_version?: number | null
    }

    const currentVersionNum = workflow.version?.version ?? workflow.current_version ?? 1
    if (body.expected_version != null && body.expected_version < currentVersionNum) {
      return workflowVersionConflictResponse(
        String(workflowId),
        currentVersionNum,
        body.expected_version,
        `/api/v1/workflows/${String(workflowId)}/versions/${String(request.params.version)}/publish`,
        workflow.updated_at ?? new Date().toISOString()
      )
    }

    const version = parseInt(String(request.params.version), 10)
    if (isNaN(version) || version < 1) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/validation-error',
          title: 'Invalid Version',
          detail: `Version must be a positive integer`,
          code: 'VALIDATION_ERROR',
          retryable: false,
        },
        { status: 400 }
      )
    }
    if (!workflow.version || workflow.version.version !== version) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/version-not-found',
          title: 'Version Not Found',
          detail: `Version ${version} not found for workflow '${workflowId as string}'`,
          code: 'VERSION_NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }
    const mutableWorkflow = workflow as MutableWorkflowWithVersion
    const versionObj = mutableWorkflow.version as Record<string, unknown>
    versionObj.name = body?.name ?? null
    versionObj.change_description = body?.change_description ?? null
    versionObj.status = WorkflowVersionStatusEnum.PUBLISHED
    mutableWorkflow.published_version_id = (versionObj.id as string) ?? null
    ;(mutableWorkflow as Record<string, unknown>).published_version_number = version
    mutableWorkflow.is_enabled = true
    mutableWorkflow.updated_at = new Date().toISOString()

    const versions = getOrCreateVersionStore(String(workflowId), workflow)
    for (const v of versions) {
      if (v.status === 'published') v.status = 'previously_published'
    }
    const storeRecord = versions.find((v) => v.version === version)
    if (storeRecord) {
      storeRecord.status = 'published'
      storeRecord.name = (body?.name as string) ?? null
    }

    return HttpResponse.json({ ...mutableWorkflow, warning: '' })
  }),

  http.post('/api/v1/workflows/:workflowId/unpublish', (request) => {
    const workflowId = request.params.workflowId
    const workflow = workflows.find((w) => w.id === workflowId)
    if (!workflow) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/workflow-not-found',
          title: 'Workflow Not Found',
          detail: `Workflow with id '${workflowId}' not found`,
          code: 'WORKFLOW_NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }
    const mutableWorkflow = workflow as MutableWorkflowWithVersion
    mutableWorkflow.published_version_id = null
    ;(mutableWorkflow as Record<string, unknown>).published_version_number = null
    mutableWorkflow.is_enabled = false
    mutableWorkflow.updated_at = new Date().toISOString()
    if (mutableWorkflow.version) {
      const versionObj = mutableWorkflow.version as Record<string, unknown>
      versionObj.status = WorkflowVersionStatusEnum.PREVIOUSLY_PUBLISHED
    }

    const versions = getOrCreateVersionStore(String(workflowId), workflow)
    for (const v of versions) {
      if (v.status === 'published') v.status = 'previously_published'
    }

    return HttpResponse.json(mutableWorkflow)
  }),

  http.patch('/api/v1/workflows/:workflowId/versions/:version', async (request) => {
    const workflowId = String(request.params.workflowId)
    const versionNum = Number(request.params.version)
    const workflow = workflows.find((w) => w.id === workflowId)
    if (!workflow) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Workflow not found', code: 'WORKFLOW_NOT_FOUND' },
        { status: 404 }
      )
    }
    const versions = getOrCreateVersionStore(workflowId, workflow)
    const found = versions.find((v) => v.version === versionNum)
    if (!found) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: `Version ${versionNum} not found`, code: 'VERSION_NOT_FOUND' },
        { status: 404 }
      )
    }
    const body = (await request.request.json()) as { name?: string | null; change_description?: string | null }
    if (body.name !== undefined) found.name = body.name
    if (body.change_description !== undefined) found.change_description = body.change_description
    found.updated_at = new Date().toISOString()
    return HttpResponse.json(found)
  }),

  http.get('/api/v1/workflows/:workflowId/versions', ({ request, params }) => {
    const workflowId = String(params.workflowId)
    const workflow = workflows.find((w) => w.id === workflowId)
    if (!workflow) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Workflow not found', code: 'WORKFLOW_NOT_FOUND' },
        { status: 404 }
      )
    }

    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'

    const versions = getOrCreateVersionStore(workflowId, workflow)
    const sorted = [...versions]
      .sort((a, b) => b.version - a.version)
      .map((version) => ({
        ...version,
        created_by_username: version.created_by_username ?? MOCK_VERSION_CREATED_BY_USERNAME,
      }))

    return HttpResponse.json(paginate(sorted, cursor, limit, includeTotal))
  }),

  http.get('/api/v1/workflows/:workflowId/versions/:version', (request) => {
    const workflowId = String(request.params.workflowId)
    const versionNum = Number(request.params.version)
    const workflow = workflows.find((w) => w.id === workflowId)
    if (!workflow) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Workflow not found', code: 'WORKFLOW_NOT_FOUND' },
        { status: 404 }
      )
    }

    const versions = getOrCreateVersionStore(workflowId, workflow)
    const found = versions.find((v) => v.version === versionNum)
    if (!found) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: `Version ${versionNum} not found`, code: 'VERSION_NOT_FOUND' },
        { status: 404 }
      )
    }

    return HttpResponse.json(found)
  }),

  http.post('/api/v1/workflows/:workflowId/versions/:version/restore', (request) => {
    const workflowId = String(request.params.workflowId)
    const workflow = workflows.find((w) => w.id === workflowId)
    if (!workflow) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Workflow not found', code: 'WORKFLOW_NOT_FOUND' },
        { status: 404 }
      )
    }

    const now = new Date().toISOString()
    const restoredVersionNum = Number(request.params.version)
    const versions = getOrCreateVersionStore(workflowId, workflow)
    const sourceVersion = versions.find((v) => v.version === restoredVersionNum)
    if (!sourceVersion) {
      return HttpResponse.json(
        {
          type: 'not-found',
          title: 'Not Found',
          detail: `Version ${restoredVersionNum} not found`,
          code: 'VERSION_NOT_FOUND',
        },
        { status: 404 }
      )
    }

    const nextVersion = Math.max(...versions.map((v) => v.version)) + 1
    const restoredDef = JSON.parse(JSON.stringify(sourceVersion.workflow_definition))

    const newVersionRecord: MockVersionRecord = {
      id: uuidv4(),
      workflow_id: workflowId,
      version: nextVersion,
      schema_version: sourceVersion.schema_version,
      workflow_definition: restoredDef,
      change_description: `Restored from version ${restoredVersionNum}`,
      status: 'draft',
      name: null,
      created_by: MOCK_VERSION_CREATED_BY,
      created_by_username: MOCK_VERSION_CREATED_BY_USERNAME,
      created_at: now,
      updated_at: now,
      deleted_at: null,
      deleted_by: null,
    }
    versions.push(newVersionRecord)

    const mutableWorkflow = workflow as MutableWorkflowWithVersion
    mutableWorkflow.current_version = nextVersion
    mutableWorkflow.updated_at = now
    mutableWorkflow.version = {
      version: nextVersion,
      schema_version: sourceVersion.schema_version,
      workflow_definition: restoredDef,
      created_by: 'user-1',
      created_at: now,
      change_description: `Restored from version ${restoredVersionNum}`,
    }

    return HttpResponse.json(workflow)
  }),

  http.get('/api/v1/workflows/:workflowId/versions/:version/export', (request) => {
    const workflowId = String(request.params.workflowId)
    const workflow = workflows.find((w) => w.id === workflowId)
    if (!workflow) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Workflow not found', code: 'WORKFLOW_NOT_FOUND' },
        { status: 404 }
      )
    }

    const versionNum = Number(request.params.version)
    const versions = getOrCreateVersionStore(workflowId, workflow)
    const versionRecord = versions.find((v) => v.version === versionNum)
    if (!versionRecord) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: `Version ${versionNum} not found`, code: 'VERSION_NOT_FOUND' },
        { status: 404 }
      )
    }

    const definition = versionRecord.workflow_definition ?? {}
    return new HttpResponse(JSON.stringify(definition, null, 2), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Content-Disposition': `attachment; filename="${workflow.name}-v${versionNum}.json"`,
      },
    })
  }),

  http.get('/api/v1/executions', ({ request }) => {
    const url = new URL(request.url)
    const workflow_id = url.searchParams.get('workflow_id')
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const sort = url.searchParams.get('sort')

    const project_id = url.searchParams.get('project_id')

    const status = url.searchParams.get('status')
    const workflow_version_id = url.searchParams.get('workflow_version_id')
    const approval_pending = url.searchParams.get('approval_pending')

    let filtered = workflow_id ? executions.filter((e) => e.workflow_id === workflow_id) : [...executions]

    if (status) {
      filtered = filtered.filter((e) => e.status === status)
    }

    if (approval_pending === 'true') {
      filtered = filtered.filter((e) => e.approval_pending === true)
    }

    if (workflow_version_id) {
      filtered = filtered.filter(
        (e) => (e as { workflow_version_id?: string }).workflow_version_id === workflow_version_id
      )
    }

    // Filter by project: find workflow IDs belonging to the project, then filter executions
    if (project_id) {
      const projectWorkflowIds = new Set(workflows.filter((w) => w.project_id === project_id).map((w) => w.id))
      filtered = filtered.filter((e) => e.workflow_id && projectWorkflowIds.has(e.workflow_id))
    }

    // Enrich executions with project_id from their workflow
    const workflowMap = new Map(workflows.map((w) => [w.id, w]))
    const enriched = filtered.map((e) => {
      const wf = e.workflow_id ? workflowMap.get(e.workflow_id) : undefined
      const versionNum = wf?.published_version ?? wf?.current_version ?? 1
      const existingVersionId = (e as { workflow_version_id?: string }).workflow_version_id
      return {
        ...e,
        project_id: wf?.project_id ?? null,
        workflow_version: versionNum,
        workflow_version_id: existingVersionId ?? (e.workflow_id ? `wv-${e.workflow_id}-${versionNum}` : null),
        workflow_version_name: null,
        workflow_version_created_at:
          (e as { workflow_version_created_at?: string }).workflow_version_created_at ?? e.created_at ?? null,
      }
    })

    if (sort) {
      const isDesc = sort.startsWith('-')
      const field = isDesc ? sort.slice(1) : sort
      // Allowlist matches Execution.__sortable_fields__; unknown fields are ignored.
      enriched.sort((a, b) => {
        let aVal = ''
        let bVal = ''
        switch (field) {
          case 'id':
            aVal = a.id ?? ''
            bVal = b.id ?? ''
            break
          case 'workflow_version_id':
            aVal = a.workflow_version_id ?? ''
            bVal = b.workflow_version_id ?? ''
            break
          case 'created_at':
            aVal = a.created_at ?? ''
            bVal = b.created_at ?? ''
            break
          case 'updated_at':
            aVal = a.updated_at ?? ''
            bVal = b.updated_at ?? ''
            break
          case 'completed_at':
            aVal = a.completed_at ?? ''
            bVal = b.completed_at ?? ''
            break
          case 'status':
            aVal = a.status ?? ''
            bVal = b.status ?? ''
            break
          case 'deleted_at':
            aVal = (a as { deleted_at?: string | null }).deleted_at ?? ''
            bVal = (b as { deleted_at?: string | null }).deleted_at ?? ''
            break
          default:
            return 0
        }
        const cmp = aVal.localeCompare(bVal)
        return isDesc ? -cmp : cmp
      })
    }

    const body = paginate(enriched, cursor, limit, includeTotal)
    return HttpResponse.json(body)
  }),

  http.post('/api/v1/executions', async ({ request }) => {
    const body = (await request.json()) as ExecutionsAPI.components['schemas']['ExecutionCreate'] & {
      /** Mock-only: optional status override for self-contained E2E seeding. */
      status?: 'completed' | 'failed' | 'running' | 'cancelled' | 'pending' | 'paused'
    }
    const executionId = uuidv4()
    const workflow = workflows.find((w) => w.id === body.workflow_id)
    const versionNum = workflow?.published_version ?? workflow?.current_version ?? 1
    const existingCount = executions.filter((e) => e.workflow_id === body.workflow_id).length

    const definition = workflow?.version?.workflow_definition as
      | {
          nodes?: Array<{ id?: string; type?: string; name?: string }>
          triggers?: Array<{ id?: string; type?: string; name?: string }>
        }
      | undefined
    // Include triggers so mock activity lists match real-backend executions.
    const nodes = [...(definition?.triggers ?? []), ...(definition?.nodes ?? [])]

    // Synthesize per-node activities so newly created executions are usable in
    // self-contained E2E tests (GET detail / activities list).
    const hasApproval = nodes.some((node) => node.type === 'approval')

    // Default remains completed for suite-wide stability. Tests that need mixed
    // statuses pass an explicit `status` (mock-only; ignored by the real API).
    // Approval workflows still default to paused when no override is provided.
    const status = body.status ?? (hasApproval ? 'paused' : 'completed')
    const timestampCycle = [mockDate.hoursAgo1, mockDate.hoursAgo2, mockDate.hoursAgo3, mockDate.hoursAgo4] as const
    const timestamp = timestampCycle[existingCount % timestampCycle.length]
    const isTerminal = status === 'completed' || status === 'failed' || status === 'cancelled'
    const isPaused = status === 'paused'

    const activities: ExecutionsAPI.components['schemas']['ActivityExecution'][] = nodes
      .filter((node): node is { id: string; type?: string; name?: string } => typeof node.id === 'string')
      .map((node, index) => {
        const isApproval = node.type === 'approval'
        return {
          id: `act-${executionId}-${index + 1}`,
          created_at: timestamp,
          updated_at: timestamp,
          execution_id: executionId,
          activity_name: node.id,
          status: isApproval && isPaused ? ('waiting' as const) : ('completed' as const),
          started_at: timestamp,
          completed_at: isApproval && isPaused ? null : timestamp,
          input_data: {},
          output_data: isApproval && isPaused ? null : {},
          error_details: null,
          retry_count: 0,
          iteration: null,
        }
      })
    if (activities.length > 0) {
      activityExecutions[executionId] = activities
    }

    const execution = {
      id: executionId,
      created_at: timestamp,
      updated_at: timestamp,
      workflow_id: body.workflow_id,
      status,
      approval_pending: isPaused,
      started_at: timestamp,
      completed_at: isTerminal ? timestamp : null,
      started_by: 'user-1',
      input_data: body.input_data ?? {},
      current_activities: isPaused
        ? activities
            .filter((activity) => activity.status === 'waiting')
            .map((activity) => ({
              activity_name: activity.activity_name,
              temporal_activity_id: activity.id,
              iteration: null,
            }))
        : [],
      workflow_version: versionNum,
      workflow_version_id: body.workflow_id ? `wv-${body.workflow_id}-${versionNum}` : null,
      workflow_version_name: null,
      workflow_version_created_at: mockDate.daysAgo1,
      project_id: workflow?.project_id ?? null,
    }
    executions.push(execution)
    return HttpResponse.json(execution, { status: 201 })
  }),

  http.get('/api/v1/executions/:executionId', ({ request, params }) => {
    const executionId = params.executionId as string
    const detail = getExecutionDetail(executionId)
    if (!detail) {
      return createExecutionNotFoundResponse(executionId)
    }

    const include = new Set(
      (new URL(request.url).searchParams.get('include') ?? '')
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean)
    )

    if (include.size === 0) {
      const summary = { ...detail, activities: undefined, workflow_definition: undefined }
      return HttpResponse.json(summary)
    }

    return HttpResponse.json({
      ...detail,
      ...(include.has('activities') ? {} : { activities: undefined }),
      ...(include.has('workflow_definition') ? {} : { workflow_definition: undefined }),
    })
  }),

  http.post('/api/v1/executions/:executionId/cancel', (request) => {
    const executionId = request.params.executionId as string
    const execution = executions.find((e) => e.id === executionId)
    if (!execution) {
      return createExecutionNotFoundResponse(executionId, 'cancel')
    }
    if (execution.status !== ExecutionStatusEnum.PENDING && execution.status !== ExecutionStatusEnum.RUNNING) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/invalid-state',
          title: 'Invalid State',
          detail: `Cannot cancel execution in '${execution.status}' state`,
          code: 'INVALID_STATE',
          retryable: false,
          instance: `/api/v1/executions/${executionId}/cancel`,
        },
        { status: 400 }
      )
    }
    execution.status = ExecutionStatusEnum.CANCELLED
    return new HttpResponse(null, { status: 202 })
  }),

  http.post('/api/v1/executions/:executionId/retry', (request) => {
    const executionId = request.params.executionId as string
    const execution = executions.find((e) => e.id === executionId)
    if (!execution) {
      return createExecutionNotFoundResponse(executionId, 'retry')
    }
    const terminalStatuses = new Set([
      ExecutionStatusEnum.COMPLETED,
      ExecutionStatusEnum.COMPLETED_WITH_ERRORS,
      ExecutionStatusEnum.FAILED,
      ExecutionStatusEnum.CANCELLED,
    ])
    if (!terminalStatuses.has(execution.status as (typeof ExecutionStatusEnum)[keyof typeof ExecutionStatusEnum])) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/resource-conflict',
          title: 'Execution Not Retryable',
          detail: `Cannot retry execution in '${execution.status}' state`,
          code: 'EXECUTION_NOT_RETRYABLE',
          retryable: false,
          instance: `/api/v1/executions/${executionId}/retry`,
        },
        { status: 409 }
      )
    }
    if (execution.mode === 'test') {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/resource-conflict',
          title: 'Execution Not Retryable',
          detail: 'Test executions cannot be retried',
          code: 'EXECUTION_NOT_RETRYABLE',
          retryable: false,
          instance: `/api/v1/executions/${executionId}/retry`,
        },
        { status: 409 }
      )
    }
    const newExecution: Execution = {
      ...execution,
      id: uuidv4(),
      status: ExecutionStatusEnum.PENDING,
      temporal_workflow_id: `exec-${uuidv4()}`,
      created_at: mockDate.now,
      updated_at: mockDate.now,
      completed_at: null,
      error_details: null,
      retried_from_execution_id: execution.id,
      current_activities: [],
    }
    executions.unshift(newExecution)
    return HttpResponse.json(newExecution, { status: 201 })
  }),

  http.get('/api/v1/executions/:executionId/activities', ({ request, params }) => {
    const executionId = params.executionId as string
    const execution = executions.find((e) => e.id === executionId)
    if (!execution) {
      return createExecutionNotFoundResponse(executionId, 'activities')
    }

    const url = new URL(request.url)
    const activityName = url.searchParams.get('activity_name')
    const limitParam = url.searchParams.get('limit')
    const parsedLimit = limitParam ? Number.parseInt(limitParam, 10) : null
    const limit = parsedLimit != null && Number.isFinite(parsedLimit) ? parsedLimit : null

    let activities = activityExecutions[executionId] ?? []
    if (activityName) {
      activities = activities.filter((activity) => activity.activity_name === activityName)
    }
    if (limit != null && limit > 0) {
      activities = activities.slice(0, limit)
    }

    return HttpResponse.json({
      resources: activities,
      next: null,
      prev: null,
    })
  }),

  http.get('/api/v1/approvals', ({ request }) => {
    const url = new URL(request.url)
    const status = url.searchParams.get('status')
    const execution_id = url.searchParams.get('execution_id')
    const project_id = url.searchParams.get('project_id')
    const created_at = url.searchParams.get('created_at')
    const nameContains = url.searchParams.get('name[contains]')
    const sort = url.searchParams.get('sort')
    const cursor = url.searchParams.get('cursor')
    const limitParam = url.searchParams.get('limit')
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const limit = Math.min(Math.max(1, limitParam ? parseInt(limitParam, 10) : 50), 100)

    // Filter approvals
    const filtered = approvals.filter((a) => {
      if (status && a.status !== status) return false
      if (project_id) {
        const approvalData = a as unknown as { project_id?: string | null }
        if (approvalData.project_id !== project_id) return false
      }
      if (execution_id) {
        const approvalData = a as unknown as { execution_id?: string }
        if (approvalData.execution_id !== execution_id) return false
      }
      if (created_at) {
        const ts = approvalCreatedAt(a)
        if (!ts) return false
        const filterDate = new Date(created_at).toDateString()
        if (new Date(ts).toDateString() !== filterDate) return false
      }
      if (nameContains) {
        const approvalData = a as unknown as { name?: string }
        const name = approvalData.name || ''
        if (!name.toLowerCase().includes(nameContains.toLowerCase())) return false
      }
      return true
    })

    // Sort if provided
    if (sort) {
      const isDesc = sort.startsWith('-')
      const field = isDesc ? sort.slice(1) : sort
      filtered.sort((a, b) => {
        let aVal: string | number = ''
        let bVal: string | number = ''
        if (field === 'created_at') {
          const aTs = approvalCreatedAt(a)
          const bTs = approvalCreatedAt(b)
          aVal = aTs ? new Date(aTs).getTime() : 0
          bVal = bTs ? new Date(bTs).getTime() : 0
        } else if (field === 'name') {
          aVal = (a as unknown as { name?: string }).name || ''
          bVal = (b as unknown as { name?: string }).name || ''
        } else if (field === 'status') {
          aVal = a.status || ''
          bVal = b.status || ''
        }
        const cmp =
          typeof aVal === 'string' && typeof bVal === 'string'
            ? aVal.localeCompare(bVal)
            : (aVal as number) - (bVal as number)
        return isDesc ? -cmp : cmp
      })
    }

    const body: ApprovalsResponse = paginate(filtered, cursor, limit, includeTotal)
    return HttpResponse.json(body)
  }),

  http.get('/api/v1/approvals/:approvalId', (request) => {
    const approvalId = request.params.approvalId
    const body = approvals.find((a) => a.id === approvalId)
    if (!body) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/approval-not-found',
          title: 'Approval Not Found',
          detail: `Approval with id '${approvalId}' not found`,
          code: 'APPROVAL_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/approvals/${approvalId}`,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json(body)
  }),

  http.patch('/api/v1/approvals/:approvalId', async (request) => {
    const approvalId = request.params.approvalId
    const approval = approvals.find((a) => a.id === approvalId)
    if (!approval) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/approval-not-found',
          title: 'Approval Not Found',
          detail: `Approval with id '${approvalId}' not found`,
          code: 'APPROVAL_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/approvals/${approvalId}`,
        },
        { status: 404 }
      )
    }

    const body = (await request.request.json()) as {
      status: 'approved' | 'rejected' | 'cancelled'
      notes?: string | null
    }

    // Check if already decided (409 conflict)
    const approvalData = approval as unknown as {
      status?: string
      decided_by?: { id: string; name: string } | null
      decided_at?: string | null
      decision_notes?: string | null
      updatedAt?: string
    }

    if (approvalData.status && approvalData.status !== 'pending' && approvalData.status !== 'expired') {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/approval-conflict',
          title: 'Approval Conflict',
          detail: 'Approval already decided or workflow cancelled',
          code: 'APPROVAL_CONFLICT',
          retryable: false,
          instance: `/api/v1/approvals/${approvalId}`,
        },
        { status: 409 }
      )
    }

    approvalData.status = body.status
    const decidedNow = new Date().toISOString()
    approvalData.decided_at = decidedNow
    approvalData.decision_notes = body.notes ?? null
    // Mock user - in real implementation, this would come from auth context
    approvalData.decided_by = {
      id: '770e8400-e29b-41d4-a716-446655440001',
      name: 'Current User',
    }
    approvalData.updatedAt = decidedNow
    ;(approval as { updated_at: string }).updated_at = decidedNow

    return HttpResponse.json(approval)
  }),

  http.post('/api/v1/approvals/batch', async (request) => {
    const body = (await request.request.json()) as {
      decisions: Array<{ approval_id: string; status: 'approved' | 'rejected' | 'cancelled'; notes?: string | null }>
    }

    if (!body.decisions || body.decisions.length === 0 || body.decisions.length > 100) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/validation-error',
          title: 'Validation Error',
          detail: 'Invalid payload: decisions array must contain 1-100 items',
          code: 'VALIDATION_ERROR',
          retryable: false,
          instance: '/api/v1/approvals/batch',
        },
        { status: 400 }
      )
    }

    const mockUser = { id: '770e8400-e29b-41d4-a716-446655440001', name: 'Current User' }
    const now = new Date().toISOString()

    const results = body.decisions.map((decision) => {
      const approval = approvals.find((a) => a.id === decision.approval_id)
      if (!approval) {
        return {
          approval_id: decision.approval_id,
          success: false,
          status: null,
          decided_at: null,
          decided_by: null,
          decision_notes: null,
          error: 'Approval not found',
        }
      }

      const data = approval as unknown as {
        status?: string
        decided_by?: { id: string; name: string } | null
        decided_at?: string | null
        decision_notes?: string | null
        updatedAt?: string
      }
      if (data.status && data.status !== 'pending' && data.status !== 'expired') {
        return {
          approval_id: decision.approval_id,
          success: false,
          status: data.status,
          decided_at: data.decided_at || null,
          decided_by: data.decided_by || null,
          decision_notes: data.decision_notes || null,
          error: 'Approval already decided or workflow cancelled',
        }
      }

      data.status = decision.status
      data.decided_at = now
      data.decision_notes = decision.notes ?? null
      data.decided_by = mockUser
      data.updatedAt = now
      ;(approval as { updated_at: string }).updated_at = now

      return {
        approval_id: decision.approval_id,
        success: true,
        status: decision.status,
        decided_at: now,
        decided_by: mockUser,
        decision_notes: decision.notes || null,
        error: null,
      }
    })

    return HttpResponse.json({
      results,
      total_success: results.filter((r) => r.success).length,
      total_failed: results.filter((r) => !r.success).length,
    })
  }),

  // Auth providers (public endpoint for login page)
  http.get('/api/v1/auth/providers', () => {
    const enabled = identityProviders.filter((p) => p.enabled)
    return HttpResponse.json({
      resources: enabled.map((p) => ({
        id: p.id,
        name: p.name,
        provider_type: p.configuration?.provider_type ?? 'oidc',
        provider_template: p.configuration?.idp_type ?? null,
      })),
    })
  }),

  // Auth login — encode the username in the access token for role-aware mock handlers
  http.post('/api/v1/auth/login', async ({ request }) => {
    const body = (await request.json()) as { username?: string } | null
    const username = body?.username ?? 'admin'
    const userId = `user-${username}`
    return HttpResponse.json({
      access_token: createMockJwt({ username, userId }),
      token_type: 'bearer',
      expires_in: 3600,
    })
  }),

  // CSRF token — return a mock form token
  http.post('/api/v1/auth/csrf_token', () => {
    return HttpResponse.json({ csrf_token: 'mock-csrf-form-token' })
  }),

  // Auth refresh — preserve username from existing token
  http.post('/api/v1/auth/refresh', ({ request }) => {
    const username = getUsernameFromRequest(request)
    const userId = `user-${username}`
    return HttpResponse.json({
      access_token: createMockJwt({ username, userId }),
      token_type: 'bearer',
      expires_in: 3600,
    })
  }),

  // Auth logout
  http.post('/api/v1/auth/logout', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  // Current user (mock profile) — returns role-appropriate profile based on token
  // Toggle RP-initiated logout via RP_LOGOUT_ENABLED env var (e.g. RP_LOGOUT_ENABLED=true npm start)
  http.get('/api/v1/auth/me', ({ request }) => {
    const rpLogoutEnabled = process.env.RP_LOGOUT_ENABLED === 'true'
    const username = getUsernameFromRequest(request)

    if (username === 'auditor') {
      return HttpResponse.json({
        id: 'a0d1t0r0-0000-0000-0000-000000000000',
        username: 'auditor',
        email: 'auditor@example.com',
        groups: ['authenticated'],
        rp_logout_enabled: rpLogoutEnabled,
      })
    }

    if (username === 'viewer') {
      return HttpResponse.json({
        id: 'v13w3r00-0000-0000-0000-000000000000',
        username: 'viewer',
        email: 'viewer@example.com',
        groups: ['authenticated'],
        rp_logout_enabled: rpLogoutEnabled,
      })
    }

    if (username === 'user') {
      return HttpResponse.json({
        id: 'us3r0000-0000-0000-0000-000000000000',
        username: 'user',
        email: 'user@example.com',
        groups: ['authenticated'],
        rp_logout_enabled: rpLogoutEnabled,
      })
    }

    if (username === 'project-admin') {
      return HttpResponse.json({
        id: 'pr0j4dm1-0000-0000-0000-000000000000',
        username: 'project-admin',
        email: 'project-admin@example.com',
        groups: ['authenticated'],
        project_id: 'p-001',
        rp_logout_enabled: rpLogoutEnabled,
      })
    }

    return HttpResponse.json({
      id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      username: 'demo',
      email: 'demo@example.com',
      groups: ['admins', 'platform-admins', 'authenticated'],
      rp_logout_enabled: rpLogoutEnabled,
    })
  }),

  // Identity provider handlers
  http.get('/api/v1/identity_providers', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const sort = url.searchParams.get('sort')

    const resources = [...identityProviders]

    if (sort) {
      const isDesc = sort.startsWith('-')
      const field = isDesc ? sort.slice(1) : sort
      resources.sort((a, b) => {
        let aVal = ''
        let bVal = ''
        switch (field) {
          case 'name':
            aVal = a.name ?? ''
            bVal = b.name ?? ''
            break
          case 'enabled':
            aVal = a.enabled ? 'Enabled' : 'Disabled'
            bVal = b.enabled ? 'Enabled' : 'Disabled'
            break
          case 'issuer_url':
            aVal = a.configuration?.issuer_url ?? ''
            bVal = b.configuration?.issuer_url ?? ''
            break
          case 'client_id':
            aVal = a.configuration?.client_id ?? ''
            bVal = b.configuration?.client_id ?? ''
            break
          default:
            aVal = a.name ?? ''
            bVal = b.name ?? ''
        }
        const cmp = aVal.localeCompare(bVal)
        return isDesc ? -cmp : cmp
      })
    }

    return HttpResponse.json(paginate(resources, cursor, limit, includeTotal))
  }),

  http.post('/api/v1/identity_providers', async ({ request }) => {
    const body = (await request.json()) as {
      name?: string
      description?: string
      enabled?: boolean
      configuration?: IdentityProvider['configuration']
    }

    const jmespathError = validateGroupJmespathExpression(body.configuration?.group_jmespath_expression)
    if (jmespathError) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/validation-error',
          title: 'Validation Error',
          detail: jmespathError,
          code: 'VALIDATION_ERROR',
          retryable: false,
          instance: '/api/v1/identity_providers',
        },
        { status: 422 }
      )
    }

    const existing = identityProviders.find((p) => p.name?.toLowerCase() === body.name?.toLowerCase())
    if (existing) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/provider-name-conflict',
          title: 'Provider Name Conflict',
          detail: `An identity provider named "${body.name}" already exists. Choose a different name.`,
          code: 'PROVIDER_NAME_CONFLICT',
          retryable: false,
          instance: '/api/v1/identity_providers',
        },
        { status: 409 }
      )
    }

    const now = new Date().toISOString()
    const safeConfig = Object.fromEntries(
      Object.entries((body.configuration ?? {}) as Record<string, unknown>).filter(([key]) => key !== 'client_secret')
    )
    const provider: IdentityProvider = {
      id: uuidv4(),
      name: body.name,
      description: body.description,
      enabled: body.enabled ?? true,
      configuration: safeConfig as IdentityProvider['configuration'],
      created_at: now,
      updated_at: now,
    }
    identityProviders.push(provider)
    return HttpResponse.json(provider, { status: 201 })
  }),

  http.get('/api/v1/identity_providers/:providerId', ({ params }) => {
    const provider = identityProviders.find((p) => p.id === params.providerId)
    if (!provider) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/provider-not-found',
          title: 'Provider Not Found',
          detail: `Identity provider with id '${params.providerId as string}' not found`,
          code: 'PROVIDER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/identity_providers/${params.providerId as string}`,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json(provider)
  }),

  http.patch('/api/v1/identity_providers/:providerId', async ({ params, request }) => {
    const provider = identityProviders.find((p) => p.id === params.providerId)
    if (!provider) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/provider-not-found',
          title: 'Provider Not Found',
          detail: `Identity provider with id '${params.providerId as string}' not found`,
          code: 'PROVIDER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/identity_providers/${params.providerId as string}`,
        },
        { status: 404 }
      )
    }

    const body = (await request.json()) as {
      name?: string
      description?: string
      enabled?: boolean
      configuration?: IdentityProvider['configuration']
    }

    if (body.name && body.name.toLowerCase() !== provider.name?.toLowerCase()) {
      const conflict = identityProviders.find(
        (p) => p.id !== provider.id && p.name?.toLowerCase() === body.name?.toLowerCase()
      )
      if (conflict) {
        return HttpResponse.json(
          {
            type: 'https://api.example.com/errors/provider-name-conflict',
            title: 'Provider Name Conflict',
            detail: `An identity provider named "${body.name}" already exists. Choose a different name.`,
            code: 'PROVIDER_NAME_CONFLICT',
            retryable: false,
            instance: `/api/v1/identity_providers/${params.providerId as string}`,
          },
          { status: 409 }
        )
      }
    }

    const mergedConfiguration =
      body.configuration !== undefined ? { ...provider.configuration, ...body.configuration } : provider.configuration
    const jmespathError = validateGroupJmespathExpression(mergedConfiguration?.group_jmespath_expression)
    if (jmespathError) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/validation-error',
          title: 'Validation Error',
          detail: jmespathError,
          code: 'VALIDATION_ERROR',
          retryable: false,
          instance: `/api/v1/identity_providers/${params.providerId as string}`,
        },
        { status: 422 }
      )
    }

    const index = identityProviders.indexOf(provider)
    let patchedConfig = body.configuration !== undefined ? mergedConfiguration : undefined
    if (patchedConfig) {
      patchedConfig = Object.fromEntries(
        Object.entries(patchedConfig as Record<string, unknown>).filter(([key]) => key !== 'client_secret')
      ) as typeof body.configuration
    }
    const updated: IdentityProvider = {
      ...provider,
      ...(body.name !== undefined && { name: body.name }),
      ...(body.description !== undefined && { description: body.description }),
      ...(body.enabled !== undefined && { enabled: body.enabled }),
      ...(patchedConfig !== undefined && { configuration: patchedConfig }),
      updated_at: new Date().toISOString(),
    }
    identityProviders[index] = updated

    return HttpResponse.json(updated)
  }),

  http.delete('/api/v1/identity_providers/:providerId', ({ params }) => {
    const index = identityProviders.findIndex((p) => p.id === params.providerId)
    if (index === -1) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/provider-not-found',
          title: 'Provider Not Found',
          detail: `Identity provider with id '${params.providerId as string}' not found`,
          code: 'PROVIDER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/identity_providers/${params.providerId as string}`,
        },
        { status: 404 }
      )
    }
    identityProviders.splice(index, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/v1/identity_providers/setup_aap_oidc', async ({ request }) => {
    const body = (await request.json()) as {
      aap_url?: string
      organization?: string
      admin_username?: string
      admin_password?: string
      personal_access_token?: string
      insecure_skip_tls_verify?: boolean
    }

    const hasBasicAuth = body.admin_username && body.admin_password
    const hasToken = body.personal_access_token

    if (!body.aap_url || (!hasBasicAuth && !hasToken)) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/validation-error',
          title: 'Validation Error',
          detail: 'aap_url and either admin credentials or a personal access token are required',
          code: 'VALIDATION_ERROR',
          retryable: false,
        },
        { status: 422 }
      )
    }

    const existing = identityProviders.find((p) => p.configuration?.idp_type === 'aap')
    if (existing) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/name-conflict',
          title: 'Identity Provider Name Conflict',
          detail: "Identity provider with name 'Ansible Automation Platform' already exists",
          code: 'IDENTITY_PROVIDER_NAME_CONFLICT',
          retryable: false,
        },
        { status: 409 }
      )
    }

    const provider: IdentityProvider = {
      id: crypto.randomUUID(),
      name: 'Ansible Automation Platform',
      description: 'Auto-configured AAP OIDC provider',
      enabled: true,
      configuration: {
        provider_type: 'oidc',
        idp_type: 'aap',
        auto_discovery: true,
        issuer_url: `${body.aap_url.replace(/\/+$/, '')}/o/`,
        client_id: `mock-${crypto.randomUUID().slice(0, 8)}`,
        redirect_uri: 'http://localhost:8000/api/v1/auth/oidc/callback',
        scopes: 'read write openid roles',
        claim_mapping: { subject: 'sub', email: 'email', username: 'preferred_username', full_name: 'name' },
        aap_role_mapping_enabled: true,
        enable_rp_initiated_logout: true,
        allow_all_authenticated: false,
        disable_tls_verify: body.insecure_skip_tls_verify ?? false,
        group_jmespath_expression: "[aap_teams[*].join('/', [organization, name]), aap_organizations[*].name] | []",
        group_mapping_entries: [],
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      created_by: 'admin',
      updated_by: 'admin',
    }

    identityProviders.push(provider)
    return HttpResponse.json(provider, { status: 201 })
  }),

  http.post('/api/v1/identity_providers/test', async ({ request }) => {
    const body = (await request.json()) as { configuration?: { issuer_url?: string } }
    const issuerUrl = body.configuration?.issuer_url ?? ''

    if (!issuerUrl) {
      return HttpResponse.json({ success: false, message: 'Issuer URL is required' }, { status: 400 })
    }

    return HttpResponse.json({
      success: true,
      message: `Successfully connected to ${issuerUrl}`,
      metadata: { issuer: issuerUrl },
      claims_supported: ['sub', 'email', 'preferred_username', 'name', 'groups'],
      claim_aliases: {
        email: ['email'],
        username: ['preferred_username'],
        first_name: ['given_name'],
        last_name: ['family_name'],
        groups: ['groups'],
      },
      end_session_endpoint_supported: true,
    })
  }),

  // User handlers
  http.get('/api/v1/users', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const sort = url.searchParams.get('sort')
    const usernameContains = url.searchParams.get('username[contains]')

    let resources = [...users]

    if (usernameContains) {
      const searchTerm = usernameContains.toLowerCase()
      resources = resources.filter((u) => u.username.toLowerCase().includes(searchTerm))
    }

    const emailContains = url.searchParams.get('email[contains]')
    if (emailContains) {
      const searchTerm = emailContains.toLowerCase()
      resources = resources.filter((u) => u.email.toLowerCase().includes(searchTerm))
    }

    const firstNameContains = url.searchParams.get('first_name[contains]')
    if (firstNameContains) {
      const searchTerm = firstNameContains.toLowerCase()
      resources = resources.filter((u) => u.first_name.toLowerCase().includes(searchTerm))
    }

    const lastNameContains = url.searchParams.get('last_name[contains]')
    if (lastNameContains) {
      const searchTerm = lastNameContains.toLowerCase()
      resources = resources.filter((u) => (u.last_name ?? '').toLowerCase().includes(searchTerm))
    }

    const authSource = url.searchParams.get('auth_source')
    if (authSource) {
      resources = resources.filter((u) => (u.auth_sources ?? []).includes(authSource))
    }

    if (sort) {
      const isDesc = sort.startsWith('-')
      const field = isDesc ? sort.slice(1) : sort
      resources.sort((a, b) => {
        let aVal = ''
        let bVal = ''
        switch (field) {
          case 'username':
            aVal = a.username
            bVal = b.username
            break
          case 'first_name':
            aVal = a.first_name
            bVal = b.first_name
            break
          case 'last_name':
            aVal = a.last_name ?? ''
            bVal = b.last_name ?? ''
            break
          case 'email':
            aVal = a.email
            bVal = b.email
            break
          case 'last_login':
            aVal = a.last_login ?? ''
            bVal = b.last_login ?? ''
            break
          default:
            aVal = a.username
            bVal = b.username
        }
        const cmp = aVal.localeCompare(bVal)
        return isDesc ? -cmp : cmp
      })
    }

    return HttpResponse.json(paginate(resources, cursor, limit, includeTotal))
  }),

  http.post('/api/v1/users', async ({ request }) => {
    const body = (await request.json()) as {
      username?: string
      email?: string
      first_name?: string | null
      last_name?: string | null
      password?: string
      is_enabled?: boolean
      group_names?: string[] | null
    }

    const existing = users.find(
      (u) =>
        u.username.toLowerCase() === body.username?.toLowerCase() || u.email.toLowerCase() === body.email?.toLowerCase()
    )
    if (existing) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-conflict',
          title: 'User Conflict',
          detail: `A user with that username or email already exists.`,
          code: 'USER_CONFLICT',
          retryable: false,
          instance: '/api/v1/users',
        },
        { status: 409 }
      )
    }

    const now = new Date().toISOString()
    const newUser: UserRead = {
      id: uuidv4(),
      username: body.username ?? '',
      email: body.email ?? '',
      first_name: body.first_name ?? '',
      last_name: body.last_name ?? null,
      is_enabled: body.is_enabled ?? true,
      auth_type: 'local',
      auth_sources: ['Local'],
      last_login: null,
      created_at: now,
      updated_at: now,
    }
    users.push(newUser)
    return HttpResponse.json(newUser, { status: 201 })
  }),

  http.get('/api/v1/users/:userId', ({ params }) => {
    const user = users.find((u) => u.id === params.userId)
    if (!user) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-not-found',
          title: 'User Not Found',
          detail: `User with id '${params.userId as string}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}`,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json(user)
  }),

  http.patch('/api/v1/users/:userId', async ({ params, request }) => {
    const user = users.find((u) => u.id === params.userId)
    if (!user) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-not-found',
          title: 'User Not Found',
          detail: `User with id '${params.userId as string}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}`,
        },
        { status: 404 }
      )
    }

    const body = (await request.json()) as {
      first_name?: string
      last_name?: string | null
      email?: string
      password?: string
      is_enabled?: boolean
    }

    if (body.email && body.email.toLowerCase() !== user.email.toLowerCase()) {
      const conflict = users.find((u) => u.id !== user.id && u.email.toLowerCase() === body.email?.toLowerCase())
      if (conflict) {
        return HttpResponse.json(
          {
            type: 'https://api.example.com/errors/user-conflict',
            title: 'Email Conflict',
            detail: `A user with that email already exists.`,
            code: 'USER_CONFLICT',
            retryable: false,
            instance: `/api/v1/users/${params.userId as string}`,
          },
          { status: 409 }
        )
      }
    }

    const index = users.indexOf(user)
    const updated: UserRead = {
      ...user,
      ...(body.first_name !== undefined && { first_name: body.first_name }),
      ...(body.last_name !== undefined && { last_name: body.last_name }),
      ...(body.email !== undefined && { email: body.email }),
      ...(body.is_enabled !== undefined && { is_enabled: body.is_enabled }),
      updated_at: new Date().toISOString(),
    }
    users[index] = updated
    return HttpResponse.json(updated)
  }),

  http.delete('/api/v1/users/:userId', ({ params }) => {
    const index = users.findIndex((u) => u.id === params.userId)
    if (index === -1) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-not-found',
          title: 'User Not Found',
          detail: `User with id '${params.userId as string}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}`,
        },
        { status: 404 }
      )
    }
    users.splice(index, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/v1/users/:userId/groups', ({ params, request }) => {
    const user = users.find((u) => u.id === params.userId)
    if (!user) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-not-found',
          title: 'User Not Found',
          detail: `User with id '${params.userId as string}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}/groups`,
        },
        { status: 404 }
      )
    }

    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20

    const memberGroupIds = userGroupMemberships[user.id] ?? []
    const userGroups = groups.filter((g) => memberGroupIds.includes(g.id))

    return HttpResponse.json(paginate(userGroups, cursor, limit, false))
  }),

  http.put('/api/v1/users/:userId/groups', async ({ params, request }) => {
    const user = users.find((u) => u.id === params.userId)
    if (!user) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-not-found',
          title: 'User Not Found',
          detail: `User with id '${params.userId as string}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}/groups`,
        },
        { status: 404 }
      )
    }

    const body = (await request.json()) as { group_ids?: string[] }
    userGroupMemberships[user.id] = body.group_ids ?? []

    const userGroups = groups.filter((g) => (body.group_ids ?? []).includes(g.id))
    return HttpResponse.json({ resources: userGroups, next: null, prev: null })
  }),

  // User identity handlers
  http.get('/api/v1/users/:userId/identities', ({ params }) => {
    const user = users.find((u) => u.id === params.userId)
    if (!user) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-not-found',
          title: 'User Not Found',
          detail: `User with id '${params.userId as string}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}/identities`,
        },
        { status: 404 }
      )
    }
    const identities = userIdentities.get(user.id) ?? []
    return HttpResponse.json({ resources: identities, next: null, prev: null, total: identities.length })
  }),

  http.post('/api/v1/users/:userId/identities', async ({ params, request }) => {
    const user = users.find((u) => u.id === params.userId)
    if (!user) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-not-found',
          title: 'User Not Found',
          detail: `User with id '${params.userId as string}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}/identities`,
        },
        { status: 404 }
      )
    }
    const body = (await request.json()) as { identity_id: string }

    // Find and move the identity from its current owner
    let found: UserIdentityRead | undefined
    for (const [ownerId, identities] of userIdentities.entries()) {
      const idx = identities.findIndex((i) => i.id === body.identity_id)
      if (idx !== -1) {
        found = identities[idx]
        identities.splice(idx, 1)
        if (identities.length === 0) userIdentities.delete(ownerId)
        break
      }
    }
    if (!found) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/identity-not-found',
          title: 'Identity Not Found',
          detail: `Identity with id '${body.identity_id}' not found`,
          code: 'IDENTITY_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}/identities`,
        },
        { status: 404 }
      )
    }

    const attached: UserIdentityRead = { ...found, user_id: user.id }
    const existing = userIdentities.get(user.id) ?? []
    existing.push(attached)
    userIdentities.set(user.id, existing)
    return HttpResponse.json(attached, { status: 201 })
  }),

  http.delete('/api/v1/users/:userId/identities/:identityId', ({ params }) => {
    const identities = userIdentities.get(params.userId as string)
    if (!identities) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/identity-not-found',
          title: 'Identity Not Found',
          detail: `Identity with id '${params.identityId as string}' not found`,
          code: 'IDENTITY_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}/identities/${params.identityId as string}`,
        },
        { status: 404 }
      )
    }
    const idx = identities.findIndex((i) => i.id === params.identityId)
    if (idx === -1) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/identity-not-found',
          title: 'Identity Not Found',
          detail: `Identity with id '${params.identityId as string}' not found`,
          code: 'IDENTITY_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}/identities/${params.identityId as string}`,
        },
        { status: 404 }
      )
    }
    identities.splice(idx, 1)
    if (identities.length === 0) userIdentities.delete(params.userId as string)
    return new HttpResponse(null, { status: 204 })
  }),

  // User role assignments
  http.get('/api/v1/users/:userId/role_assignments', ({ params }) => {
    const user = users.find((u) => u.id === params.userId)
    if (!user) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/not-found',
          title: 'User Not Found',
          detail: `User with id '${params.userId as string}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/users/${params.userId as string}/role_assignments`,
        },
        { status: 404 }
      )
    }
    const assignments = mockUserRoleAssignments
      .filter((a) => a.user_id === (params.userId as string))
      .map((a) => ({
        id: a.id,
        principal_id: a.user_id,
        principal_name: a.username,
        role_name: a.role_name,
        role_description: null,
        role_policies: [],
        project_id: null,
        project_name: null,
        created_at: a.created_at,
      }))
    return HttpResponse.json({ resources: assignments, total: assignments.length })
  }),

  // Directory handlers (lightweight id + username/name only)
  http.get('/api/v1/users/directory', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'

    let resources = users.map((u) => ({ id: u.id, username: u.username }))

    const usernameContains = url.searchParams.get('username[contains]')
    if (usernameContains) {
      const searchTerm = usernameContains.toLowerCase()
      resources = resources.filter((u) => u.username.toLowerCase().includes(searchTerm))
    }

    return HttpResponse.json(paginate(resources, cursor, limit, includeTotal))
  }),

  // Group handlers
  http.get('/api/v1/groups', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const sort = url.searchParams.get('sort')
    const nameContains = url.searchParams.get('name[contains]')

    let resources = [...groups]

    if (nameContains) {
      const searchTerm = nameContains.toLowerCase()
      resources = resources.filter((g) => (g.name ?? '').toLowerCase().includes(searchTerm))
    }

    const descContains = url.searchParams.get('description[contains]')
    if (descContains) {
      const searchTerm = descContains.toLowerCase()
      resources = resources.filter((g) => (g.description ?? '').toLowerCase().includes(searchTerm))
    }

    const createdByContains = url.searchParams.get('created_by_name[contains]')
    if (createdByContains) {
      const searchTerm = createdByContains.toLowerCase()
      resources = resources.filter((g) => {
        if (!g.created_by) return false
        const creator = users.find((u) => u.id === g.created_by)
        return creator?.username.toLowerCase().includes(searchTerm) ?? false
      })
    }

    if (sort) {
      const isDesc = sort.startsWith('-')
      const field = isDesc ? sort.slice(1) : sort
      resources.sort((a, b) => {
        let aVal = ''
        let bVal = ''
        switch (field) {
          case 'name':
            aVal = a.name ?? ''
            bVal = b.name ?? ''
            break
          case 'description':
            aVal = a.description ?? ''
            bVal = b.description ?? ''
            break
          case 'created_at':
            aVal = a.created_at ?? ''
            bVal = b.created_at ?? ''
            break
          case 'updated_at':
            aVal = a.updated_at ?? ''
            bVal = b.updated_at ?? ''
            break
          case 'created_by':
            aVal = a.created_by ?? ''
            bVal = b.created_by ?? ''
            break
          default:
            aVal = a.name ?? ''
            bVal = b.name ?? ''
        }
        const cmp = aVal.localeCompare(bVal)
        return isDesc ? -cmp : cmp
      })
    }

    return HttpResponse.json(paginate(resources, cursor, limit, includeTotal))
  }),

  http.get('/api/v1/groups/directory', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const nameFilter = url.searchParams.get('name[contains]')

    let resources = groups
      .filter((g): g is typeof g & { id: string; name: string } => !!g.id && !!g.name)
      .map((g) => ({ id: g.id, name: g.name }))

    if (nameFilter) {
      const searchTerm = nameFilter.toLowerCase()
      resources = resources.filter((g) => g.name.toLowerCase().includes(searchTerm))
    }

    return HttpResponse.json(paginate(resources, cursor, limit, includeTotal))
  }),

  http.post('/api/v1/groups', async ({ request }) => {
    const body = (await request.json()) as { name?: string; description?: string | null }

    const existing = groups.find((g) => g.name?.toLowerCase() === body.name?.toLowerCase())
    if (existing) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/group-name-conflict',
          title: 'Group Name Conflict',
          detail: `A group named "${body.name}" already exists.`,
          code: 'GROUP_NAME_CONFLICT',
          retryable: false,
          instance: '/api/v1/groups',
        },
        { status: 409 }
      )
    }

    const now = new Date().toISOString()
    const newGroup: GroupRead = {
      id: uuidv4(),
      name: body.name ?? '',
      description: body.description ?? null,
      is_builtin: false,
      created_by: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      created_at: now,
      updated_at: now,
      source: 'local',
      member_count: 0,
    }
    groups.push(newGroup)
    return HttpResponse.json(newGroup, { status: 201 })
  }),

  http.get('/api/v1/groups/:groupId', ({ params }) => {
    const group = groups.find((g) => g.id === params.groupId)
    if (!group) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/group-not-found',
          title: 'Group Not Found',
          detail: `Group with id '${params.groupId as string}' not found`,
          code: 'GROUP_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}`,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json(group)
  }),

  http.patch('/api/v1/groups/:groupId', async ({ params, request }) => {
    const group = groups.find((g) => g.id === params.groupId)
    if (!group) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/group-not-found',
          title: 'Group Not Found',
          detail: `Group with id '${params.groupId as string}' not found`,
          code: 'GROUP_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}`,
        },
        { status: 404 }
      )
    }

    const body = (await request.json()) as { name?: string; description?: string | null }

    if (body.name && body.name.toLowerCase() !== group.name?.toLowerCase()) {
      const conflict = groups.find((g) => g.id !== group.id && g.name?.toLowerCase() === body.name?.toLowerCase())
      if (conflict) {
        return HttpResponse.json(
          {
            type: 'https://api.example.com/errors/group-name-conflict',
            title: 'Group Name Conflict',
            detail: `A group named "${body.name}" already exists.`,
            code: 'GROUP_NAME_CONFLICT',
            retryable: false,
            instance: `/api/v1/groups/${params.groupId as string}`,
          },
          { status: 409 }
        )
      }
    }

    const index = groups.indexOf(group)
    const updated: GroupRead = {
      ...group,
      ...(body.name !== undefined && { name: body.name }),
      ...(body.description !== undefined && { description: body.description }),
      updated_at: new Date().toISOString(),
    }
    groups[index] = updated
    return HttpResponse.json(updated)
  }),

  http.delete('/api/v1/groups/:groupId', ({ params }) => {
    const index = groups.findIndex((g) => g.id === params.groupId)
    if (index === -1) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/group-not-found',
          title: 'Group Not Found',
          detail: `Group with id '${params.groupId as string}' not found`,
          code: 'GROUP_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}`,
        },
        { status: 404 }
      )
    }
    if (groups[index].is_builtin) {
      return HttpResponse.json({ detail: 'Cannot delete built-in group' }, { status: 403 })
    }
    groups.splice(index, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/v1/groups/:groupId/members', ({ params, request }) => {
    const group = groups.find((g) => g.id === params.groupId)
    if (!group) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/group-not-found',
          title: 'Group Not Found',
          detail: `Group with id '${params.groupId as string}' not found`,
          code: 'GROUP_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}/members`,
        },
        { status: 404 }
      )
    }

    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20

    const memberUserIds = Object.entries(userGroupMemberships)
      .filter(([, groupIds]) => groupIds.includes(group.id))
      .map(([userId]) => userId)
    const members = users.filter((u) => memberUserIds.includes(u.id))

    return HttpResponse.json(paginate(members, cursor, limit, false))
  }),

  http.post('/api/v1/groups/:groupId/members', async ({ params, request }) => {
    const group = groups.find((g) => g.id === params.groupId)
    if (!group) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/group-not-found',
          title: 'Group Not Found',
          detail: `Group with id '${params.groupId as string}' not found`,
          code: 'GROUP_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}/members`,
        },
        { status: 404 }
      )
    }

    const body = (await request.json()) as { user_id?: string }
    const user = users.find((u) => u.id === body.user_id)
    if (!user) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/user-not-found',
          title: 'User Not Found',
          detail: `User with id '${body.user_id ?? ''}' not found`,
          code: 'USER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}/members`,
        },
        { status: 404 }
      )
    }

    if (!userGroupMemberships[user.id]) {
      userGroupMemberships[user.id] = []
    }
    if (userGroupMemberships[user.id].includes(group.id)) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/member-conflict',
          title: 'Member Conflict',
          detail: 'User is already a member of this group',
          code: 'MEMBER_CONFLICT',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}/members`,
        },
        { status: 409 }
      )
    }
    userGroupMemberships[user.id].push(group.id)
    return HttpResponse.json({ message: 'Member added successfully' }, { status: 201 })
  }),

  http.delete('/api/v1/groups/:groupId/members/:userId', ({ params }) => {
    const group = groups.find((g) => g.id === params.groupId)
    if (!group) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/group-not-found',
          title: 'Group Not Found',
          detail: `Group with id '${params.groupId as string}' not found`,
          code: 'GROUP_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}/members/${params.userId as string}`,
        },
        { status: 404 }
      )
    }

    const userId = params.userId as string
    const memberGroupIds = userGroupMemberships[userId]
    if (!memberGroupIds || !memberGroupIds.includes(group.id)) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/member-not-found',
          title: 'Member Not Found',
          detail: 'User is not a member of this group',
          code: 'MEMBER_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${params.groupId as string}/members/${userId}`,
        },
        { status: 404 }
      )
    }
    userGroupMemberships[userId] = memberGroupIds.filter((id) => id !== group.id)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Group Role Assignments (nested under /groups/:groupId) ──────────────
  http.get('/api/v1/groups/:groupId/role_assignments', ({ params }) => {
    const groupId = params.groupId as string
    const group = groups.find((g) => g.id === groupId)
    if (!group) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/group-not-found',
          title: 'Group Not Found',
          detail: `Group with id '${groupId}' not found`,
          code: 'GROUP_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/groups/${groupId}/role_assignments`,
        },
        { status: 404 }
      )
    }

    const systemAssignments = mockGroupRoleAssignments
      .filter((a) => a.group_id === groupId)
      .map((a) => {
        const role = mockRoles.find((r) => r.id === a.role_id)
        return {
          id: a.id,
          principal_id: null,
          group_id: a.group_id,
          principal_name: a.group_name,
          role_name: a.role_name,
          role_description: role?.description ?? null,
          role_policies: role?.policies ?? [],
          project_id: null,
          project_name: null,
          created_at: a.created_at,
        }
      })

    const projectAssignments = mockProjectGroupRoleAssignments
      .filter((a) => a.group_id === groupId)
      .map((a) => {
        const role = mockRoles.find((r) => r.id === a.role_id)
        return {
          id: a.id,
          principal_id: null,
          group_id: a.group_id,
          principal_name: a.group_name,
          role_name: a.role_name,
          role_description: role?.description ?? null,
          role_policies: role?.policies ?? [],
          project_id: a.project_id,
          project_name: mockProjects.find((p) => p.id === a.project_id)?.name ?? null,
          created_at: a.created_at,
        }
      })

    const all = [...systemAssignments, ...projectAssignments]
    return HttpResponse.json({ resources: all, total: all.length, next: null, prev: null })
  }),

  // Credential handlers
  http.get('/api/v1/credentials', ({ request }) => {
    const url = new URL(request.url)
    const nameExact = url.searchParams.get('name')
    const nameContains = url.searchParams.get('name[contains]')
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'

    let resources = credentials

    if (nameExact) {
      resources = resources.filter((c) => c.name === nameExact)
    }
    if (nameContains) {
      const searchTerm = nameContains.toLowerCase()
      resources = resources.filter((c) => (c.name ?? '').toLowerCase().includes(searchTerm))
    }

    const credTypeId = url.searchParams.get('credential_type_id')
    if (credTypeId) {
      resources = resources.filter((c) => c.credential_type_id === credTypeId)
    }

    const projectId = url.searchParams.get('project_id')
    if (projectId) {
      resources = resources.filter((c) => c.project_id === projectId)
    }

    return HttpResponse.json(paginate(resources, cursor, limit, includeTotal))
  }),

  http.post('/api/v1/credentials', async (req) => {
    const body = (await req.request.json()) as {
      name: string
      description?: string | null
      credential_type_id: string
      inputs?: Record<string, unknown>
      project_id?: string
    }

    // Return existing credential for duplicate names (idempotency for parallel test workers)
    const existing = credentials.find((c) => c.name === body.name)
    if (existing) {
      return HttpResponse.json(redactCredential(existing), { status: 200 })
    }

    // Validate credential type exists
    const matchingType = credentialTypes.find((t) => t.id === body.credential_type_id)
    if (!matchingType) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/not-found',
          title: 'Not Found',
          detail: `Credential type '${body.credential_type_id}' not found`,
          code: 'NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }

    // Validate required fields from the type schema
    const typeInputs = matchingType.inputs as Record<string, unknown>
    const requiredFields = (typeInputs?.required as string[]) ?? []
    const providedInputs = body.inputs ?? {}
    const missingFields = requiredFields.filter((field) => !(field in providedInputs) || providedInputs[field] === '')
    if (missingFields.length > 0) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/validation-error',
          title: 'Validation Error',
          detail: `Missing required input fields: ${missingFields.join(', ')}`,
          code: 'VALIDATION_ERROR',
          retryable: false,
        },
        { status: 422 }
      )
    }

    const now = new Date().toISOString()
    const newCredential = {
      id: uuidv4(),
      name: body.name,
      description: body.description ?? null,
      credential_type_id: body.credential_type_id,
      inputs: JSON.parse(JSON.stringify(body.inputs ?? {})) as Record<string, unknown>,
      enabled: true,
      created_at: now,
      updated_at: now,
      created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-001' },
      labels: {},
      deleted_at: null,
      deleted_by: null,
      project_id: body.project_id,
    }
    credentials.push(newCredential)
    matchingType.credential_count = (matchingType.credential_count ?? 0) + 1

    return HttpResponse.json(redactCredential(newCredential), { status: 201 })
  }),

  http.get('/api/v1/credentials/:credential_id', (request) => {
    const { credential_id } = request.params as { credential_id: string }
    const credential = credentials.find((c) => c.id === credential_id)
    if (!credential) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Credential not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    return HttpResponse.json(redactCredential(credential))
  }),

  http.patch('/api/v1/credentials/:credential_id', async (request) => {
    const { credential_id } = request.params as { credential_id: string }
    const credential = credentials.find((c) => c.id === credential_id)
    if (!credential) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Credential not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const { name, description, inputs, enabled } = (await request.request.json()) as {
      name?: string
      description?: string | null
      inputs?: Record<string, unknown>
      enabled?: boolean
    }
    if (name != null) credential.name = name
    if (description !== undefined) credential.description = description
    if (inputs != null) {
      // JSON round-trip strips prototype properties at all nesting levels
      const sanitized = JSON.parse(JSON.stringify(inputs)) as Record<string, unknown>
      Object.assign(credential.inputs, sanitized)
    }
    if (enabled != null) credential.enabled = enabled
    ;(credential as { updated_at: string }).updated_at = new Date().toISOString()
    return HttpResponse.json(redactCredential(credential))
  }),

  http.delete('/api/v1/credentials/:credential_id', (request) => {
    const { credential_id } = request.params as { credential_id: string }
    const index = credentials.findIndex((c) => c.id === credential_id)
    if (index === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Credential not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    credentials.splice(index, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/v1/credentials/:credential_id/workflows', (request) => {
    const { credential_id } = request.params as { credential_id: string }
    const credential = credentials.find((c) => c.id === credential_id)
    if (!credential) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Credential not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    return HttpResponse.json({ resources: credentialWorkflows[credential_id] ?? [] })
  }),

  http.get('/api/v1/credential_types', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'

    return HttpResponse.json(paginate(credentialTypes, cursor, limit, includeTotal))
  }),

  http.get('/api/v1/credential_types/:credential_type_id', (request) => {
    const { credential_type_id } = request.params as { credential_type_id: string }
    const credType = credentialTypes.find((t) => t.id === credential_type_id)
    if (!credType) {
      return HttpResponse.json(
        {
          type: 'not-found',
          title: 'Not Found',
          detail: 'Credential type not found',
          code: 'NOT_FOUND',
          retryable: false,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json(credType)
  }),

  // File upload / metadata / download mock handlers
  http.post('/api/v1/files', async ({ request }) => {
    const formData = await request.formData()
    const files = formData.getAll('files').filter((entry): entry is File => entry instanceof File)

    const fileResponses = await Promise.all(
      files.map(async (file) => {
        const file_id = uuidv4()
        mockUploadedFiles.set(file_id, {
          filename: file.name,
          content: await file.arrayBuffer(),
          mime_type: file.type || 'application/octet-stream',
        })
        return {
          file_id,
          filename: file.name,
          size_bytes: file.size,
          mime_type: file.type || 'application/octet-stream',
          status: 'pending_conversion',
        }
      })
    )

    return HttpResponse.json({
      file_ids: fileResponses.map((f) => f.file_id),
      files: fileResponses,
    })
  }),

  // Mock deployments always have object storage available, so upload
  // controls stay enabled. Change to 'unconfigured' to exercise the
  // disabled-upload states.
  http.get('/api/v1/files/storage_status', () => HttpResponse.json({ status: 'ok' })),

  http.get('/api/v1/files/metadata', ({ request }) => {
    const url = new URL(request.url)
    const fileIds = url.searchParams.getAll('file_ids')
    const files = fileIds.map((id) => {
      const uploaded = mockUploadedFiles.get(id)
      if (uploaded) {
        return {
          file_id: id,
          filename: uploaded.filename,
          size_bytes: uploaded.content.byteLength,
          mime_type: uploaded.mime_type,
          status: 'ready',
        }
      }
      const known = knownFileMetadata[id]
      return {
        file_id: id,
        filename: known?.filename ?? `file-${id.slice(0, 8)}.txt`,
        size_bytes: known?.size_bytes ?? 1024,
        mime_type: known?.mime_type ?? 'text/plain',
        status: 'ready',
      }
    })
    return HttpResponse.json({ files })
  }),

  http.get('/api/v1/files/:file_id', ({ params }) => {
    const fileId = String(params.file_id)
    const uploaded = mockUploadedFiles.get(fileId)
    if (uploaded) {
      return HttpResponse.json({
        file_id: fileId,
        filename: uploaded.filename,
        size_bytes: uploaded.content.byteLength,
        mime_type: uploaded.mime_type,
        status: 'converted',
        conversion_error: null,
      })
    }
    const known = knownFileMetadata[fileId]
    if (known) {
      return HttpResponse.json({
        file_id: fileId,
        filename: known.filename,
        size_bytes: known.size_bytes,
        mime_type: known.mime_type ?? 'text/plain',
        status: 'converted',
        conversion_error: null,
      })
    }
    return new HttpResponse(null, { status: 404 })
  }),

  http.get('/api/v1/files/:file_id/download', ({ params }) => {
    const fileId = String(params.file_id)
    const uploaded = mockUploadedFiles.get(fileId)
    if (uploaded) {
      return new HttpResponse(uploaded.content, {
        status: 200,
        headers: {
          'Content-Type': uploaded.mime_type,
          'Content-Disposition': `attachment; filename="${uploaded.filename}"`,
        },
      })
    }

    const known = knownFileMetadata[fileId]
    if (known) {
      const body = `mock contents for ${known.filename}`
      return new HttpResponse(body, {
        status: 200,
        headers: {
          'Content-Type': known.mime_type,
          'Content-Disposition': `attachment; filename="${known.filename}"`,
        },
      })
    }

    return HttpResponse.json({ detail: 'File not found' }, { status: 404 })
  }),

  // Settings endpoints
  http.get('/api/v1/settings/categories', () => {
    return HttpResponse.json({ resources: settingsCategories })
  }),

  http.get('/api/v1/settings', ({ request }) => {
    const url = new URL(request.url)
    const category = url.searchParams.get('category')
    const group = url.searchParams.get('group')
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = parseInt(url.searchParams.get('limit') || '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20

    let filtered = settings
    if (category) filtered = filtered.filter((s) => s.category === category)
    if (group) filtered = filtered.filter((s) => s.group === group)

    const body = paginate(filtered, cursor, limit, false)
    return HttpResponse.json(body)
  }),

  http.get('/api/v1/settings/:key', (request) => {
    const key = request.params.key as string
    const setting = settings.find((s) => s.key === key)
    if (!setting) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/setting-not-found',
          title: 'Setting Not Found',
          detail: `Setting with key '${key}' not found`,
          code: 'SETTING_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/settings/${key}`,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json(setting)
  }),

  http.patch('/api/v1/settings', async (req) => {
    const body = (await req.request.json()) as {
      updates: Array<{ key: string; value: unknown; expected_version: number }>
    }
    const updated = []

    for (const update of body.updates) {
      const setting = settings.find((s) => s.key === update.key)
      if (!setting) {
        return HttpResponse.json(
          {
            type: 'https://api.example.com/errors/setting-not-found',
            title: 'Setting Not Found',
            detail: `Setting with key '${update.key}' not found`,
            code: 'SETTING_NOT_FOUND',
            retryable: false,
            instance: '/api/v1/settings',
          },
          { status: 404 }
        )
      }
      if (setting.version !== update.expected_version) {
        return HttpResponse.json(
          {
            type: 'https://api.example.com/errors/version-conflict',
            title: 'Version Conflict',
            detail: `Setting '${update.key}' has been modified (expected v${String(update.expected_version)}, current v${String(setting.version)})`,
            code: 'SETTING_VERSION_CONFLICT',
            retryable: false,
            instance: '/api/v1/settings',
          },
          { status: 409 }
        )
      }

      setting.value = update.value
      setting.effective_value = update.value
      setting.version += 1
      setting.updated_at = new Date().toISOString()
      updated.push(setting)
    }

    return HttpResponse.json(updated)
  }),

  http.patch('/api/v1/settings/:key', async (req) => {
    const key = req.params.key as string
    const setting = settings.find((s) => s.key === key)
    if (!setting) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/setting-not-found',
          title: 'Setting Not Found',
          detail: `Setting with key '${key}' not found`,
          code: 'SETTING_NOT_FOUND',
          retryable: false,
          instance: `/api/v1/settings/${key}`,
        },
        { status: 404 }
      )
    }

    const body = (await req.request.json()) as { value: unknown; expected_version: number }
    if (setting.version !== body.expected_version) {
      return HttpResponse.json(
        {
          type: 'https://api.example.com/errors/version-conflict',
          title: 'Version Conflict',
          detail: `Setting '${key}' has been modified (expected v${String(body.expected_version)}, current v${String(setting.version)})`,
          code: 'SETTING_VERSION_CONFLICT',
          retryable: false,
          instance: `/api/v1/settings/${key}`,
        },
        { status: 409 }
      )
    }

    setting.value = body.value
    setting.effective_value = body.value
    setting.version += 1
    setting.updated_at = new Date().toISOString()
    return HttpResponse.json(setting)
  }),

  // ── Access Management: Projects ─────────────────────────────────────────

  http.get('/api/v1/projects', ({ request }) => {
    const url = new URL(request.url)
    // Support both plain 'name' (eq) and 'name[contains]' (FilterBar chip format)
    const nameContains = url.searchParams.get('name') ?? url.searchParams.get('name[contains]')
    const isDefault = url.searchParams.get('is_default')
    const isBuiltin = url.searchParams.get('is_builtin')
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'
    // Match backend ProjectService default: sort or "-created_at"
    const sort = url.searchParams.get('sort') ?? '-created_at'

    let resources = [...mockProjects]

    if (nameContains) {
      const term = nameContains.toLowerCase()
      resources = resources.filter((p) => p.name.toLowerCase().includes(term))
    }

    if (isDefault !== null) {
      resources = resources.filter((p) => p.is_default === (isDefault === 'true'))
    }

    if (isBuiltin !== null) {
      resources = resources.filter((p) => p.is_builtin === (isBuiltin === 'true'))
    }

    const isDesc = sort.startsWith('-')
    const field = (isDesc ? sort.slice(1) : sort) as keyof (typeof resources)[0]
    resources.sort((a, b) => {
      const aVal = String(a[field] ?? '')
      const bVal = String(b[field] ?? '')
      const cmp = aVal.localeCompare(bVal)
      return isDesc ? -cmp : cmp
    })

    const body = paginate(resources, cursor, limit, includeTotal)
    return HttpResponse.json(body)
  }),

  http.post('/api/v1/projects', async ({ request }) => {
    const body = (await request.json()) as { name: string; description?: string; labels?: Record<string, string> }
    const now = new Date().toISOString()
    const project = {
      id: uuidv4(),
      name: body.name,
      description: body.description ?? null,
      labels: body.labels ?? {},
      is_default: false,
      is_builtin: false,
      created_at: now,
      updated_at: now,
    }
    mockProjects.push(project)
    return HttpResponse.json(project, { status: 201 })
  }),

  http.get('/api/v1/projects/:project_id', ({ params }) => {
    const project = mockProjects.find((p) => p.id === params.project_id)
    if (!project) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Project not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    return HttpResponse.json(project)
  }),

  http.patch('/api/v1/projects/:project_id', async ({ params, request }) => {
    const project = mockProjects.find((p) => p.id === params.project_id)
    if (!project) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Project not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const body = (await request.json()) as { name?: string; description?: string; labels?: Record<string, string> }
    if (body.name !== undefined) project.name = body.name
    if (body.description !== undefined) project.description = body.description
    if (body.labels !== undefined) project.labels = body.labels
    project.updated_at = new Date().toISOString()
    return HttpResponse.json(project)
  }),

  http.delete('/api/v1/projects/:project_id', ({ params }) => {
    const idx = mockProjects.findIndex((p) => p.id === params.project_id)
    if (idx === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Project not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    mockProjects.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Project-scoped workflows ────────────────────────────────────────────
  http.get('/api/v1/projects/:project_id/workflows', ({ params, request }) => {
    const url = new URL(request.url)
    const projectId = params.project_id as string
    const nameStartsWith = url.searchParams.get('name[starts_with]')
    const nameContains = url.searchParams.get('name[contains]')
    const isEnabled = url.searchParams.get('is_enabled')
    const cursor = url.searchParams.get('cursor')
    const parsedLimit = Number.parseInt(url.searchParams.get('limit') ?? '20', 10)
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20
    const includeTotal = url.searchParams.get('include_total') === 'true'

    // Filter by project
    let resources = workflows.filter((w) => w.project_id === projectId)

    // Apply name filters
    if (nameStartsWith) {
      const prefix = nameStartsWith.toLowerCase()
      resources = resources.filter((w) => (w.name ?? '').toLowerCase().startsWith(prefix))
    }
    if (nameContains) {
      const searchTerm = nameContains.toLowerCase()
      resources = resources.filter((w) => (w.name ?? '').toLowerCase().includes(searchTerm))
    }

    // Apply is_enabled filter
    if (isEnabled !== null) {
      const enabled = isEnabled === 'true'
      resources = resources.filter((w) => w.is_enabled === enabled)
    }

    const body: WorkflowsResponse = paginate(resources, cursor, limit, includeTotal)
    return HttpResponse.json(body)
  }),

  // ── Access Management: Project Role Assignments ─────────────────────────

  http.get('/api/v1/projects/:project_id/role_assignments', ({ params }) => {
    const pid = params.project_id as string

    const userEntries = mockProjectRoleAssignments
      .filter((a) => a.project_id === pid)
      .map((a) => ({
        id: a.id,
        principal_id: a.user_id,
        group_id: null,
        principal_name: a.username,
        principal_type: 'user' as const,
        role_name: a.role_name,
        role_policies: mockRoles.find((r) => r.name === a.role_name)?.policies ?? [],
        project_id: a.project_id,
        created_at: a.created_at,
      }))

    const groupEntries = mockProjectGroupRoleAssignments
      .filter((a) => a.project_id === pid)
      .map((a) => ({
        id: a.id,
        principal_id: null,
        group_id: a.group_id,
        principal_name: a.group_name,
        principal_type: 'group' as const,
        role_name: a.role_name,
        role_policies: mockRoles.find((r) => r.name === a.role_name)?.policies ?? [],
        project_id: a.project_id,
        created_at: a.created_at,
      }))

    const saEntries = mockServiceAccountRoleAssignments
      .filter((a) => a.project_id === pid)
      .map((a) => ({
        id: a.id,
        principal_id: a.service_account_id,
        group_id: null,
        principal_name: a.service_account_name,
        principal_type: 'service_account' as const,
        role_name: a.role_name,
        role_policies: mockRoles.find((r) => r.name === a.role_name)?.policies ?? [],
        project_id: a.project_id,
        created_at: a.created_at,
      }))

    return HttpResponse.json({ resources: [...userEntries, ...groupEntries, ...saEntries] })
  }),

  http.post('/api/v1/projects/:project_id/role_assignments', async ({ params, request }) => {
    const body = (await request.json()) as { principal_id?: string; group_id?: string; role_name: string }
    const projectId = params.project_id as string

    if (body.group_id) {
      const assignment = {
        id: uuidv4(),
        group_id: body.group_id,
        group_name: groups.find((g) => g.id === body.group_id)?.name ?? body.group_id,
        project_id: projectId,
        role_name: body.role_name,
        created_at: new Date().toISOString(),
      }
      mockProjectGroupRoleAssignments.push(assignment)
      return HttpResponse.json(
        {
          id: assignment.id,
          principal_id: null,
          group_id: assignment.group_id,
          principal_name: assignment.group_name,
          role_name: assignment.role_name,
          project_id: assignment.project_id,
          created_at: assignment.created_at,
        },
        { status: 201 }
      )
    }

    const principalId = body.principal_id!
    const assignment = {
      id: uuidv4(),
      user_id: principalId,
      username: users.find((u) => u.id === principalId)?.username ?? principalId,
      project_id: projectId,
      role_name: body.role_name,
      created_at: new Date().toISOString(),
    }
    mockProjectRoleAssignments.push(assignment)
    return HttpResponse.json(
      {
        id: assignment.id,
        principal_id: assignment.user_id,
        group_id: null,
        principal_name: assignment.username,
        role_name: assignment.role_name,
        project_id: assignment.project_id,
        created_at: assignment.created_at,
      },
      { status: 201 }
    )
  }),

  http.delete('/api/v1/projects/:project_id/role_assignments/:assignment_id', ({ params }) => {
    const assignmentId = params.assignment_id as string
    const projectId = params.project_id as string

    const userIdx = mockProjectRoleAssignments.findIndex((a) => a.id === assignmentId && a.project_id === projectId)
    if (userIdx !== -1) {
      mockProjectRoleAssignments.splice(userIdx, 1)
      return new HttpResponse(null, { status: 204 })
    }

    const groupIdx = mockProjectGroupRoleAssignments.findIndex(
      (a) => a.id === assignmentId && a.project_id === projectId
    )
    if (groupIdx !== -1) {
      mockProjectGroupRoleAssignments.splice(groupIdx, 1)
      return new HttpResponse(null, { status: 204 })
    }

    return HttpResponse.json(
      { type: 'not-found', title: 'Not Found', detail: 'Assignment not found', code: 'NOT_FOUND', retryable: false },
      { status: 404 }
    )
  }),

  // ── Access Management: Project Group Role Assignments ───────────────────

  http.get('/api/v1/projects/:project_id/group_role_assignments', ({ params }) => {
    const assignments = mockProjectGroupRoleAssignments.filter((a) => a.project_id === params.project_id)
    return HttpResponse.json(assignments)
  }),

  http.post('/api/v1/projects/:project_id/group_role_assignments', async ({ params, request }) => {
    const body = (await request.json()) as { group_id: string; role_name: string }
    const assignment = {
      id: uuidv4(),
      group_id: body.group_id,
      group_name: groups.find((g) => g.id === body.group_id)?.name ?? body.group_id,
      project_id: params.project_id as string,
      role_name: body.role_name,
      created_at: new Date().toISOString(),
    }
    mockProjectGroupRoleAssignments.push(assignment)
    return HttpResponse.json(assignment, { status: 201 })
  }),

  http.delete('/api/v1/projects/:project_id/group_role_assignments/:assignment_id', ({ params }) => {
    const idx = mockProjectGroupRoleAssignments.findIndex(
      (a) => a.id === params.assignment_id && a.project_id === params.project_id
    )
    if (idx === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Assignment not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    mockProjectGroupRoleAssignments.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Access Management: Project-scoped Roles (CRUD) ─────────────────────

  http.get('/api/v1/projects/:project_id/roles', ({ params, request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'

    const projectId = params.project_id as string
    let filtered = mockRoles.filter((r) => r.project_id === projectId)

    filtered = filterByPolicyName(filtered, url)

    return HttpResponse.json(paginate(filtered, cursor, limit, includeTotal))
  }),

  http.post('/api/v1/projects/:project_id/roles', async ({ params, request }) => {
    const body = (await request.json()) as { name: string; description?: string; policies: string[] }
    const projectId = params.project_id as string

    if (mockRoles.some((r) => r.name === body.name && r.project_id === projectId)) {
      return HttpResponse.json(
        {
          type: 'conflict',
          title: 'Conflict',
          detail: `Role with name '${body.name}' already exists in this project`,
          code: 'ROLE_NAME_CONFLICT',
          retryable: false,
        },
        { status: 409 }
      )
    }

    const now = new Date().toISOString()
    const role = {
      id: uuidv4(),
      name: body.name,
      description: body.description ?? null,
      policies: body.policies,
      is_builtin: false,
      project_id: projectId,
      labels: {},
      created_at: now,
      updated_at: now,
    }
    mockRoles.push(role)
    return HttpResponse.json(role, { status: 201 })
  }),

  http.get('/api/v1/projects/:project_id/roles/:role_id', ({ params }) => {
    const role = mockRoles.find((r) => r.id === params.role_id && r.project_id === params.project_id)
    if (!role) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Role not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    return HttpResponse.json(role)
  }),

  http.patch('/api/v1/projects/:project_id/roles/:role_id', async ({ params, request }) => {
    const idx = mockRoles.findIndex((r) => r.id === params.role_id && r.project_id === params.project_id)
    if (idx === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Role not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const body = (await request.json()) as { name?: string; description?: string; policies?: string[] }
    mockRoles[idx] = {
      ...mockRoles[idx],
      ...(body.name !== undefined && { name: body.name }),
      ...(body.description !== undefined && { description: body.description }),
      ...(body.policies !== undefined && { policies: body.policies }),
      updated_at: new Date().toISOString(),
    }
    return HttpResponse.json(mockRoles[idx])
  }),

  http.delete('/api/v1/projects/:project_id/roles/:role_id', ({ params }) => {
    const idx = mockRoles.findIndex((r) => r.id === params.role_id && r.project_id === params.project_id)
    if (idx === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Role not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    mockRoles.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Access Management: Project-scoped Policies (CRUD) ──────────────────

  http.get('/api/v1/projects/:project_id/policies', ({ params, request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'

    const projectId = params.project_id as string
    const filtered = mockPolicies.filter((p) => p.project_id === projectId || p.project_id === null)

    return HttpResponse.json(paginate(filtered, cursor, limit, includeTotal))
  }),

  http.post('/api/v1/projects/:project_id/policies', async ({ params, request }) => {
    const body = (await request.json()) as { name: string; description?: string; statements: unknown[] }
    const projectId = params.project_id as string

    if (mockPolicies.some((p) => p.name === body.name && p.project_id === projectId)) {
      return HttpResponse.json(
        {
          type: 'conflict',
          title: 'Conflict',
          detail: `Policy with name '${body.name}' already exists in this project`,
          code: 'POLICY_NAME_CONFLICT',
          retryable: false,
        },
        { status: 409 }
      )
    }

    const now = new Date().toISOString()
    const policy = {
      id: uuidv4(),
      name: body.name,
      description: body.description ?? null,
      is_builtin: false,
      is_project_eligible: true,
      scope: 'project' as const,
      project_id: projectId,
      created_at: now,
      updated_at: now,
    }
    mockPolicies.push(policy)
    return HttpResponse.json(policy, { status: 201 })
  }),

  http.get('/api/v1/projects/:project_id/policies/:policy_id', ({ params }) => {
    const policy = mockPolicies.find(
      (p) => p.id === params.policy_id && (p.project_id === params.project_id || p.project_id === null)
    )
    if (!policy) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Policy not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    return HttpResponse.json(policy)
  }),

  http.patch('/api/v1/projects/:project_id/policies/:policy_id', async ({ params, request }) => {
    const idx = mockPolicies.findIndex((p) => p.id === params.policy_id && p.project_id === params.project_id)
    if (idx === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Policy not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    const body = (await request.json()) as { name?: string; description?: string }
    mockPolicies[idx] = {
      ...mockPolicies[idx],
      ...(body.name !== undefined && { name: body.name }),
      ...(body.description !== undefined && { description: body.description }),
      updated_at: new Date().toISOString(),
    }
    return HttpResponse.json(mockPolicies[idx])
  }),

  http.delete('/api/v1/projects/:project_id/policies/:policy_id', ({ params }) => {
    const idx = mockPolicies.findIndex((p) => p.id === params.policy_id && p.project_id === params.project_id)
    if (idx === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Policy not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    mockPolicies.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Access Management: Policies (read-only) ─────────────────────────────

  http.get('/api/v1/policies', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const nameContains = url.searchParams.get('name[contains]')

    let filtered = [...mockPolicies]

    if (nameContains) {
      const term = nameContains.toLowerCase()
      filtered = filtered.filter((p) => p.name.toLowerCase().includes(term))
    }

    const descContains = url.searchParams.get('description[contains]')
    if (descContains) {
      const term = descContains.toLowerCase()
      filtered = filtered.filter((p) => (p.description ?? '').toLowerCase().includes(term))
    }

    const projectEligible = url.searchParams.get('project_eligible')
    if (projectEligible === 'true') {
      // Return only system (builtin) policies whose actions are valid for project-scoped roles
      const projectActionPrefixes = ['workflow:', 'execution:', 'approval:', 'project-role:', 'audit:']
      filtered = filtered.filter(
        (p) =>
          p.is_builtin && p.project_id === null && projectActionPrefixes.some((prefix) => p.name.startsWith(prefix))
      )
    }

    const isBuiltin = url.searchParams.get('is_builtin')
    if (isBuiltin !== null) {
      const builtin = isBuiltin === 'true'
      filtered = filtered.filter((p) => p.is_builtin === builtin)
    }

    const scopeEq = url.searchParams.get('scope')
    if (scopeEq) {
      filtered = filtered.filter((p) => p.scope === scopeEq)
    }

    const projectIdEq = url.searchParams.get('project_id')
    if (projectIdEq) {
      filtered = filtered.filter((p) => p.project_id === projectIdEq)
    }

    const sort = url.searchParams.get('sort')
    if (sort) {
      const isDesc = sort.startsWith('-')
      const field = isDesc ? sort.slice(1) : sort
      filtered.sort((a, b) => {
        let cmp = 0
        switch (field) {
          case 'name':
            cmp = a.name.localeCompare(b.name)
            break
          case 'description':
            cmp = (a.description ?? '').localeCompare(b.description ?? '')
            break
          case 'scope':
            cmp = a.scope.localeCompare(b.scope)
            break
          case 'project_id':
            cmp = (a.project_id ?? '').localeCompare(b.project_id ?? '')
            break
          case 'is_builtin':
            cmp = Number(a.is_builtin) - Number(b.is_builtin)
            break
          default:
            cmp = a.name.localeCompare(b.name)
        }
        return isDesc ? -cmp : cmp
      })
    }

    return HttpResponse.json(paginate(filtered, cursor, limit, includeTotal))
  }),

  // ── Access Management: Roles ────────────────────────────────────────────

  http.get('/api/v1/roles', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const nameContains = url.searchParams.get('name[contains]')

    let filtered = [...mockRoles]

    if (nameContains) {
      const term = nameContains.toLowerCase()
      filtered = filtered.filter((r) => r.name.toLowerCase().includes(term))
    }

    const descContains = url.searchParams.get('description[contains]')
    if (descContains) {
      const term = descContains.toLowerCase()
      filtered = filtered.filter((r) => (r.description ?? '').toLowerCase().includes(term))
    }

    const isBuiltin = url.searchParams.get('is_builtin')
    if (isBuiltin !== null) {
      const builtin = isBuiltin === 'true'
      filtered = filtered.filter((r) => r.is_builtin === builtin)
    }

    filtered = filterByPolicyName(filtered, url)

    const sort = url.searchParams.get('sort')
    if (sort) {
      const isDesc = sort.startsWith('-')
      const field = isDesc ? sort.slice(1) : sort
      filtered.sort((a, b) => {
        let cmp = 0
        switch (field) {
          case 'name':
            cmp = a.name.localeCompare(b.name)
            break
          case 'is_builtin':
            cmp = Number(a.is_builtin) - Number(b.is_builtin)
            break
          default:
            cmp = a.name.localeCompare(b.name)
        }
        return isDesc ? -cmp : cmp
      })
    }

    return HttpResponse.json(paginate(filtered, cursor, limit, includeTotal))
  }),

  http.post('/api/v1/roles', async ({ request }) => {
    const body = (await request.json()) as { name: string; description?: string; policies: string[] }
    if (mockRoles.some((r) => r.name === body.name)) {
      return HttpResponse.json(
        {
          type: 'conflict',
          title: 'Conflict',
          detail: `Role with name '${body.name}' already exists`,
          code: 'ROLE_NAME_CONFLICT',
          retryable: false,
        },
        { status: 409 }
      )
    }
    const role = {
      id: uuidv4(),
      name: body.name,
      description: body.description ?? null,
      policies: body.policies,
      is_builtin: false,
      project_id: null,
      labels: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    mockRoles.push(role)
    return HttpResponse.json(role, { status: 201 })
  }),

  http.put('/api/v1/roles/:role_id', async ({ params, request }) => {
    const { role_id } = params as { role_id: string }
    const idx = mockRoles.findIndex((r) => r.id === role_id)
    if (idx === -1) {
      return HttpResponse.json({ detail: 'Role not found' }, { status: 404 })
    }
    if (mockRoles[idx].is_builtin) {
      return HttpResponse.json({ detail: 'Cannot modify built-in role' }, { status: 403 })
    }
    const body = (await request.json()) as { name?: string; description?: string; policies?: string[] }
    if (body.name && body.name !== mockRoles[idx].name && mockRoles.some((r) => r.name === body.name)) {
      return HttpResponse.json(
        {
          type: 'conflict',
          title: 'Conflict',
          detail: `Role with name '${body.name}' already exists`,
          code: 'ROLE_NAME_CONFLICT',
          retryable: false,
        },
        { status: 409 }
      )
    }
    mockRoles[idx] = {
      ...mockRoles[idx],
      ...(body.name !== undefined && { name: body.name }),
      ...(body.description !== undefined && { description: body.description }),
      ...(body.policies !== undefined && { policies: body.policies }),
      updated_at: new Date().toISOString(),
    }
    return HttpResponse.json(mockRoles[idx])
  }),

  http.delete('/api/v1/roles/:role_id', ({ params }) => {
    const { role_id } = params as { role_id: string }
    const idx = mockRoles.findIndex((r) => r.id === role_id)
    if (idx === -1) {
      return HttpResponse.json({ detail: 'Role not found' }, { status: 404 })
    }
    if (mockRoles[idx].is_builtin) {
      return HttpResponse.json({ detail: 'Cannot delete built-in role' }, { status: 403 })
    }
    mockRoles.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Access Management: System-level User Role Assignments ───────────────

  http.get('/api/v1/user_role_assignments', () => {
    return HttpResponse.json(mockUserRoleAssignments)
  }),

  http.post('/api/v1/user_role_assignments', async ({ request }) => {
    const body = (await request.json()) as { user_id: string; role_id: string }
    const assignment = {
      id: uuidv4(),
      user_id: body.user_id,
      username: getUserName(body.user_id),
      role_id: body.role_id,
      role_name: getRoleName(body.role_id),
      created_at: new Date().toISOString(),
    }
    mockUserRoleAssignments.push(assignment)
    return HttpResponse.json(assignment, { status: 201 })
  }),

  http.delete('/api/v1/user_role_assignments/:assignment_id', ({ params }) => {
    const idx = mockUserRoleAssignments.findIndex((a) => a.id === params.assignment_id)
    if (idx === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Assignment not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    mockUserRoleAssignments.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Access Management: System-level Group Role Assignments ──────────────

  http.get('/api/v1/group_role_assignments', () => {
    return HttpResponse.json(mockGroupRoleAssignments)
  }),

  http.post('/api/v1/group_role_assignments', async ({ request }) => {
    const body = (await request.json()) as { group_id: string; role_id: string }
    const assignment = {
      id: uuidv4(),
      group_id: body.group_id,
      group_name: getGroupName(body.group_id),
      role_id: body.role_id,
      role_name: getRoleName(body.role_id),
      created_at: new Date().toISOString(),
    }
    mockGroupRoleAssignments.push(assignment)
    return HttpResponse.json(assignment, { status: 201 })
  }),

  http.delete('/api/v1/group_role_assignments/:assignment_id', ({ params }) => {
    const idx = mockGroupRoleAssignments.findIndex((a) => a.id === params.assignment_id)
    if (idx === -1) {
      return HttpResponse.json(
        { type: 'not-found', title: 'Not Found', detail: 'Assignment not found', code: 'NOT_FOUND', retryable: false },
        { status: 404 }
      )
    }
    mockGroupRoleAssignments.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Access Management: Role Assignments (policy-driven) ────────────────

  http.get('/api/v1/role_assignments', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const principalId = url.searchParams.get('principal_id')
    const groupId = url.searchParams.get('group_id')
    // UI sends operator-suffixed keys via buildFilterParams (e.g. principal_name[contains]).
    // Also accept the bare keys for older clients / direct queries.
    const principalName = url.searchParams.get('principal_name[contains]') ?? url.searchParams.get('principal_name')
    const roleName = url.searchParams.get('role_name[contains]') ?? url.searchParams.get('role_name')
    const projectId = url.searchParams.get('project_id')
    const principalType = url.searchParams.get('principal_type')

    // Build unified list from all sources
    const userEntries = mockUserRoleAssignments.map((a) => {
      const role = mockRoles.find((r) => r.name === a.role_name)
      return {
        id: a.id,
        principal_id: a.user_id,
        group_id: null,
        principal_name: a.username,
        principal_type: 'user' as const,
        role_name: a.role_name,
        role_description: role?.description ?? null,
        role_policies: role?.policies ?? [],
        project_id: null,
        project_name: null,
        created_at: a.created_at,
      }
    })

    const groupEntries = mockGroupRoleAssignments.map((a) => {
      const role = mockRoles.find((r) => r.name === a.role_name)
      return {
        id: a.id,
        principal_id: null,
        group_id: a.group_id,
        principal_name: a.group_name,
        principal_type: 'group' as const,
        role_name: a.role_name,
        role_description: role?.description ?? null,
        role_policies: role?.policies ?? [],
        project_id: null,
        project_name: null,
        created_at: a.created_at,
      }
    })

    const projectUserEntries = mockProjectRoleAssignments.map((a) => {
      const role = mockRoles.find((r) => r.name === a.role_name)
      return {
        id: a.id,
        principal_id: a.user_id,
        group_id: null,
        principal_name: a.username,
        principal_type: 'user' as const,
        role_name: a.role_name,
        role_description: role?.description ?? null,
        role_policies: role?.policies ?? [],
        project_id: a.project_id,
        project_name: mockProjects.find((p) => p.id === a.project_id)?.name ?? null,
        created_at: a.created_at,
      }
    })

    const projectGroupEntries = mockProjectGroupRoleAssignments.map((a) => {
      const role = mockRoles.find((r) => r.name === a.role_name)
      return {
        id: a.id,
        principal_id: null,
        group_id: a.group_id,
        principal_name: a.group_name,
        principal_type: 'group' as const,
        role_name: a.role_name,
        role_description: role?.description ?? null,
        role_policies: role?.policies ?? [],
        project_id: a.project_id,
        project_name: mockProjects.find((p) => p.id === a.project_id)?.name ?? null,
        created_at: a.created_at,
      }
    })

    const saEntries = mockServiceAccountRoleAssignments.map((a) => {
      const role = mockRoles.find((r) => r.name === a.role_name)
      return {
        id: a.id,
        principal_id: a.service_account_id,
        group_id: null,
        principal_name: a.service_account_name,
        principal_type: 'service_account' as const,
        role_name: a.role_name,
        role_description: role?.description ?? null,
        role_policies: role?.policies ?? [],
        project_id: a.project_id,
        project_name: mockProjects.find((p) => p.id === a.project_id)?.name ?? null,
        created_at: a.created_at,
      }
    })

    let all = [...userEntries, ...groupEntries, ...projectUserEntries, ...projectGroupEntries, ...saEntries]

    // Apply filters
    if (principalId) all = all.filter((a) => a.principal_id === principalId)
    if (groupId != null) {
      all = all.filter((a) => a.group_id === groupId)
    }
    if (principalName) {
      const needle = principalName.toLowerCase()
      all = all.filter((a) => a.principal_name.toLowerCase().includes(needle))
    }
    if (roleName) {
      const needle = roleName.toLowerCase()
      all = all.filter((a) => a.role_name.toLowerCase().includes(needle))
    }
    if (projectId) all = all.filter((a) => a.project_id === projectId)
    if (principalType) all = all.filter((a) => a.principal_type === principalType)

    return HttpResponse.json(paginate(all, cursor, limit, includeTotal))
  }),

  // ── Access Management: All Role Assignments (unified view) ─────────────

  http.get('/api/v1/all_role_assignments', ({ request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const groupId = url.searchParams.get('group_id')
    const principalName = url.searchParams.get('principal_name')
    const roleName = url.searchParams.get('role_name')
    const projectId = url.searchParams.get('project_id')

    const userEntries = mockUserRoleAssignments.map((a) => ({
      id: a.id,
      principal_id: a.user_id,
      group_id: null,
      principal_name: a.username,
      role_name: a.role_name,
      project_id: null,
      project_name: null,
      created_at: a.created_at,
    }))

    const groupEntries = mockGroupRoleAssignments.map((a) => ({
      id: a.id,
      principal_id: null,
      group_id: a.group_id,
      principal_name: a.group_name,
      role_name: a.role_name,
      project_id: null,
      project_name: null,
      created_at: a.created_at,
    }))

    const projectUserEntries = mockProjectRoleAssignments.map((a) => ({
      id: a.id,
      principal_id: a.user_id,
      group_id: null,
      principal_name: a.username,
      role_name: a.role_name,
      project_id: a.project_id,
      project_name: mockProjects.find((p) => p.id === a.project_id)?.name ?? null,
      created_at: a.created_at,
    }))

    const projectGroupEntries = mockProjectGroupRoleAssignments.map((a) => ({
      id: a.id,
      principal_id: null,
      group_id: a.group_id,
      principal_name: a.group_name,
      role_name: a.role_name,
      project_id: a.project_id,
      project_name: mockProjects.find((p) => p.id === a.project_id)?.name ?? null,
      created_at: a.created_at,
    }))

    let all = [...userEntries, ...groupEntries, ...projectUserEntries, ...projectGroupEntries]

    if (groupId != null) {
      all = all.filter((a) => a.group_id === groupId)
    }
    if (principalName) all = all.filter((a) => a.principal_name.includes(principalName))
    if (roleName) all = all.filter((a) => a.role_name.includes(roleName))
    if (projectId) all = all.filter((a) => a.project_id === projectId)

    return HttpResponse.json(paginate(all, cursor, limit, includeTotal))
  }),

  http.get('/api/v1/projects/:project_id/all_role_assignments', ({ params, request }) => {
    const url = new URL(request.url)
    const cursor = url.searchParams.get('cursor')
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const includeTotal = url.searchParams.get('include_total') === 'true'
    const groupId = url.searchParams.get('group_id')
    const principalName = url.searchParams.get('principal_name')
    const roleName = url.searchParams.get('role_name')

    const pid = params.project_id as string

    const userEntries = mockProjectRoleAssignments
      .filter((a) => a.project_id === pid)
      .map((a) => ({
        id: a.id,
        principal_id: a.user_id,
        group_id: null,
        principal_name: a.username,
        role_name: a.role_name,
        project_id: a.project_id,
        project_name: mockProjects.find((p) => p.id === a.project_id)?.name ?? null,
        created_at: a.created_at,
      }))

    const groupEntries = mockProjectGroupRoleAssignments
      .filter((a) => a.project_id === pid)
      .map((a) => ({
        id: a.id,
        principal_id: null,
        group_id: a.group_id,
        principal_name: a.group_name,
        role_name: a.role_name,
        project_id: a.project_id,
        project_name: mockProjects.find((p) => p.id === a.project_id)?.name ?? null,
        created_at: a.created_at,
      }))

    let all = [...userEntries, ...groupEntries]

    if (groupId != null) {
      all = all.filter((a) => a.group_id === groupId)
    }
    if (principalName) all = all.filter((a) => a.principal_name.includes(principalName))
    if (roleName) all = all.filter((a) => a.role_name.includes(roleName))

    return HttpResponse.json(paginate(all, cursor, limit, includeTotal))
  }),

  // ── Access Management: Users (for display in dropdowns) ─────────────────

  http.get('/api/v1/users', () => {
    return HttpResponse.json(mockUsers)
  }),

  // ── Access Management: Groups (for display in dropdowns) ────────────────

  http.get('/api/v1/groups', () => {
    return HttpResponse.json(mockGroups)
  }),

  // ── AAP proxy endpoints ──────────────────────────────────────────────
  http.get('*/proxies/aap/organizations', ({ request }) => {
    const url = new URL(request.url)
    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    const search = url.searchParams.get('search')?.toLowerCase()

    const filtered = search ? organizations.filter((o) => o.name.toLowerCase().includes(search)) : organizations
    return HttpResponse.json({ count: filtered.length, results: filtered })
  }),

  http.get('*/proxies/aap/job_templates/:id', ({ params, request }) => {
    const url = new URL(request.url)
    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    const id = Number(params.id)
    const template = jobTemplates.find((t) => t.id === id)
    if (!template) {
      return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    }
    const flags = jobTemplateDetails[id] ?? {}
    return HttpResponse.json({
      id: template.id,
      name: template.name,
      description: template.description,
      url: `https://aap.example.com/execution/templates/job-template/${id}/details`,
      ask_job_type_on_launch: false,
      ask_inventory_on_launch: false,
      ask_credential_on_launch: false,
      ask_variables_on_launch: false,
      ask_limit_on_launch: false,
      ask_tags_on_launch: false,
      ask_skip_tags_on_launch: false,
      ask_verbosity_on_launch: false,
      ask_diff_mode_on_launch: false,
      ask_forks_on_launch: false,
      ask_job_slice_count_on_launch: false,
      ask_execution_environment_on_launch: false,
      ask_instance_groups_on_launch: false,
      ask_labels_on_launch: false,
      ask_timeout_on_launch: false,
      survey_enabled: false,
      ...flags,
    })
  }),

  http.get('*/proxies/aap/job_templates', ({ request }) => {
    const url = new URL(request.url)
    const org = url.searchParams.get('organization')
    const search = url.searchParams.get('search')?.toLowerCase()

    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    let filtered = org ? jobTemplates.filter((t) => t.organization === org) : jobTemplates
    if (search) {
      filtered = filtered.filter((t) => t.name.toLowerCase().includes(search))
    }
    return HttpResponse.json({ count: filtered.length, results: filtered })
  }),

  http.get('*/proxies/aap/workflow_job_templates/:id', ({ params, request }) => {
    const url = new URL(request.url)
    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    const id = Number(params.id)
    const template = workflowTemplates.find((t) => t.id === id)
    if (!template) {
      return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    }
    const flags = workflowTemplateDetails[id] ?? {}
    return HttpResponse.json({
      id: template.id,
      name: template.name,
      description: template.description,
      url: `https://aap.example.com/execution/templates/workflow-job-template/${id}/details`,
      ask_inventory_on_launch: false,
      ask_credential_on_launch: false,
      ask_variables_on_launch: false,
      ask_limit_on_launch: false,
      ask_scm_branch_on_launch: false,
      ask_labels_on_launch: false,
      ask_tags_on_launch: false,
      ask_skip_tags_on_launch: false,
      survey_enabled: false,
      ...flags,
    })
  }),

  http.get('*/proxies/aap/workflow_job_templates', ({ request }) => {
    const url = new URL(request.url)
    const org = url.searchParams.get('organization')
    const search = url.searchParams.get('search')?.toLowerCase()

    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    let filtered = org ? workflowTemplates.filter((t) => t.organization === org) : workflowTemplates
    if (search) {
      filtered = filtered.filter((t) => t.name.toLowerCase().includes(search))
    }
    return HttpResponse.json({ count: filtered.length, results: filtered })
  }),

  http.get('*/proxies/aap/inventories', ({ request }) => {
    const url = new URL(request.url)
    const org = url.searchParams.get('organization')
    const search = url.searchParams.get('search')?.toLowerCase()

    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    let filtered = org ? inventories.filter((i) => i.organization === org) : inventories
    if (search) {
      filtered = filtered.filter((i) => i.name.toLowerCase().includes(search))
    }
    return HttpResponse.json({ count: filtered.length, results: filtered })
  }),

  http.get('*/proxies/aap/execution_environments', ({ request }) => {
    const url = new URL(request.url)
    const search = url.searchParams.get('search')?.toLowerCase()

    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    const filtered = search
      ? executionEnvironments.filter((ee) => ee.name.toLowerCase().includes(search))
      : executionEnvironments
    return HttpResponse.json({ count: filtered.length, results: filtered })
  }),

  http.get('*/proxies/aap/credentials', ({ request }) => {
    const url = new URL(request.url)
    const search = url.searchParams.get('search')?.toLowerCase()

    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    const filtered = search ? aapCredentials.filter((c) => c.name.toLowerCase().includes(search)) : aapCredentials
    return HttpResponse.json({ count: filtered.length, results: filtered })
  }),

  http.get('/api/v1/authz/resource_actions', () => {
    return HttpResponse.json({
      resource_actions: {
        approval: ['create', 'decide', 'read'],
        audit: ['read'],
        authz: ['query'],
        credential: ['create', 'delete', 'read', 'update'],
        execution: ['read', 'run'],
        group: ['create', 'delete', 'manage-members', 'read', 'update'],
        integration: ['create', 'delete', 'read', 'update'],
        'identity-provider': ['create', 'delete', 'read', 'test', 'update'],
        policy: ['create', 'delete', 'read', 'update'],
        project: ['create', 'delete', 'read', 'update'],
        role: ['create', 'delete', 'read', 'update'],
        role_assignment: ['assign', 'read', 'revoke'],
        setting: ['read', 'write'],
        user: ['create', 'delete', 'read', 'update'],
        user_identity: ['create', 'delete', 'read'],
        workflow: ['create', 'delete', 'read', 'update'],
      },
    })
  }),

  http.get('*/proxies/aap/instance_groups', ({ request }) => {
    const url = new URL(request.url)
    const search = url.searchParams.get('search')?.toLowerCase()

    const validationError = validateCredentialId(url)
    if (validationError) return validationError

    const filtered = search ? instanceGroups.filter((ig) => ig.name.toLowerCase().includes(search)) : instanceGroups
    return HttpResponse.json({ count: filtered.length, results: filtered })
  }),

  // ── Service Accounts ───────────────────────────────────────────────

  http.get('/api/v1/service_accounts', ({ request }) => {
    const url = new URL(request.url)
    const limit = Math.min(Number(url.searchParams.get('limit') ?? '20'), 50)
    const cursor = url.searchParams.get('cursor') ?? undefined
    const sort = url.searchParams.get('sort') ?? 'name'
    const nameFilter = url.searchParams.get('name[contains]')?.toLowerCase()
    const statusFilter = url.searchParams.get('status')?.toLowerCase()
    const includeTotal = url.searchParams.get('include_total') === 'true'

    let results = [...mockServiceAccounts]

    const username = getUsernameFromRequest(request)
    if (username === 'project-admin') {
      results = results.filter((sa) => sa.project_id === 'p-001')
    }

    if (nameFilter) results = results.filter((sa) => sa.name.toLowerCase().includes(nameFilter))
    if (statusFilter) results = results.filter((sa) => sa.status === statusFilter)

    const desc = sort.startsWith('-')
    const field = (desc ? sort.slice(1) : sort) as keyof (typeof results)[0]
    results.sort((a, b) => {
      const va = a[field] ?? ''
      const vb = b[field] ?? ''
      const cmp = String(va).localeCompare(String(vb))
      return desc ? -cmp : cmp
    })

    let startIdx = 0
    if (cursor) {
      const idx = results.findIndex((sa) => sa.id === cursor)
      if (idx >= 0) startIdx = idx + 1
    }

    const page = results.slice(startIdx, startIdx + limit)
    const nextCursor = startIdx + limit < results.length ? (results[startIdx + limit - 1]?.id ?? null) : null

    return HttpResponse.json({
      resources: page,
      next_cursor: nextCursor,
      max_lifetime_days: 180,
      ...(includeTotal ? { total: results.length } : {}),
    })
  }),

  http.post('/api/v1/service_accounts', async ({ request }) => {
    const body = (await request.json()) as { name?: string; description?: string | null; project_id?: string } | null
    if (!body?.name || !body?.project_id) {
      return HttpResponse.json({ detail: 'name and project_id are required' }, { status: 422 })
    }
    const id = `sa-new-${uuidv4().slice(0, 8)}`
    const project = mockProjects.find((p) => p.id === body.project_id)
    const project_name = project?.name ?? null

    const sa = {
      id,
      name: body.name,
      description: body.description ?? null,
      status: 'active' as const,
      project_id: body.project_id,
      project_name,
      is_project_deleted: false,
      last_authenticated_at: null,
      created_by: 'u-001',
      updated_by: null,
      created_at: mockDate.now,
      updated_at: mockDate.now,
      labels: {},
    }
    mockServiceAccounts.push(sa)
    return HttpResponse.json(sa, { status: 201 })
  }),

  http.get('/api/v1/service_accounts/:service_account_id', ({ params }) => {
    const sa = mockServiceAccounts.find((s) => s.id === params.service_account_id)
    if (!sa) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    return HttpResponse.json(sa)
  }),

  http.patch('/api/v1/service_accounts/:service_account_id', async ({ params, request }) => {
    const sa = mockServiceAccounts.find((s) => s.id === params.service_account_id)
    if (!sa) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    const body = (await request.json()) as { name?: string; description?: string | null } | null
    if (body?.name !== undefined) sa.name = body.name
    if (body?.description !== undefined) sa.description = body.description
    sa.updated_by = 'u-001'
    sa.updated_at = mockDate.now
    return HttpResponse.json(sa)
  }),

  http.delete('/api/v1/service_accounts/:service_account_id', ({ params }) => {
    const idx = mockServiceAccounts.findIndex((s) => s.id === params.service_account_id)
    if (idx < 0) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    mockServiceAccounts.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/v1/service_accounts/:service_account_id/enable', ({ params }) => {
    const sa = mockServiceAccounts.find((s) => s.id === params.service_account_id)
    if (!sa) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    sa.status = 'active'
    sa.updated_at = mockDate.now
    return HttpResponse.json(sa)
  }),

  http.post('/api/v1/service_accounts/:service_account_id/disable', ({ params }) => {
    const sa = mockServiceAccounts.find((s) => s.id === params.service_account_id)
    if (!sa) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    sa.status = 'disabled'
    sa.updated_at = mockDate.now
    return HttpResponse.json(sa)
  }),

  http.get('/api/v1/service_accounts/:service_account_id/credentials', ({ params, request }) => {
    const sa = mockServiceAccounts.find((s) => s.id === params.service_account_id)
    if (!sa) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    const url = new URL(request.url)
    const statusFilter = url.searchParams.get('status')
    const allForSa = mockServiceAccountCredentials.filter((c) => c.service_account_id === sa.id)
    let resources = [...allForSa]
    if (statusFilter) resources = resources.filter((c) => c.status === statusFilter)
    const sort = url.searchParams.get('sort')
    if (sort) {
      const desc = sort.startsWith('-')
      const field = desc ? sort.slice(1) : sort
      resources = resources.sort((a, b) => {
        const aVal = String((a as Record<string, unknown>)[field] ?? '')
        const bVal = String((b as Record<string, unknown>)[field] ?? '')
        return desc ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal)
      })
    }
    return HttpResponse.json({
      resources,
      next: null,
      prev: null,
      max_credentials: MAX_CREDENTIALS_PER_SA,
      total_credentials: allForSa.length,
      max_lifetime_days: 180,
    })
  }),

  http.post('/api/v1/service_accounts/:service_account_id/credentials', async ({ params, request }) => {
    const sa = mockServiceAccounts.find((s) => s.id === params.service_account_id)
    if (!sa) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    const existing = mockServiceAccountCredentials.filter((c) => c.service_account_id === sa.id)
    if (existing.length >= MAX_CREDENTIALS_PER_SA) {
      return HttpResponse.json(
        {
          detail: `Service account ${sa.id} has reached the maximum of ${MAX_CREDENTIALS_PER_SA} credentials`,
          code: 'SERVICE_ACCOUNT_CREDENTIAL_LIMIT',
        },
        { status: 409 }
      )
    }
    const body = (await request.json()) as { expires_at?: string | null } | null
    const credIndex = mockServiceAccountCredentials.length + 1
    const identifier = `nx_sa_${sa.name.replace(/-/g, '_')}_new${String(credIndex).padStart(3, '0')}`
    const clientSecret = `nxs_mock_secret_${sa.name}_${credIndex}`
    const defaultExpiry = mockDate.daysFromNow180
    const newCred = {
      id: `cred-new-${credIndex}`,
      service_account_id: sa.id,
      credential_type: 'client_credentials' as const,
      identifier,
      status: 'active' as const,
      grace_period_seconds: 3600,
      expires_at: body?.expires_at ?? defaultExpiry,
      last_used_at: null,
      created_by: 'u-001',
      updated_by: null,
      created_at: mockDate.now,
      updated_at: mockDate.now,
    }
    mockServiceAccountCredentials.push(newCred)
    return HttpResponse.json({ ...newCred, client_secret: clientSecret }, { status: 201 })
  }),

  http.get('/api/v1/service_accounts/:service_account_id/credentials/:credential_id', ({ params }) => {
    const cred = mockServiceAccountCredentials.find(
      (c) => c.id === params.credential_id && c.service_account_id === params.service_account_id
    )
    if (!cred) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    return HttpResponse.json(cred)
  }),

  http.delete('/api/v1/service_accounts/:service_account_id/credentials/:credential_id', ({ params }) => {
    const idx = mockServiceAccountCredentials.findIndex(
      (c) => c.id === params.credential_id && c.service_account_id === params.service_account_id
    )
    if (idx === -1) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    mockServiceAccountCredentials.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.post(
    '/api/v1/service_accounts/:service_account_id/credentials/:credential_id/rotate',
    async ({ params, request }) => {
      const cred = mockServiceAccountCredentials.find(
        (c) => c.id === params.credential_id && c.service_account_id === params.service_account_id
      )
      if (!cred) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })

      const body = (await request.json()) as { grace_period_seconds?: number }
      const gracePeriodSeconds = body?.grace_period_seconds ?? 0

      cred.updated_at = mockDate.now
      cred.updated_by = 'u-001'
      cred.grace_period_seconds = gracePeriodSeconds
      cred.old_secret_valid_until =
        gracePeriodSeconds > 0 ? new Date(Date.now() + gracePeriodSeconds * 1000).toISOString() : null

      const clientSecret = `nxs_rotated_${cred.identifier}`
      return HttpResponse.json({ ...cred, client_secret: clientSecret })
    }
  ),

  http.post('/api/v1/service_accounts/:service_account_id/credentials/:credential_id/enable', ({ params }) => {
    const cred = mockServiceAccountCredentials.find(
      (c) => c.id === params.credential_id && c.service_account_id === params.service_account_id
    )
    if (!cred) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    cred.status = 'active'
    cred.updated_at = mockDate.now
    return HttpResponse.json(cred)
  }),

  http.post('/api/v1/service_accounts/:service_account_id/credentials/:credential_id/disable', ({ params }) => {
    const cred = mockServiceAccountCredentials.find(
      (c) => c.id === params.credential_id && c.service_account_id === params.service_account_id
    )
    if (!cred) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    cred.status = 'disabled'
    cred.updated_at = mockDate.now
    return HttpResponse.json(cred)
  }),

  // ── Authz ──────────────────────────────────────────────────────────
  // Returns role-appropriate permissions based on the user's access token.
  // Honors check_any_project / resource_project for project-scoped personas
  // (padmin / puser) so mock UI gates match real can_i semantics.
  http.post('/api/v1/authz/can_i', async ({ request }) => {
    const username = getUsernameFromRequest(request)
    const body = (await request.json()) as {
      action?: string
      resource_type?: string
      check_any_project?: boolean
      resource_project?: string
    } | null
    const action = (body?.action ?? '').toLowerCase()
    const resourceType = (body?.resource_type ?? '').toLowerCase()
    const checkAnyProject = body?.check_any_project === true
    const hasResourceProject = Boolean(body?.resource_project)
    const projectContext = checkAnyProject || hasResourceProject

    if (!action || !resourceType) {
      return HttpResponse.json({
        allowed: false,
        denied: true,
        matched_policy: '',
        denial_reason: 'Missing required parameters: action and resource_type',
        denied_by: 'authorization-service',
      })
    }

    const WRITE_ACTIONS = new Set([
      'create',
      'update',
      'delete',
      'write',
      'assign',
      'revoke',
      'execute',
      'manage-members',
      'attach',
      'detach',
      'test',
      'run',
      'decide',
      'rotate_secret',
      'disable',
      'enable',
    ])

    const projectAdminGrants: Record<string, Set<string>> = {
      project: new Set(['read', 'update', 'delete']),
      'role-assignment': new Set(['read', 'assign', 'revoke']),
      role: new Set(['read', 'create', 'update', 'delete']),
      policy: new Set(['read', 'create', 'update', 'delete']),
      service_account: new Set(['read', 'create', 'update', 'delete', 'rotate_secret', 'disable', 'enable']),
      workflow: new Set(['read', 'create', 'update', 'delete']),
      execution: new Set(['read', 'run']),
      credential: new Set(['read', 'create', 'update', 'delete', 'use']),
      approval: new Set(['read', 'decide']),
    }

    const projectUserGrants: Record<string, Set<string>> = {
      project: new Set(['read']),
      role: new Set(['read']),
      policy: new Set(['read']),
      workflow: new Set(['read', 'create', 'update', 'delete']),
      execution: new Set(['read', 'run']),
      credential: new Set(['read', 'create', 'update', 'use']),
      approval: new Set(['read', 'decide']),
    }

    let allowed = true

    if (username === 'viewer') {
      const readableResources = new Set(['workflow', 'execution', 'approval', 'credential', 'integration'])
      if (readableResources.has(resourceType)) {
        allowed = action === 'read'
      } else {
        allowed = false
      }
    } else if (username === 'user') {
      const readableResources = new Set([
        'workflow',
        'execution',
        'approval',
        'credential',
        'user',
        'group',
        'role',
        'policy',
        'authz',
      ])
      if (WRITE_ACTIONS.has(action)) {
        allowed = false
      } else if (!readableResources.has(resourceType)) {
        allowed = false
      }
    } else if (username === 'auditor') {
      if (WRITE_ACTIONS.has(action)) {
        allowed = false
      } else if (resourceType === 'user_identity') {
        allowed = false
      }
    } else if (username === 'padmin' || username === 'project-admin') {
      // Project-admin: project-scoped grants only apply with project context.
      if (!projectContext) {
        allowed = false
      } else {
        allowed = projectAdminGrants[resourceType]?.has(action) ?? false
      }
    } else if (username === 'puser' || username === 'project-user') {
      if (!projectContext) {
        allowed = false
      } else {
        allowed = projectUserGrants[resourceType]?.has(action) ?? false
      }
    }
    // admin / demo / default: all actions allowed

    return HttpResponse.json({
      allowed,
      denied: !allowed,
      matched_policy: allowed ? 'default-policy' : '',
      denial_reason: allowed ? '' : `Insufficient permissions for ${resourceType}:${action}`,
      denied_by: allowed ? '' : 'authorization-service',
    })
  }),

  // ── Admin: Token Revocation ──────────────────────────────────────────

  http.get('/api/v1/admin/revocation', () => {
    return HttpResponse.json({
      revoked_before: revocationState.revoked_before,
      updated_at: revocationState.updated_at,
    })
  }),

  http.post('/api/v1/admin/revocation', () => {
    const now = new Date().toISOString()
    revocationState.revoked_before = now
    revocationState.updated_at = now
    return HttpResponse.json({ message: 'All tokens have been revoked.' })
  }),

  http.post('/api/v1/admin/revocation/users/:username', ({ params }) => {
    const username = params.username as string
    const user = users.find((u) => u.username === username)
    if (!user) {
      return HttpResponse.json(
        { type: 'about:blank', title: 'Not Found', status: 404, detail: `User "${username}" not found.` },
        { status: 404 }
      )
    }
    return HttpResponse.json({ message: `Tokens for user "${username}" have been revoked.` })
  }),

  http.post('/api/v1/admin/revocation/identity_providers/:idp_name', ({ params }) => {
    const idpName = params.idp_name as string
    const provider = identityProviders.find((p) => p.name === idpName)
    if (!provider) {
      return HttpResponse.json(
        {
          type: 'about:blank',
          title: 'Not Found',
          status: 404,
          detail: `Identity provider "${idpName}" not found.`,
        },
        { status: 404 }
      )
    }
    return HttpResponse.json({ message: `Tokens for identity provider "${idpName}" have been revoked.` })
  }),

  http.post('/api/v1/authz/who_can', async ({ request }) => {
    const body = (await request.json()) as { resource_type?: string; action?: string } | null
    const resourceType = body?.resource_type ?? 'workflow'
    const action = body?.action ?? 'read'

    const mockUsers = [
      { id: 'a1b2c3d4-0000-0000-0000-000000000001', username: 'demo' },
      { id: 'a1b2c3d4-0000-0000-0000-000000000002', username: 'admin' },
      { id: 'a1b2c3d4-0000-0000-0000-000000000003', username: 'operator' },
    ]

    const users =
      action === 'delete'
        ? mockUsers.filter((u) => u.username === 'admin')
        : resourceType === 'setting'
          ? mockUsers.filter((u) => u.username !== 'operator')
          : mockUsers

    return HttpResponse.json({ resources: users, next: null, prev: null, total: users.length })
  }),

  http.post('/api/v1/authz/what_can_i', async ({ request }) => {
    const username = getUsernameFromRequest(request)

    const respond = (items: Record<string, unknown>[]) => HttpResponse.json(paginate(items, null, items.length, true))

    if (username === 'viewer') {
      return respond([
        { policy_name: 'viewer-policy', effect: 'allow', actions: ['read'], scope: 'system', project: '' },
      ])
    }

    if (username === 'user') {
      return respond([{ policy_name: 'user-policy', effect: 'allow', actions: ['read'], scope: 'system', project: '' }])
    }

    if (username === 'auditor') {
      return respond([
        { policy_name: 'auditor-policy', effect: 'allow', actions: ['read'], scope: 'system', project: '' },
      ])
    }

    if (username === 'padmin' || username === 'project-admin') {
      return respond([
        {
          policy_name: 'project-admin',
          effect: 'allow',
          actions: [
            'project:read',
            'project:update',
            'role-assignment:read',
            'role-assignment:assign',
            'role-assignment:revoke',
            'role:read',
            'role:create',
            'role:update',
            'role:delete',
            'service_account:read',
            'service_account:create',
            'service_account:update',
            'service_account:delete',
          ],
          scope: 'project',
          project: 'default',
        },
      ])
    }

    if (username === 'puser' || username === 'project-user') {
      return respond([
        {
          policy_name: 'project-user',
          effect: 'allow',
          actions: ['project:read', 'workflow:read', 'workflow:create', 'role:read', 'policy:read'],
          scope: 'project',
          project: 'default',
        },
      ])
    }

    return respond([
      {
        policy_name: 'admin-policy',
        effect: 'allow',
        actions: ['create', 'read', 'update', 'delete', 'approval:decide'],
        scope: 'system',
        project: '',
      },
      { policy_name: 'admin-policy', effect: 'allow', actions: ['read', 'run'], scope: 'system', project: '' },
      {
        policy_name: 'project-editor',
        effect: 'allow',
        actions: ['create', 'read', 'update'],
        scope: 'project',
        project: 'default',
      },
      { policy_name: 'project-viewer', effect: 'allow', actions: ['read'], scope: 'project', project: 'production' },
      { policy_name: 'audit-reader', effect: 'allow', actions: ['read'], scope: 'system', project: '' },
    ])
  }),
]
