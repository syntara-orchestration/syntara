import { ActivityTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'

import { createWorkflowDetailsTool } from './workflowWebMcpDetailsTool'
import { createWorkflowDraftTool } from './workflowWebMcpDraftTool'
import { getWorkflowSnapshot } from './workflowWebMcpState'

vi.mock('./workflowWebMcpState', () => ({ getWorkflowSnapshot: vi.fn() }))

const snapshot = vi.mocked(getWorkflowSnapshot)
const emptyWorkflow = {
  id: 'workflow-1',
  name: 'Untitled',
  description: '',
  workflow: { activities: [] },
  triggers: [],
} as unknown as WorkflowDefinition
const replaceWorkflowContent = vi.fn()
const dispatch = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  snapshot.mockReturnValue({
    store: { replaceWorkflowContent } as never,
    currentWorkflow: emptyWorkflow,
    activities: [],
    triggers: [],
    edges: [],
    nodePositions: {},
  })
})

describe('createWorkflowDraftTool', () => {
  it('creates only a draft and synchronizes builder name and description', () => {
    const actionsRef = { current: { canEdit: true, isNew: true, workflowName: '', workflowDescription: '', dispatch } }
    const tool = createWorkflowDraftTool(actionsRef)
    const result = tool.execute({
      name: 'Demo',
      description: 'Draft description',
      nodes: [{ id: 'task-1', type: ActivityTypeEnum.SCRIPT, name: 'Script' }],
      edges: [{ source: 'trigger-0', target: 'task-1' }],
    })

    expect(result).toMatchObject({ ok: true, saved: false, run_started: false, trigger_count: 1, name: 'Demo' })
    expect(replaceWorkflowContent).toHaveBeenCalledOnce()
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_WORKFLOW_NAME', payload: 'Demo' })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_WORKFLOW_DESCRIPTION', payload: 'Draft description' })
    expect(actionsRef.current.workflowName).toBe('Demo')
  })

  it('rejects unauthorized, existing, and invalid draft creation', () => {
    expect(
      createWorkflowDraftTool({
        current: { canEdit: false, isNew: true, workflowName: '', workflowDescription: '', dispatch },
      }).execute({})
    ).toMatchObject({ ok: false, message: 'You do not have permission to edit this workflow.' })
    expect(
      createWorkflowDraftTool({
        current: { canEdit: true, isNew: false, workflowName: '', workflowDescription: '', dispatch },
      }).execute({})
    ).toMatchObject({ ok: false, message: 'Open a new, empty workflow builder to create a draft with this tool.' })
    expect(
      createWorkflowDraftTool({
        current: { canEdit: true, isNew: true, workflowName: '', workflowDescription: '', dispatch },
      }).execute({})
    ).toMatchObject({ ok: false, message: 'Workflow name must be text.' })
    expect(replaceWorkflowContent).not.toHaveBeenCalled()
  })
})

describe('createWorkflowDetailsTool', () => {
  function makeTool(canEdit = true, workflowName = 'Existing', workflowDescription = 'Current') {
    const actionsRef = { current: { canEdit, workflowName, workflowDescription, dispatch } }
    return { actionsRef, tool: createWorkflowDetailsTool(actionsRef) }
  }

  it('cleans changed details and dispatches only changed fields', () => {
    const { actionsRef, tool } = makeTool()
    expect(tool.execute({ name: '  Renamed  ', description: '  New\u0000 description  ' })).toMatchObject({
      ok: true,
      saved: false,
      changed_fields: ['name', 'description'],
      name: 'Renamed',
      description: 'New description',
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_WORKFLOW_NAME', payload: 'Renamed' })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_WORKFLOW_DESCRIPTION', payload: 'New description' })
    expect(actionsRef.current.workflowName).toBe('Renamed')
  })

  it('rejects unauthorized, missing, and unsupported updates', () => {
    expect(makeTool(false).tool.execute({ name: 'Changed' })).toMatchObject({ ok: false })
    expect(makeTool().tool.execute(null)).toMatchObject({
      ok: false,
      message: 'Provide a name or description to update.',
    })
    expect(makeTool().tool.execute({})).toMatchObject({
      ok: false,
      message: 'Provide a name or description to update.',
    })
    expect(makeTool().tool.execute({ other: true })).toMatchObject({
      ok: false,
      message: 'Only workflow name and description can be updated by this tool.',
    })
  })

  it('reports unchanged details and validates text input', () => {
    const { tool } = makeTool()
    expect(tool.execute({ name: 'Existing', description: 'Current' })).toMatchObject({
      ok: true,
      changed_fields: [],
      message: 'Workflow details are unchanged.',
    })
    expect(tool.execute({ name: ' ' })).toMatchObject({ ok: false, message: 'Workflow name is required.' })
    expect(tool.execute({ description: 'x'.repeat(1025) })).toMatchObject({
      ok: false,
      message: 'Workflow description must be 1024 characters or fewer.',
    })
  })

  it('reports when the workflow state is still loading', () => {
    snapshot.mockReturnValue({
      currentWorkflow: null,
      store: {} as never,
      activities: [],
      triggers: [],
      edges: [],
      nodePositions: {},
    })
    expect(makeTool().tool.execute({ name: 'Changed' })).toMatchObject({
      ok: false,
      message: 'The workflow builder is still loading.',
    })
  })
})
