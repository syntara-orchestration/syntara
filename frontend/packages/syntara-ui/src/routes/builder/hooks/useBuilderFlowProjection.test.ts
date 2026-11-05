import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../../workflows/execution/types'
import type { EdgeType } from '../utils/workflowToGraph'

import { useBuilderFlowProjection } from './useBuilderFlowProjection'

describe('useBuilderFlowProjection', () => {
  it('memoizes the graph projection while its inputs stay the same', () => {
    const options = {
      nodes: [] as NodeType[],
      edges: [] as EdgeType[],
      isInitialized: false,
      pendingEdge: null,
      buttonEdgeExecutionStatus: null,
      isReadOnly: false,
      effectiveExecutionStatus: null,
      isExecutionDetailView: false,
      currentWorkflow: null,
      activityStates: new Map<string, ActivityState>(),
      storedEdges: [],
      triggers: [],
      preResolvedNodes: new Set<string>(),
    }
    const { result, rerender } = renderHook(() => useBuilderFlowProjection(options))
    const firstProjection = result.current

    rerender()

    expect(result.current).toBe(firstProjection)
    expect(result.current).toEqual({ nodes: [], edges: [] })
  })

  it('keeps placeholder nodes stable across controlled-node measurement updates', () => {
    const options = {
      nodes: [
        {
          id: 'task-1',
          type: FlowNodeType.TASK,
          position: { x: 20, y: 40 },
          data: {},
        } as unknown as NodeType,
      ],
      edges: [] as EdgeType[],
      isInitialized: true,
      pendingEdge: null,
      buttonEdgeExecutionStatus: null,
      isReadOnly: false,
      effectiveExecutionStatus: null,
      isExecutionDetailView: false,
      currentWorkflow: null,
      activityStates: new Map<string, ActivityState>(),
      storedEdges: [],
      triggers: [],
      preResolvedNodes: new Set<string>(),
    }
    const { result, rerender } = renderHook(({ currentOptions }) => useBuilderFlowProjection(currentOptions), {
      initialProps: { currentOptions: options },
    })
    const initialPlaceholder = result.current.nodes.find((node) => node.id === 'placeholder-task-1')

    expect(initialPlaceholder).toBeDefined()

    rerender({
      currentOptions: {
        ...options,
        nodes: [{ ...options.nodes[0], width: 82, height: 50 }],
      },
    })

    expect(result.current.nodes.find((node) => node.id === 'placeholder-task-1')).toBe(initialPlaceholder)

    rerender({
      currentOptions: {
        ...options,
        nodes: [{ ...options.nodes[0], width: 82, height: 52 }],
      },
    })

    expect(result.current.nodes.find((node) => node.id === 'placeholder-task-1')).toBe(initialPlaceholder)
  })
})
