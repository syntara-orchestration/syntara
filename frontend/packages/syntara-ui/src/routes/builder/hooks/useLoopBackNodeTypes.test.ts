import { ActivityTypeEnum } from '@syntara/contracts'
import { renderHook } from '@testing-library/react'
import { type Dispatch, type SetStateAction } from 'react'
import { describe, expect, it, vi, beforeEach, type Mock } from 'vitest'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { detectLoopBackNodes } from '../utils/detectLoopBackNodes'
import type { EdgeType } from '../utils/workflowToGraph'

import { useLoopBackNodeTypes } from './useLoopBackNodeTypes'

vi.mock('../utils/detectLoopBackNodes', () => ({
  detectLoopBackNodes: vi.fn(() => new Set<string>()),
}))

const mockDetect = detectLoopBackNodes as Mock

function makeTaskNode(
  id: string,
  type: typeof FlowNodeType.TASK | typeof FlowNodeType.TASK_REVERSED = FlowNodeType.TASK
): NodeType {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: { type: ActivityTypeEnum.SCRIPT, id, name: id, parameters: {} },
  } as unknown as NodeType
}

function makeGenericNode(id: string, reverseHandles = false): NodeType {
  const metadata: Record<string, unknown> = { __isGeneric: true }
  if (reverseHandles) {
    metadata.__reverseHandles = true
  }
  return {
    id,
    type: FlowNodeType.GENERIC,
    position: { x: 0, y: 0 },
    data: { type: ActivityTypeEnum.SCRIPT, id, name: id, parameters: {}, metadata },
  } as unknown as NodeType
}

describe('useLoopBackNodeTypes', () => {
  let currentNodes: NodeType[]
  let setNodes: Dispatch<SetStateAction<NodeType[]>>

  beforeEach(() => {
    vi.clearAllMocks()
    currentNodes = []
    setNodes = vi.fn((updater: SetStateAction<NodeType[]>) => {
      if (typeof updater === 'function') {
        currentNodes = updater(currentNodes)
      }
    })
  })

  it('does nothing when not initialized', () => {
    renderHook(() => useLoopBackNodeTypes({ edges: [], isInitialized: false, setNodes }))
    expect(setNodes).not.toHaveBeenCalled()
  })

  it('returns same nodes when no changes are needed', () => {
    const nodes = [makeTaskNode('a'), makeTaskNode('b')]
    currentNodes = nodes
    mockDetect.mockReturnValue(new Set<string>())

    renderHook(() => useLoopBackNodeTypes({ edges: [] as EdgeType[], isInitialized: true, setNodes }))

    expect(setNodes).toHaveBeenCalled()
    expect(currentNodes).toBe(nodes)
  })

  it('reverses a task node to task-reversed when in loop-back path', () => {
    currentNodes = [makeTaskNode('a'), makeTaskNode('b')]
    mockDetect.mockReturnValue(new Set(['a']))

    renderHook(() => useLoopBackNodeTypes({ edges: [] as EdgeType[], isInitialized: true, setNodes }))

    expect(currentNodes[0].type).toBe(FlowNodeType.TASK_REVERSED)
    expect(currentNodes[1].type).toBe(FlowNodeType.TASK)
  })

  it('restores a task-reversed node to task when no longer in loop-back path', () => {
    currentNodes = [makeTaskNode('a', FlowNodeType.TASK_REVERSED)]
    mockDetect.mockReturnValue(new Set<string>())

    renderHook(() => useLoopBackNodeTypes({ edges: [] as EdgeType[], isInitialized: true, setNodes }))

    expect(currentNodes[0].type).toBe(FlowNodeType.TASK)
  })

  it('adds __reverseHandles to generic node when in loop-back path', () => {
    currentNodes = [makeGenericNode('g1')]
    mockDetect.mockReturnValue(new Set(['g1']))

    renderHook(() => useLoopBackNodeTypes({ edges: [] as EdgeType[], isInitialized: true, setNodes }))

    const metadata = (currentNodes[0].data as Record<string, unknown>).metadata as Record<string, unknown>
    expect(metadata.__reverseHandles).toBe(true)
  })

  it('removes __reverseHandles from generic node when no longer in loop-back path', () => {
    currentNodes = [makeGenericNode('g1', true)]
    mockDetect.mockReturnValue(new Set<string>())

    renderHook(() => useLoopBackNodeTypes({ edges: [] as EdgeType[], isInitialized: true, setNodes }))

    const metadata = (currentNodes[0].data as Record<string, unknown>).metadata as Record<string, unknown>
    expect(metadata.__reverseHandles).toBeUndefined()
  })

  it('skips non-task non-generic nodes', () => {
    const triggerNode = {
      id: 'trigger-0',
      type: FlowNodeType.TRIGGER,
      position: { x: 0, y: 0 },
      data: { name: 'Manual', triggerType: 'manual', details: '' },
    } as unknown as NodeType
    currentNodes = [triggerNode]
    mockDetect.mockReturnValue(new Set(['trigger-0']))

    renderHook(() => useLoopBackNodeTypes({ edges: [] as EdgeType[], isInitialized: true, setNodes }))

    expect(currentNodes[0].type).toBe(FlowNodeType.TRIGGER)
  })

  it('re-runs when edges change', () => {
    currentNodes = [makeTaskNode('a')]
    mockDetect.mockReturnValue(new Set<string>())

    const edge1: EdgeType[] = []
    const edge2: EdgeType[] = [{ id: 'e1', source: 'a', target: 'b' }] as EdgeType[]

    const { rerender } = renderHook(({ edges }) => useLoopBackNodeTypes({ edges, isInitialized: true, setNodes }), {
      initialProps: { edges: edge1 },
    })

    const callCount = (setNodes as unknown as Mock).mock.calls.length

    mockDetect.mockReturnValue(new Set(['a']))
    rerender({ edges: edge2 })

    expect((setNodes as unknown as Mock).mock.calls.length).toBeGreaterThan(callCount)
  })
})
