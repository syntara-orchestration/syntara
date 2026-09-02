/**
 * Workflow API helpers for E2E test setup/teardown.
 */
import type { Page } from '../fixtures'

import { apiRequest, ensureProject, getAuthToken } from './api-core'

type WorkflowStepDef = { id: string; type: string; name?: string; parameters: Record<string, unknown> }
type WorkflowEdgeDef = { from: string; to: string; from_port?: string }

/** Create a workflow via the API. Returns the new workflow ID. */
export async function createWorkflowViaApi(
  app: Page,
  name: string,
  triggers: WorkflowStepDef[],
  nodes: WorkflowStepDef[] = [],
  edges: WorkflowEdgeDef[] = []
): Promise<{
  /** UUID of the created workflow. */
  id: string
  /** Version number of the initial draft, as returned by POST /workflows (`current_version`). Pass to `publishWorkflowViaApi` to avoid a separate GET. */
  versionNumber: number
}> {
  const token = await getAuthToken(app)
  if (!token) throw new Error('createWorkflowViaApi: could not obtain auth token')
  const project = await ensureProject(app)
  if (!project) throw new Error('createWorkflowViaApi: could not ensure project')
  const resp = await apiRequest(app, 'post', '/workflows', {
    token,
    data: {
      name,
      project_id: project.id,
      workflow_definition: {
        schema_version: '2.0.0',
        name,
        triggers,
        nodes,
        edges,
      },
    },
  })
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '(unreadable)')
    throw new Error(`POST /workflows returned ${resp.status()}: ${body}`)
  }
  const body = (await resp.json()) as { id: string; current_version: number }
  return { id: body.id, versionNumber: body.current_version }
}

/** Publish a specific version of a workflow via the API. */
export async function publishWorkflowViaApi(
  app: Page,
  workflowId: string,
  /** Pass the value from `createWorkflowViaApi` to skip the extra GET. When omitted, the current version is fetched first. */
  versionNumber?: number
): Promise<void> {
  const token = await getAuthToken(app)
  if (!token) throw new Error('publishWorkflowViaApi: could not obtain auth token')

  if (versionNumber === undefined) {
    const getResp = await apiRequest(app, 'get', `/workflows/${workflowId}`, { token })
    if (!getResp.ok()) {
      const body = await getResp.text().catch(() => '(unreadable)')
      throw new Error(`GET /workflows/${workflowId} returned ${getResp.status()}: ${body}`)
    }
    versionNumber = ((await getResp.json()) as { version: { version: number } }).version.version
  }

  const publishResp = await apiRequest(app, 'post', `/workflows/${workflowId}/versions/${versionNumber}/publish`, {
    token,
    data: {},
  })
  if (!publishResp.ok()) {
    const body = await publishResp.text().catch(() => '(unreadable)')
    throw new Error(
      `POST /workflows/${workflowId}/versions/${versionNumber}/publish returned ${publishResp.status()}: ${body}`
    )
  }
}

/**
 * API equivalent of `createBasicWorkflow` — manual trigger + script action.
 * Prefer this for arrange/cleanup; keep UI creation when the test asserts create UX.
 */
export async function createBasicWorkflowViaApi(
  app: Page,
  name: string,
  actionName = 'Script'
): Promise<{ id: string; name: string; versionNumber: number }> {
  const { id, versionNumber } = await createWorkflowViaApi(
    app,
    name,
    [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
    [
      {
        id: 'action_1',
        type: 'script',
        name: actionName,
        parameters: { language: 'python', code: 'print("hello")' },
      },
    ],
    [{ from: 'trigger_1', to: 'action_1' }]
  )
  return { id, name, versionNumber }
}

/** Look up a workflow ID by exact name (best-effort). */
export async function findWorkflowIdByName(app: Page, name: string): Promise<string | null> {
  try {
    const token = await getAuthToken(app)
    if (!token) return null
    const resp = await apiRequest(app, 'get', `/workflows?name[contains]=${encodeURIComponent(name)}&limit=50`, {
      token,
    })
    if (!resp.ok()) return null
    const body = (await resp.json()) as { resources?: Array<{ id: string; name: string }> }
    return body.resources?.find((workflow) => workflow.name === name)?.id ?? null
  } catch {
    return null
  }
}

/** Delete a workflow by ID via the API (best-effort cleanup). */
export async function deleteWorkflowViaApi(app: Page, workflowId: string): Promise<void> {
  if (app.isClosed()) return
  try {
    const token = await getAuthToken(app)
    if (token) await apiRequest(app, 'delete', `/workflows/${workflowId}`, { token })
  } catch {
    // Best-effort cleanup
  }
}
