import { ActivityTypeEnum, TriggerTypeEnum, type Activity } from '@syntara/contracts'
import { render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'

import type { EdgeConnection } from './types/edge'
import { WorkflowWebMcpTools } from './WorkflowWebMcpTools'

const mocks = vi.hoisted(() => ({
  useReactFlow: vi.fn(),
  getWorkflowSnapshot: vi.fn(),
  post: vi.fn(),
  getProjectState: vi.fn(),
}))

vi.mock('@xyflow/react', () => ({ useReactFlow: mocks.useReactFlow }))
vi.mock('../../client', () => ({ workflowFetchClient: { POST: mocks.post } }))
vi.mock('../../stores/useProjectStore', () => ({ useProjectStore: { getState: mocks.getProjectState } }))
vi.mock('./workflowWebMcpState', () => ({ getWorkflowSnapshot: mocks.getWorkflowSnapshot }))

const activities: Activity[] = [
  { id: 'step-1', type: ActivityTypeEnum.SCRIPT, name: 'Script', parameters: { code: 'safe', api_token: 'hidden' } },
]
const triggers: Activity[] = [
  { id: 'trigger-real', type: TriggerTypeEnum.MANUAL_TRIGGER, name: 'Manual', parameters: {} },
]
const edges: EdgeConnection[] = [
  { id: 'edge-1', source: 'trigger-0', target: 'step-1', sourceHandle: 'source', targetHandle: 'target' },
]
const currentWorkflow = {
  id: 'workflow-1',
  name: 'Example',
  description: 'Example workflow',
  workflow: { activities },
  triggers,
} as unknown as WorkflowDefinition
const registered: { name: string; execute: (input: unknown) => unknown }[] = []
const registerTool = vi.fn((tool: { name: string; execute: (input: unknown) => unknown }) => {
  registered.push(tool)
})
const dispatch = vi.fn()
const selectProject = vi.fn(() => true)
const handleSaveWorkflow = vi.fn(() => Promise.resolve(true))
const selectableProjects = [
  { id: 'project-1', name: 'Production', is_builtin: false },
  { id: 'project-2', name: 'Production Sandbox', is_builtin: false },
] as never

function setDocumentModelContext(context: unknown) {
  Object.defineProperty(document, 'modelContext', { configurable: true, value: context })
}

function tool(name: string) {
  const found = registered.find((candidate) => candidate.name === name)
  if (!found) throw new Error(`Tool ${name} was not registered.`)
  return found
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    isNew: true,
    workflowId: null,
    workflowName: 'Example',
    workflowDescription: 'Example workflow',
    selectableProjects,
    selectableProjectsLoading: false,
    selectableProjectsFailed: false,
    selectProject,
    canEdit: true,
    canRun: false,
    handleSaveWorkflow,
    dispatch,
    ...overrides,
  } as Parameters<typeof WorkflowWebMcpTools>[0]
}

function setSnapshot(overrides: Record<string, unknown> = {}) {
  mocks.getWorkflowSnapshot.mockReturnValue({
    currentWorkflow,
    activities,
    triggers,
    edges,
    nodePositions: {},
    store: { isDirty: true, edges },
    ...overrides,
  })
}

async function renderAndRegister(inputProps = props()) {
  render(<WorkflowWebMcpTools {...inputProps} />)
  await waitFor(() => expect(registerTool).toHaveBeenCalled())
  await waitFor(() => expect(registered.length).toBeGreaterThan(0))
}

beforeEach(() => {
  registered.length = 0
  vi.clearAllMocks()
  mocks.getProjectState.mockReturnValue({ selectedProjectId: null, selectedProjectName: null })
  mocks.useReactFlow.mockReturnValue({
    deleteElements: vi.fn(() => Promise.resolve({ deletedEdges: [], deletedNodes: [] })),
    getEdges: () => [],
    setEdges: vi.fn(),
    setNodes: vi.fn(),
  })
  mocks.post.mockResolvedValue({
    data: { is_valid: true, findings: [] },
    error: undefined,
    response: { ok: true },
  })
  setSnapshot()
  setDocumentModelContext({ registerTool })
})

afterEach(() => {
  delete (document as Document & { modelContext?: unknown }).modelContext
})

describe('WorkflowWebMcpTools', () => {
  it('registers editing tools for a new editable workflow and aborts registrations on unmount', async () => {
    const view = render(<WorkflowWebMcpTools {...props()} />)
    await waitFor(() => expect(registered.length).toBe(15))
    expect(registered.map(({ name }) => name)).toContain('create_workflow_draft')
    expect(registered.map(({ name }) => name)).toContain('select_workflow_project')
    expect(registered.map(({ name }) => name)).toContain('save_workflow')
    view.unmount()
  })

  it('does not register tools for an invalid model context', () => {
    setDocumentModelContext({ registerTool: true })
    render(<WorkflowWebMcpTools {...props()} />)
    expect(registerTool).not.toHaveBeenCalled()
  })

  it('exposes safe builder state and resolves project selection by name or ID', async () => {
    await renderAndRegister()
    expect(tool('get_workflow_builder_state').execute({})).toMatchObject({
      workflow_id: null,
      is_new: true,
      is_dirty: true,
      steps: [{ id: 'step-1', type: ActivityTypeEnum.SCRIPT, name: 'Script' }],
    })
    expect(JSON.stringify(tool('get_workflow_builder_state').execute({}))).not.toContain('api_token')
    expect(tool('get_syntara_guide').execute({ topic: 'workflow_graph' })).toMatchObject({
      ok: true,
      title: 'Workflow basics',
    })
    expect(tool('get_syntara_guide').execute({ topic: 'unknown' })).toMatchObject({ ok: false })

    expect(tool('select_workflow_project').execute({ project_name: 'production' })).toMatchObject({ ok: true })
    expect(selectProject).toHaveBeenCalledWith(selectableProjects[0])
    expect(tool('select_workflow_project').execute({ project_id: 'project-2' })).toMatchObject({ ok: true })
    expect(tool('select_workflow_project').execute({ project_name: 'Production' })).toMatchObject({
      ok: true,
      selected_project: { id: 'project-1', name: 'Production' },
    })
    expect(tool('select_workflow_project').execute({ project_name: 'Sandbox' })).toMatchObject({
      ok: false,
      matching_projects: [{ id: 'project-2', name: 'Production Sandbox' }],
    })
  })

  it('validates a workflow through the backend and reports client or backend failures', async () => {
    await renderAndRegister()
    expect(await tool('validate_workflow_draft').execute({})).toMatchObject({
      ok: true,
      backend_validated: true,
      ready_to_run: true,
    })
    expect(mocks.post).toHaveBeenCalledWith('/workflows/validate', expect.any(Object))

    mocks.post.mockResolvedValueOnce({ data: undefined, error: new Error('offline'), response: { ok: false } })
    const backendFailure = (await tool('validate_workflow_draft').execute({})) as {
      errors: string[]
      backend_validated: boolean
    }
    expect(backendFailure.backend_validated).toBe(false)
    expect(backendFailure.errors.join(' ')).toContain('Backend validation could not complete')

    setSnapshot({ currentWorkflow: null })
    const loadingFailure = (await tool('validate_workflow_draft').execute({})) as {
      errors: string[]
      backend_validated: boolean
    }
    expect(loadingFailure.backend_validated).toBe(false)
    expect(loadingFailure.errors).toContain('The workflow builder is still loading.')
  })

  it('saves only after project selection for new workflows', async () => {
    await renderAndRegister()
    expect(await tool('save_workflow').execute({})).toMatchObject({
      ok: false,
      message: 'Select a project in the builder before saving this new workflow.',
    })
    mocks.getProjectState.mockReturnValue({ selectedProjectId: 'project-1', selectedProjectName: 'Production' })
    expect(await tool('save_workflow').execute({})).toMatchObject({ ok: true, saved: true })
    expect(handleSaveWorkflow).toHaveBeenCalledOnce()
    handleSaveWorkflow.mockResolvedValueOnce(false)
    expect(await tool('save_workflow').execute({})).toMatchObject({ ok: false, saved: false })
  })

  it('opens the confirmation dialog for a validated saved workflow run', async () => {
    await renderAndRegister(props({ isNew: false, workflowId: 'workflow-1', canRun: true, canEdit: false }))
    expect(await tool('request_workflow_run').execute({ trigger_index: 1 })).toMatchObject({ ok: false })
    expect(await tool('request_workflow_run').execute({ trigger_index: 0 })).toMatchObject({
      ok: true,
      confirmation_required: true,
      run_started: false,
      trigger: 'Manual',
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_SELECTED_TRIGGER', payload: 0 })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_FORCE_RUN_CONFIRMATION', payload: true })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: true })
  })

  it('gates tool registration by workflow permissions and state', async () => {
    await renderAndRegister(props({ isNew: false, workflowId: 'workflow-1', canEdit: false, canRun: true }))
    expect(registered.map(({ name }) => name)).toEqual([
      'get_syntara_guide',
      'get_workflow_builder_state',
      'get_workflow_node',
      'get_workflow_connection',
      'validate_workflow_draft',
      'request_workflow_run',
    ])
  })
})
