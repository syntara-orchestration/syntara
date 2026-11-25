import { renderHook } from '@testing-library/react'
import type { Node, ReactFlowInstance } from '@xyflow/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useStepPanelNavigation } from './useStepPanelNavigation'

function makeFlowNode(id: string, data: Record<string, unknown>): Node {
  return {
    id,
    position: { x: 0, y: 0 },
    data,
  }
}

const mockStoreState = vi.hoisted(() => ({
  currentWorkflow: { triggers: [] as Array<{ id: string }> },
}))

vi.mock('../../../stores/useWorkflowStore', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../../stores/useWorkflowStore')>()
  return {
    ...original,
    useWorkflowStore: Object.assign(
      (selector?: (state: { currentWorkflow: typeof mockStoreState.currentWorkflow }) => unknown) => {
        const state = { currentWorkflow: mockStoreState.currentWorkflow }
        return selector ? selector(state) : state
      },
      {
        getState: () => ({ currentWorkflow: mockStoreState.currentWorkflow }),
      }
    ),
  }
})

describe('useStepPanelNavigation', () => {
  beforeEach(() => {
    mockStoreState.currentWorkflow = { triggers: [] }
  })

  it('dispatches NODE_CLICK with the resolved node', () => {
    const dispatch = vi.fn()
    const node = makeFlowNode('node-b', { name: 'Step B' })
    const reactFlowInstance = {
      getNode: vi.fn().mockReturnValue(node),
    } as unknown as ReactFlowInstance

    const { result } = renderHook(() => useStepPanelNavigation(reactFlowInstance, dispatch))

    result.current('node-b')

    expect(reactFlowInstance.getNode).toHaveBeenCalledWith('node-b')
    expect(dispatch).toHaveBeenCalledWith({
      type: 'NODE_CLICK',
      payload: { node, isGeneric: false },
    })
  })

  it('resolves real trigger ids to React Flow display ids before lookup', () => {
    mockStoreState.currentWorkflow = {
      triggers: [{ id: 'real-trigger-id' }],
    }
    const dispatch = vi.fn()
    const node = makeFlowNode('trigger-0', { name: 'Manual Trigger' })
    const reactFlowInstance = {
      getNode: vi.fn().mockReturnValue(node),
    } as unknown as ReactFlowInstance

    const { result } = renderHook(() => useStepPanelNavigation(reactFlowInstance, dispatch))

    result.current('real-trigger-id')

    expect(reactFlowInstance.getNode).toHaveBeenCalledWith('trigger-0')
    expect(dispatch).toHaveBeenCalledWith({
      type: 'NODE_CLICK',
      payload: { node, isGeneric: false },
    })
  })

  it('uses an updated trigger list after the store changes', () => {
    mockStoreState.currentWorkflow = {
      triggers: [{ id: 'first-trigger' }],
    }
    const dispatch = vi.fn()
    const firstTriggerNode = makeFlowNode('trigger-0', { name: 'First Trigger' })
    const secondTriggerNode = makeFlowNode('trigger-1', { name: 'Second Trigger' })
    const getNode = vi.fn().mockReturnValueOnce(firstTriggerNode).mockReturnValueOnce(secondTriggerNode)
    const reactFlowInstance = {
      getNode,
    } as unknown as ReactFlowInstance

    const { result, rerender } = renderHook(() => useStepPanelNavigation(reactFlowInstance, dispatch))

    result.current('first-trigger')
    expect(getNode).toHaveBeenLastCalledWith('trigger-0')

    mockStoreState.currentWorkflow = {
      triggers: [{ id: 'first-trigger' }, { id: 'second-trigger' }],
    }
    rerender()

    result.current('second-trigger')
    expect(getNode).toHaveBeenLastCalledWith('trigger-1')
    expect(dispatch).toHaveBeenCalledTimes(2)
  })

  it('does nothing when node is not found', () => {
    const dispatch = vi.fn()
    const reactFlowInstance = {
      getNode: vi.fn().mockReturnValue(undefined),
    } as unknown as ReactFlowInstance

    const { result } = renderHook(() => useStepPanelNavigation(reactFlowInstance, dispatch))

    result.current('missing-node')

    expect(dispatch).not.toHaveBeenCalled()
  })
})
