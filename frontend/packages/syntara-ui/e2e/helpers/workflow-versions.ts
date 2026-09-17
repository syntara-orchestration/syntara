import { type Page } from '../fixtures'
import { apiRequest, ensureProject } from '../utils/api'

export async function createWorkflowViaApi(page: Page, name: string): Promise<{ id: string; name: string }> {
  const project = await ensureProject(page)
  if (!project) throw new Error('ensureProject failed')
  const resp = await apiRequest(page, 'post', '/workflows', {
    data: {
      name,
      project_id: project.id,
      workflow_definition: {
        schema_version: '2.0.0',
        name,
        triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
        nodes: [
          {
            id: 'step1',
            name: 'Step 1',
            type: 'script',
            parameters: { language: 'python', code: 'print("v1")' },
          },
        ],
        edges: [{ from: 'trigger_1', to: 'step1' }],
      },
    },
  })
  if (!resp.ok()) throw new Error(`Workflow creation failed: ${resp.status()}`)
  return (await resp.json()) as { id: string; name: string }
}

export async function updateWorkflowViaApi(page: Page, workflowId: string, description: string) {
  const resp = await apiRequest(page, 'patch', `/workflows/${workflowId}`, {
    data: {
      workflow_definition: {
        schema_version: '2.0.0',
        name: 'updated',
        description,
        triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
        nodes: [
          {
            id: 'step1',
            name: 'Step 1',
            type: 'script',
            parameters: { language: 'python', code: `print("${description}")` },
          },
        ],
        edges: [{ from: 'trigger_1', to: 'step1' }],
      },
    },
  })
  if (!resp.ok()) throw new Error(`Workflow update failed: ${resp.status()}`)
}

export async function deleteWorkflowViaApi(page: Page, workflowId: string) {
  try {
    await apiRequest(page, 'delete', `/workflows/${workflowId}`)
  } catch {
    // Best-effort cleanup — don't mask the real test failure
  }
}

export async function simulateConcurrentSave(page: Page, workflowId: string) {
  const resp = await apiRequest(page, 'patch', `/workflows/${workflowId}`, {
    data: {
      workflow_definition: {
        schema_version: '2.0.0',
        name: 'concurrent-update',
        description: 'Simulated concurrent save',
        triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
        nodes: [
          {
            id: 'concurrent_step',
            name: 'Concurrent Step',
            type: 'script',
            parameters: { language: 'python', code: 'print("concurrent")' },
          },
        ],
        edges: [{ from: 'trigger_1', to: 'concurrent_step' }],
      },
    },
  })
  if (!resp.ok()) throw new Error(`Concurrent save failed: ${resp.status()}`)
}
