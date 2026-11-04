import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

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
})
