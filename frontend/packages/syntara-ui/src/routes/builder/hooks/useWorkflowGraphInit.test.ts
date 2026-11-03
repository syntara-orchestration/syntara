import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

import { useWorkflowGraphInit } from './useWorkflowGraphInit'

let workflowStoreState: Record<string, unknown> = {}

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: () => workflowStoreState,
  },
}))

const initialNodes = [
  { id: 'trigger-0', position: { x: 0, y: 0 }, data: {} },
  { id: 'task-1', position: { x: 100, y: 0 }, data: {} },
] as NodeType[]

const initialEdges = [{ id: 'e1', source: 'trigger-0', target: 'task-1' }] as EdgeType[]

const sampleWorkflow = {
  id: 'wf-1',
  triggers: [{ id: 'trig-1', type: 'manual_trigger' }],
  workflow: {
    activities: [{ id: 'task-1', type: 'script', name: 'Task', parameters: {} }],
  },
}

beforeEach(() => {
  workflowStoreState = {
    currentWorkflow: sampleWorkflow,
    nodePositions: {},
    edges: initialEdges,
  }
})

describe('useWorkflowGraphInit', () => {
  it('initializes nodes and edges when workflow data is ready', () => {
    const { result } = renderHook(() =>
      useWorkflowGraphInit({
        workflowId: 'wf-1',
        workflowVersion: 1,
        initialNodes,
        initialEdges,
      })
    )

    expect(result.current.nodes).toHaveLength(2)
    expect(result.current.edges).toHaveLength(1)
    expect(result.current.isInitializedRef.current).toBe(true)
  })

  it('applies stored node positions on initialization', () => {
    workflowStoreState.nodePositions = { 'task-1': { x: 250, y: 75 } }

    const { result } = renderHook(() =>
      useWorkflowGraphInit({
        workflowId: 'wf-1',
        workflowVersion: 1,
        initialNodes,
        initialEdges,
      })
    )

    const taskNode = result.current.nodes.find((node) => node.id === 'task-1')
    expect(taskNode?.position).toEqual({ x: 250, y: 75 })
  })

  it('clears nodes and edges when workflowId changes and store has no workflow', () => {
    const { result, rerender } = renderHook(
      ({ workflowId }: { workflowId: string }) =>
        useWorkflowGraphInit({
          workflowId,
          workflowVersion: 1,
          initialNodes,
          initialEdges,
        }),
      { initialProps: { workflowId: 'wf-1' } }
    )

    expect(result.current.nodes).toHaveLength(2)

    workflowStoreState.currentWorkflow = null
    rerender({ workflowId: 'wf-2' })

    expect(result.current.nodes).toHaveLength(0)
    expect(result.current.edges).toHaveLength(0)
    expect(result.current.isInitializedRef.current).toBe(false)
  })

  it('re-initializes nodes when workflowVersion changes', () => {
    const { result, rerender } = renderHook(
      ({ workflowVersion }: { workflowVersion: number }) =>
        useWorkflowGraphInit({
          workflowId: 'wf-1',
          workflowVersion,
          initialNodes,
          initialEdges,
        }),
      { initialProps: { workflowVersion: 1 } }
    )

    expect(result.current.nodes).toHaveLength(2)

    workflowStoreState.nodePositions = { 'task-1': { x: 400, y: 50 } }
    rerender({ workflowVersion: 2 })

    const taskNode = result.current.nodes.find((node) => node.id === 'task-1')
    expect(taskNode?.position).toEqual({ x: 400, y: 50 })
    expect(result.current.edges).toHaveLength(1)
  })

  it('waits for edges when workflow has activities but edges are empty', () => {
    const { result } = renderHook(() =>
      useWorkflowGraphInit({
        workflowId: 'wf-1',
        workflowVersion: 1,
        initialNodes,
        initialEdges: [],
      })
    )

    expect(result.current.nodes).toHaveLength(0)
    expect(result.current.isInitializedRef.current).toBe(false)
  })
})
