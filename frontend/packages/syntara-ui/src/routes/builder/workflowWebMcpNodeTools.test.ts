import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'

import { createWorkflowNodeTools, getAvailableSourceHandles, isEditableWorkflowNode } from './workflowWebMcpNodeTools'
import { getWorkflowSnapshot } from './workflowWebMcpState'

vi.mock('./workflowWebMcpState', () => ({ getWorkflowSnapshot: vi.fn() }))

const snapshot = vi.mocked(getWorkflowSnapshot)
const updateActivity = vi.fn()
const replaceActivity = vi.fn()
const addActivity = vi.fn()
const deleteCanvasNode = vi.fn()

const script: Activity = {
  id: 'script-1',
  type: ActivityTypeEnum.SCRIPT,
  name: 'Script',
  parameters: { language: 'python', code: 'print(1)', api_token: 'secret' },
}

const workflow = { workflow: { activities: [script] }, triggers: [] } as unknown as WorkflowDefinition

function makeTools(canEdit = true) {
  const actionsRef = { current: { canEdit, deleteCanvasNode } }
  return { actionsRef, tools: Object.fromEntries(createWorkflowNodeTools(actionsRef).map((tool) => [tool.name, tool])) }
}

beforeEach(() => {
  vi.clearAllMocks()
  snapshot.mockReturnValue({
    currentWorkflow: workflow,
    activities: [script],
    triggers: [],
    edges: [],
    nodePositions: {},
    store: { addActivity, updateActivity, replaceActivity } as never,
  })
})

describe('workflow node helpers', () => {
  it('filters unsupported and generic nodes from editing', () => {
    expect(isEditableWorkflowNode(script)).toBe(true)
    expect(isEditableWorkflowNode({ ...script, type: 'internal_activity' })).toBe(false)
    expect(isEditableWorkflowNode({ ...script, metadata: { __isGeneric: true } })).toBe(false)
  })

  it('returns type-specific output handles', () => {
    expect(getAvailableSourceHandles({ ...script, type: ActivityTypeEnum.CONDITION })).toEqual([
      EdgeHandleEnum.TRUE,
      EdgeHandleEnum.FALSE,
    ])
    expect(getAvailableSourceHandles({ ...script, type: ActivityTypeEnum.APPROVAL })).toEqual([
      EdgeHandleEnum.APPROVED,
      EdgeHandleEnum.REJECTED,
    ])
    expect(getAvailableSourceHandles({ ...script, type: ActivityTypeEnum.LOOP })).toEqual([
      EdgeHandleEnum.DONE,
      EdgeHandleEnum.LOOP,
    ])
    expect(
      getAvailableSourceHandles({
        ...script,
        type: ActivityTypeEnum.SWITCH,
        parameters: { cases: [{ port: 'case_0' }, { port: 'invalid' }], default_port: 'default' },
      })
    ).toEqual(['case_0', EdgeHandleEnum.DEFAULT])
    expect(
      getAvailableSourceHandles({ ...script, type: ActivityTypeEnum.SWITCH, parameters: { default_port: 'case_0' } })
    ).toEqual([EdgeHandleEnum.DEFAULT])
    expect(getAvailableSourceHandles(script, true)).toEqual([EdgeHandleEnum.SOURCE])
    expect(getAvailableSourceHandles(script)).toEqual([EdgeHandleEnum.SOURCE])
  })
})

describe('createWorkflowNodeTools', () => {
  it('registers read-only inspection when editing is unavailable', () => {
    const { tools } = makeTools(false)
    expect(Object.keys(tools)).toEqual(['get_workflow_node'])
    expect(tools.get_workflow_node.execute({ node_id: 'script-1' })).toMatchObject({
      ok: true,
      node: { id: 'script-1', editable: true },
    })
  })

  it('redacts secret-shaped values and rejects invalid node lookups', () => {
    const { tools } = makeTools()
    expect(tools.get_workflow_node.execute({ node_id: 'script-1' })).toMatchObject({
      ok: true,
      node: { parameters: { api_token: '[redacted]' } },
    })
    expect(tools.get_workflow_node.execute({ node_id: 'missing' })).toMatchObject({
      ok: false,
      message: 'No workflow node was found with ID "missing".',
    })
    expect(tools.get_workflow_node.execute({})).toMatchObject({
      ok: false,
      message: 'Provide a node_id from get_workflow_builder_state.',
    })
  })

  it('adds supported nodes and rejects edits without permission or valid input', () => {
    const { actionsRef, tools } = makeTools()
    actionsRef.current.canEdit = false
    expect(tools.add_workflow_node.execute({ type: ActivityTypeEnum.WAIT, name: 'Pause' })).toMatchObject({
      ok: false,
      message: 'You do not have permission to edit this workflow.',
    })
    actionsRef.current.canEdit = true
    const result = tools.add_workflow_node.execute({
      type: ActivityTypeEnum.WAIT,
      name: 'Pause',
      parameters: { duration: 5 },
    })
    expect(result).toMatchObject({ ok: true, saved: false, node: { type: ActivityTypeEnum.WAIT, name: 'Pause' } })
    expect(addActivity).toHaveBeenCalledOnce()
    expect(tools.add_workflow_node.execute({ type: 'unknown', name: 'Bad' })).toMatchObject({ ok: false })

    const noPermission = makeTools(false).tools
    expect(noPermission.add_workflow_node).toBeUndefined()
  })

  it('updates node parameters through the store', () => {
    const { tools } = makeTools()
    expect(
      tools.update_workflow_node.execute({ node_id: 'script-1', parameters_patch: { code: 'print(2)' } })
    ).toMatchObject({
      ok: true,
      node: { id: 'script-1', type: ActivityTypeEnum.SCRIPT },
    })
    expect(updateActivity).toHaveBeenCalledWith('script-1', {
      parameters: { language: 'python', code: 'print(2)', api_token: 'secret' },
    })
    expect(tools.update_workflow_node.execute({ node_id: 'script-1', name: ' ' })).toMatchObject({ ok: false })
  })

  it('deletes editable nodes and reports a failed canvas deletion', async () => {
    const { tools } = makeTools()
    deleteCanvasNode.mockResolvedValueOnce(['script-1']).mockResolvedValueOnce([])
    expect(await tools.delete_workflow_node.execute({ node_id: 'script-1' })).toMatchObject({
      ok: true,
      deleted_node_ids: ['script-1'],
    })
    expect(await tools.delete_workflow_node.execute({ node_id: 'script-1' })).toMatchObject({
      ok: false,
      message: 'The canvas did not confirm deletion of this node.',
    })
  })

  it('returns loading and permission errors without changing the canvas', () => {
    const { tools } = makeTools(false)
    expect(tools.update_workflow_node).toBeUndefined()
    expect(tools.delete_workflow_node).toBeUndefined()

    snapshot.mockReturnValue({
      currentWorkflow: null,
      activities: [],
      triggers: [],
      edges: [],
      nodePositions: {},
      store: {} as never,
    })
    expect(tools.get_workflow_node.execute({ node_id: 'script-1' })).toMatchObject({
      ok: false,
      message: 'The workflow builder is still loading.',
    })
  })
})
