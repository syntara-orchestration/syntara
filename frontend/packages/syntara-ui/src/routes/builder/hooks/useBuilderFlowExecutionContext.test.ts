import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useBuilderFlowExecutionContext } from './useBuilderFlowExecutionContext'

let isExecutionView = false
let executionStoreState: Record<string, unknown> = {}

vi.mock('../ExecutionViewContext', () => ({
  useIsExecutionView: () => isExecutionView,
}))

vi.mock('../../workflows/stores/useExecutionStore', () => ({
  useExecutionStore: (selector: (state: Record<string, unknown>) => unknown) => selector(executionStoreState),
}))

vi.mock('../builderFlowConfig', () => ({
  resolveExecutionStatus: (rest?: string | null, store?: string | null): string | null => {
    if (rest === null) return null
    return store ?? rest ?? null
  },
}))

beforeEach(() => {
  isExecutionView = false
  executionStoreState = {
    executionMetadata: { pre_resolved_nodes: { 'task-1': true } },
    visualization: { status: 'running' },
  }
})

describe('useBuilderFlowExecutionContext', () => {
  it('marks the canvas read-only during active execution', () => {
    const { result } = renderHook(() => useBuilderFlowExecutionContext({ executionStatus: 'running', canEdit: true }))

    expect(result.current.isActiveExecution).toBe(true)
    expect(result.current.isReadOnly).toBe(true)
    expect(result.current.buttonEdgeExecutionStatus).toBe('running')
  })

  it('allows editing outside execution view when the user can edit', () => {
    executionStoreState.visualization = undefined
    const { result } = renderHook(() => useBuilderFlowExecutionContext({ executionStatus: null, canEdit: true }))

    expect(result.current.isReadOnly).toBe(false)
    expect(result.current.buttonEdgeExecutionStatus).toBeNull()
  })

  it('forces read-only mode in execution view even when canEdit is true', () => {
    isExecutionView = true
    executionStoreState.visualization = undefined

    const { result } = renderHook(() => useBuilderFlowExecutionContext({ executionStatus: null, canEdit: true }))

    expect(result.current.isExecutionView).toBe(true)
    expect(result.current.isReadOnly).toBe(true)
  })

  it('exposes pre-resolved nodes from execution metadata', () => {
    const { result } = renderHook(() => useBuilderFlowExecutionContext({ executionStatus: 'running', canEdit: true }))

    expect(result.current.preResolvedNodes).toEqual(new Set(['task-1']))
  })

  it('clears button-edge execution status for terminal execution states', () => {
    executionStoreState.visualization = { status: 'completed' }

    const { result } = renderHook(() => useBuilderFlowExecutionContext({ executionStatus: 'completed', canEdit: true }))

    expect(result.current.isActiveExecution).toBe(false)
    expect(result.current.buttonEdgeExecutionStatus).toBeNull()
  })
})
