import { renderHook } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'

import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { Activity } from '../../../../stores/workflowStoreTypes'
import type { EdgeConnection } from '../../types/edge'

import { useUpstreamSteps } from './useUpstreamSteps'

// Helper to create an Activity for tests
function makeActivity(id: string, type: string, name?: string): Activity {
  return { id, type, name, parameters: {} }
}

// Helper to create a WorkflowDefinition
function makeWorkflow(activities: Activity[], triggers: Activity[] = []) {
  return {
    schema_version: '2.0.0' as const,
    name: 'test-workflow',
    description: '',
    triggers,
    workflow: { activities },
  }
}

describe('useUpstreamSteps', () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      currentWorkflow: null,
      workflowVersion: 0,
      edges: [],
    })
  })

  it('returns empty array when no edges target the given nodeId', () => {
    const activity = makeActivity('node-1', 'script', 'My Script')
    useWorkflowStore.setState({
      currentWorkflow: makeWorkflow([activity]),
      edges: [],
    })

    const { result } = renderHook(() => useUpstreamSteps('node-1'))

    expect(result.current).toEqual([])
  })

  it('returns the correct upstream Activity when an edge targets the nodeId', () => {
    const upstream = makeActivity('node-a', 'script', 'Upstream Script')
    const target = makeActivity('node-b', 'condition', 'My Condition')
    const edge: EdgeConnection = {
      id: 'e1',
      source: 'node-a',
      target: 'node-b',
    }

    useWorkflowStore.setState({
      currentWorkflow: makeWorkflow([upstream, target]),
      edges: [edge],
    })

    const { result } = renderHook(() => useUpstreamSteps('node-b'))

    expect(result.current).toEqual([{ id: 'node-a', name: 'Upstream Script', type: 'script' }])
  })

  it('returns upstream Trigger when a trigger is the source', () => {
    const trigger = makeActivity('trigger-real-id', 'manual_trigger', 'Manual Trigger')
    const target = makeActivity('node-1', 'script', 'My Script')
    const edge: EdgeConnection = {
      id: 'e1',
      source: 'trigger-real-id',
      target: 'node-1',
    }

    useWorkflowStore.setState({
      currentWorkflow: makeWorkflow([target], [trigger]),
      edges: [edge],
    })

    const { result } = renderHook(() => useUpstreamSteps('node-1'))

    expect(result.current).toEqual([{ id: 'trigger-real-id', name: 'Manual Trigger', type: 'manual_trigger' }])
  })

  it('returns empty array when currentWorkflow is null', () => {
    useWorkflowStore.setState({
      currentWorkflow: null,
      edges: [{ id: 'e1', source: 'node-a', target: 'node-b' }],
    })

    const { result } = renderHook(() => useUpstreamSteps('node-b'))

    expect(result.current).toEqual([])
  })

  it('returns multiple upstream nodes for fan-in', () => {
    const activityA = makeActivity('node-a', 'script', 'Script A')
    const activityB = makeActivity('node-b', 'http_request', 'HTTP B')
    const converge = makeActivity('node-c', 'converge', 'Converge')
    const edges: EdgeConnection[] = [
      { id: 'e1', source: 'node-a', target: 'node-c' },
      { id: 'e2', source: 'node-b', target: 'node-c' },
    ]

    useWorkflowStore.setState({
      currentWorkflow: makeWorkflow([activityA, activityB, converge]),
      edges,
    })

    const { result } = renderHook(() => useUpstreamSteps('node-c'))

    expect(result.current).toEqual([
      { id: 'node-a', name: 'Script A', type: 'script' },
      { id: 'node-b', name: 'HTTP B', type: 'http_request' },
    ])
  })

  it('returns all transitive ancestors in a chain, not just direct predecessors', () => {
    const trigger = makeActivity('trigger-1', 'manual_trigger', 'Trigger')
    const gather = makeActivity('gather', 'script', 'Gather Info')
    const process = makeActivity('process', 'script', 'Process Data')
    const alert = makeActivity('alert', 'script', 'Send Alert')
    const edges: EdgeConnection[] = [
      { id: 'e1', source: 'trigger-1', target: 'gather' },
      { id: 'e2', source: 'gather', target: 'process' },
      { id: 'e3', source: 'process', target: 'alert' },
    ]

    useWorkflowStore.setState({
      currentWorkflow: makeWorkflow([gather, process, alert], [trigger]),
      edges,
    })

    const { result } = renderHook(() => useUpstreamSteps('alert'))

    // Should include ALL ancestors: process (direct), gather, and trigger
    expect(result.current).toHaveLength(3)
    expect(result.current.map((n) => n.id)).toContain('process')
    expect(result.current.map((n) => n.id)).toContain('gather')
    expect(result.current.map((n) => n.id)).toContain('trigger-1')
  })

  describe('chain deletion and reconnection', () => {
    // Build a 6-node chain: trigger → A → B → C → D → E
    const trigger = makeActivity('trigger-1', 'manual_trigger', 'Trigger')
    const nodeA = makeActivity('node-a', 'script', 'Step A')
    const nodeB = makeActivity('node-b', 'script', 'Step B')
    const nodeC = makeActivity('node-c', 'script', 'Step C')
    const nodeD = makeActivity('node-d', 'script', 'Step D')
    const nodeE = makeActivity('node-e', 'script', 'Step E')
    const fullChainEdges: EdgeConnection[] = [
      { id: 'e1', source: 'trigger-1', target: 'node-a' },
      { id: 'e2', source: 'node-a', target: 'node-b' },
      { id: 'e3', source: 'node-b', target: 'node-c' },
      { id: 'e4', source: 'node-c', target: 'node-d' },
      { id: 'e5', source: 'node-d', target: 'node-e' },
    ]

    it('last node in a 6-deep chain sees all 5 ancestors', () => {
      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow([nodeA, nodeB, nodeC, nodeD, nodeE], [trigger]),
        edges: fullChainEdges,
      })

      const { result } = renderHook(() => useUpstreamSteps('node-e'))

      expect(result.current).toHaveLength(5)
      expect(result.current.map((n) => n.id)).toEqual(
        expect.arrayContaining(['node-d', 'node-c', 'node-b', 'node-a', 'trigger-1'])
      )
    })

    it('deleting a middle node breaks the chain — downstream loses upstream ancestors', () => {
      // Delete node-c: remove it from activities and remove edges touching it
      const remainingEdges = fullChainEdges.filter((e) => e.source !== 'node-c' && e.target !== 'node-c')

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow([nodeA, nodeB, nodeD, nodeE], [trigger]),
        edges: remainingEdges,
      })

      // node-e should only see node-d (its direct predecessor), nothing beyond the break
      const { result: resultE } = renderHook(() => useUpstreamSteps('node-e'))
      expect(resultE.current).toHaveLength(1)
      expect(resultE.current[0].id).toBe('node-d')

      // node-b should still see node-a and trigger (the chain before the break is intact)
      const { result: resultB } = renderHook(() => useUpstreamSteps('node-b'))
      expect(resultB.current).toHaveLength(2)
      expect(resultB.current.map((n) => n.id)).toEqual(expect.arrayContaining(['node-a', 'trigger-1']))
    })

    it('reconnecting the chains restores full ancestor visibility', () => {
      // After deleting node-c, reconnect node-b directly to node-d
      const reconnectedEdges: EdgeConnection[] = [
        { id: 'e1', source: 'trigger-1', target: 'node-a' },
        { id: 'e2', source: 'node-a', target: 'node-b' },
        { id: 'e-new', source: 'node-b', target: 'node-d' },
        { id: 'e5', source: 'node-d', target: 'node-e' },
      ]

      useWorkflowStore.setState({
        currentWorkflow: makeWorkflow([nodeA, nodeB, nodeD, nodeE], [trigger]),
        edges: reconnectedEdges,
      })

      const { result } = renderHook(() => useUpstreamSteps('node-e'))

      // node-e should see: node-d, node-b, node-a, trigger (4 ancestors, node-c is gone)
      expect(result.current).toHaveLength(4)
      expect(result.current.map((n) => n.id)).toEqual(
        expect.arrayContaining(['node-d', 'node-b', 'node-a', 'trigger-1'])
      )
    })
  })

  it('resolves trigger via display ID (trigger-0) in edges', () => {
    const trigger = makeActivity('real-trigger-id', 'manual_trigger', 'Manual Trigger')
    const target = makeActivity('node-1', 'script', 'My Script')
    const edge: EdgeConnection = {
      id: 'e1',
      source: 'trigger-0',
      target: 'node-1',
    }

    useWorkflowStore.setState({
      currentWorkflow: makeWorkflow([target], [trigger]),
      edges: [edge],
    })

    const { result } = renderHook(() => useUpstreamSteps('node-1'))

    expect(result.current).toHaveLength(1)
    expect(result.current[0]).toEqual({ id: 'real-trigger-id', name: 'Manual Trigger', type: 'manual_trigger' })
  })

  it('does not return the node itself', () => {
    const activity = makeActivity('node-a', 'script', 'Self Loop')
    const otherActivity = makeActivity('node-b', 'script', 'Other')
    const edges: EdgeConnection[] = [
      { id: 'e1', source: 'node-a', target: 'node-a' },
      { id: 'e2', source: 'node-b', target: 'node-a' },
    ]

    useWorkflowStore.setState({
      currentWorkflow: makeWorkflow([activity, otherActivity]),
      edges,
    })

    const { result } = renderHook(() => useUpstreamSteps('node-a'))

    expect(result.current).toEqual([{ id: 'node-b', name: 'Other', type: 'script' }])
  })
})
