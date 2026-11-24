import { ActivityTypeEnum, EdgeHandleEnum, TriggerTypeEnum, type Activity } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'

import type { EdgeConnection } from './types/edge'
import type { EdgeType } from './utils/workflowToGraph'
import { createWorkflowConnectionTools, saveCanvasConnection } from './workflowWebMcpConnectionTools'
import { getWorkflowSnapshot } from './workflowWebMcpState'

vi.mock('./workflowWebMcpState', () => ({ getWorkflowSnapshot: vi.fn() }))

const snapshot = vi.mocked(getWorkflowSnapshot)
const sourceNode: Activity = { id: 'script-1', type: ActivityTypeEnum.SCRIPT, name: 'Script', parameters: {} }
const targetNode: Activity = { id: 'script-2', type: ActivityTypeEnum.SCRIPT, name: 'Target', parameters: {} }
const trigger: Activity = { id: 'trigger-0', type: TriggerTypeEnum.MANUAL_TRIGGER, name: 'Manual', parameters: {} }
const workflow = {
  workflow: { activities: [sourceNode, targetNode] },
  triggers: [trigger],
} as unknown as WorkflowDefinition
const existingEdge = {
  id: 'script-1-script-2',
  source: 'script-1',
  target: 'script-2',
  sourceHandle: EdgeHandleEnum.SOURCE,
  targetHandle: EdgeHandleEnum.TARGET,
}

function makeFlow() {
  let edges: EdgeType[] = []
  let nodes: { id: string; className?: string }[] = []
  const flow = {
    getEdges: () => edges,
    setEdges: (updater: EdgeType[] | ((current: EdgeType[]) => EdgeType[])) => {
      edges = typeof updater === 'function' ? updater(edges) : updater
    },
    setNodes: (updater: typeof nodes | ((current: typeof nodes) => typeof nodes)) => {
      nodes = typeof updater === 'function' ? updater(nodes) : updater
    },
  } as unknown as Parameters<typeof saveCanvasConnection>[1]
  return { flow, edges: () => edges, nodes: () => nodes }
}

function setSnapshot({
  current = workflow,
  activities = [sourceNode, targetNode],
  triggers = [trigger],
  edges = [],
}: {
  current?: WorkflowDefinition | null
  activities?: Activity[]
  triggers?: Activity[]
  edges?: EdgeConnection[]
} = {}) {
  snapshot.mockReturnValue({
    currentWorkflow: current,
    activities,
    triggers,
    edges,
    nodePositions: {},
    store: {} as never,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  setSnapshot()
})

describe('saveCanvasConnection', () => {
  it('resolves trigger references, adds a canvas edge, and returns the workflow edge shape', () => {
    const instance = makeFlow()
    const result = saveCanvasConnection({ source: 'trigger-0', target: 'script-1' }, instance.flow)
    expect(result).toMatchObject({
      ok: true,
      connection: {
        source: 'trigger-0',
        target: 'script-1',
        sourceHandle: EdgeHandleEnum.SOURCE,
        targetHandle: EdgeHandleEnum.TARGET,
      },
    })
    expect(instance.edges()).toHaveLength(1)
    expect(instance.edges()[0]).toMatchObject({ source: 'trigger-0', target: 'script-1' })
  })

  it('rejects invalid endpoints, self-connections, handles, duplicates, and missing replacement IDs', () => {
    const instance = makeFlow()
    expect(saveCanvasConnection({ source: 'missing', target: 'script-1' }, instance.flow)).toMatchObject({
      ok: false,
      message: 'No step or trigger was found with ID "missing".',
    })
    expect(saveCanvasConnection({ source: 'script-1', target: 'script-1' }, instance.flow)).toMatchObject({
      ok: false,
      message: 'A node cannot connect to itself.',
    })
    const unsupportedHandle = saveCanvasConnection(
      { source: 'script-1', target: 'script-2', sourceHandle: EdgeHandleEnum.TRUE },
      instance.flow
    )
    expect(unsupportedHandle.ok).toBe(false)
    if (!unsupportedHandle.ok)
      expect(unsupportedHandle.message).toContain('Provide a source_handle supported by Script')
    expect(saveCanvasConnection({ source: 'script-1', target: 'script-2' }, instance.flow)).toMatchObject({ ok: true })
    setSnapshot({ edges: [existingEdge] })
    expect(saveCanvasConnection({ source: 'script-1', target: 'script-2' }, instance.flow)).toMatchObject({
      ok: false,
      message: 'This workflow connection already exists.',
    })
    expect(
      saveCanvasConnection({ edgeId: 'missing-edge', source: 'script-1', target: 'script-2' }, instance.flow)
    ).toMatchObject({ ok: false, message: 'No workflow connection was found with ID "missing-edge".' })
  })

  it('validates loop target handles and rejects missing workflow state', () => {
    expect(
      saveCanvasConnection(
        { source: 'script-1', target: 'script-2', targetHandle: EdgeHandleEnum.END },
        makeFlow().flow
      )
    ).toMatchObject({ ok: false, message: 'target_handle "end" is only valid when connecting back to a loop node.' })
    setSnapshot({ current: null })
    expect(saveCanvasConnection({ source: 'script-1', target: 'script-2' }, makeFlow().flow)).toMatchObject({
      ok: false,
      message: 'The workflow builder is still loading.',
    })
  })
})

describe('createWorkflowConnectionTools', () => {
  it('exposes inspection only when editing is unavailable', () => {
    const tools = createWorkflowConnectionTools({
      current: { canEdit: false, deleteCanvasConnection: vi.fn(), saveCanvasConnection: vi.fn() },
    })
    expect(tools.map((tool) => tool.name)).toEqual(['get_workflow_connection'])
  })

  it('adds, updates, and deletes connections through the supplied canvas actions', async () => {
    const save = vi.fn().mockReturnValue({ ok: true, connection: existingEdge })
    const remove = vi.fn().mockResolvedValue(true)
    const actionsRef = { current: { canEdit: true, deleteCanvasConnection: remove, saveCanvasConnection: save } }
    const tools = Object.fromEntries(createWorkflowConnectionTools(actionsRef).map((tool) => [tool.name, tool]))

    setSnapshot({ edges: [existingEdge] })
    expect(tools.get_workflow_connection.execute({ edge_id: existingEdge.id })).toMatchObject({
      ok: true,
      connection: existingEdge,
    })
    expect(tools.add_workflow_connection.execute({ source: 'script-1', target: 'script-2' })).toMatchObject({
      ok: true,
      saved: false,
    })
    expect(save).toHaveBeenLastCalledWith({ source: 'script-1', target: 'script-2' })

    setSnapshot({ edges: [existingEdge] })
    expect(
      tools.update_workflow_connection.execute({ edge_id: existingEdge.id, source: 'script-1', target: 'script-2' })
    ).toMatchObject({ ok: true, saved: false })
    expect(save).toHaveBeenLastCalledWith({
      edgeId: existingEdge.id,
      source: 'script-1',
      target: 'script-2',
      sourceHandle: EdgeHandleEnum.SOURCE,
      targetHandle: EdgeHandleEnum.TARGET,
    })

    expect(await tools.delete_workflow_connection.execute({ edge_id: existingEdge.id })).toMatchObject({
      ok: true,
      deleted_edge_id: existingEdge.id,
    })
    expect(remove).toHaveBeenCalledWith(existingEdge.id)
  })

  it('reports missing IDs and permission changes', () => {
    const save = vi.fn()
    const remove = vi.fn()
    const actionsRef = { current: { canEdit: true, deleteCanvasConnection: remove, saveCanvasConnection: save } }
    const tools = Object.fromEntries(createWorkflowConnectionTools(actionsRef).map((tool) => [tool.name, tool]))
    expect(tools.get_workflow_connection.execute({ edge_id: 'missing' })).toMatchObject({ ok: false })
    expect(tools.add_workflow_connection.execute({})).toMatchObject({
      ok: false,
      message: 'Provide source and target node IDs.',
    })
    expect(tools.update_workflow_connection.execute({ edge_id: 'missing', source: 'a', target: 'b' })).toMatchObject({
      ok: false,
    })

    actionsRef.current.canEdit = false
    expect(tools.add_workflow_connection.execute({ source: 'a', target: 'b' })).toMatchObject({
      ok: false,
      message: 'You do not have permission to edit this workflow.',
    })
  })
})
