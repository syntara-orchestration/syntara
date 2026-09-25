import { describe, expect, it } from 'vitest'

import type { ActivityState } from '../../../../workflows/execution/types'
import type { EdgeConnection } from '../../../types/edge'
import { WorkflowTraversal } from '../traversal'

describe('WorkflowTraversal', () => {
  describe('hasDownstreamPendingNodes', () => {
    it('returns true when immediate downstream node is pending', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        ['task-2', { activityId: 'task-2', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = WorkflowTraversal.hasDownstreamPendingNodes('task-1', activityStates, edges)

      expect(result).toBe(true)
    })

    it('returns true when immediate downstream node is running', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        ['task-2', { activityId: 'task-2', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null }],
      ])

      const result = WorkflowTraversal.hasDownstreamPendingNodes('task-1', activityStates, edges)

      expect(result).toBe(true)
    })

    it('returns true when downstream node several hops away is pending', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
        { id: '2', source: 'task-2', target: 'task-3', sourceHandle: 'source', targetHandle: 'target' },
        { id: '3', source: 'task-3', target: 'task-4', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-2',
          {
            activityId: 'task-2',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        [
          'task-3',
          {
            activityId: 'task-3',
            status: 'completed',
            startedAt: '2024-01-01T00:01:00Z',
            completedAt: '2024-01-01T00:02:00Z',
          },
        ],
        ['task-4', { activityId: 'task-4', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = WorkflowTraversal.hasDownstreamPendingNodes('task-1', activityStates, edges)

      expect(result).toBe(true)
    })

    it('returns false when all downstream nodes are completed', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
        { id: '2', source: 'task-2', target: 'task-3', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-2',
          {
            activityId: 'task-2',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        [
          'task-3',
          {
            activityId: 'task-3',
            status: 'completed',
            startedAt: '2024-01-01T00:01:00Z',
            completedAt: '2024-01-01T00:02:00Z',
          },
        ],
      ])

      const result = WorkflowTraversal.hasDownstreamPendingNodes('task-1', activityStates, edges)

      expect(result).toBe(false)
    })

    it('returns false when there are no downstream nodes', () => {
      const edges: EdgeConnection[] = []
      const activityStates = new Map<string, ActivityState>()

      const result = WorkflowTraversal.hasDownstreamPendingNodes('task-1', activityStates, edges)

      expect(result).toBe(false)
    })

    it('handles cycles in the graph without infinite recursion', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'loop-1', target: 'task-1', sourceHandle: 'loop', targetHandle: 'target' },
        { id: '2', source: 'task-1', target: 'loop-1', sourceHandle: 'source', targetHandle: 'end' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-1',
          {
            activityId: 'task-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
      ])

      // Should not throw or hang
      const result = WorkflowTraversal.hasDownstreamPendingNodes('loop-1', activityStates, edges)

      expect(result).toBe(false)
    })

    it('returns true when one branch has pending and another is completed', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'cond-1', target: 'task-a', sourceHandle: 'true', targetHandle: 'target' },
        { id: '2', source: 'cond-1', target: 'task-b', sourceHandle: 'false', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-a',
          {
            activityId: 'task-a',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        ['task-b', { activityId: 'task-b', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = WorkflowTraversal.hasDownstreamPendingNodes('cond-1', activityStates, edges)

      expect(result).toBe(true)
    })
  })

  describe('shouldMarkAsSkipped', () => {
    it('returns false when node has execution state', () => {
      const edges: EdgeConnection[] = []
      const activityStates = new Map<string, ActivityState>([
        [
          'task-1',
          {
            activityId: 'task-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
      ])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-1',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(false)
    })

    it('returns false when node has no incoming edges', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>()

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-1',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(false) // Trigger nodes or orphans should not be skipped
    })

    it('returns false when downstream nodes are pending', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
        { id: '2', source: 'task-2', target: 'task-3', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        ['task-3', { activityId: 'task-3', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-2',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(false) // Execution could still reach this node
    })

    it('returns true when node is on non-taken conditional branch', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'cond-1', target: 'task-true', sourceHandle: 'true', targetHandle: 'target' },
        { id: '2', source: 'cond-1', target: 'task-false', sourceHandle: 'false', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'cond-1',
          {
            activityId: 'cond-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        [
          'task-true',
          {
            activityId: 'task-true',
            status: 'completed',
            startedAt: '2024-01-01T00:01:00Z',
            completedAt: '2024-01-01T00:02:00Z',
          },
        ],
        // task-false never started - it's on the non-taken branch
      ])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-false',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(true)
    })

    it('returns true when node is on non-taken approval branch', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'approval-1', target: 'task-approved', sourceHandle: 'approved', targetHandle: 'target' },
        { id: '2', source: 'approval-1', target: 'task-rejected', sourceHandle: 'rejected', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'approval-1',
          {
            activityId: 'approval-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        [
          'task-rejected',
          {
            activityId: 'task-rejected',
            status: 'completed',
            startedAt: '2024-01-01T00:01:00Z',
            completedAt: '2024-01-01T00:02:00Z',
          },
        ],
        // task-approved never started - it's on the non-taken branch
      ])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-approved',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(true)
    })

    it('returns true when incoming node is skipped (cascading skip)', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'cond-1', target: 'task-a', sourceHandle: 'true', targetHandle: 'target' },
        { id: '2', source: 'cond-1', target: 'task-b', sourceHandle: 'false', targetHandle: 'target' },
        { id: '3', source: 'task-a', target: 'task-c', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'cond-1',
          {
            activityId: 'cond-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        [
          'task-b',
          {
            activityId: 'task-b',
            status: 'completed',
            startedAt: '2024-01-01T00:01:00Z',
            completedAt: '2024-01-01T00:02:00Z',
          },
        ],
        // task-a is skipped (non-taken branch)
        // task-c should also be skipped (parent is skipped)
      ])

      // First verify task-a is skipped
      expect(
        WorkflowTraversal.shouldMarkAsSkipped({ activityId: 'task-a', activityStates: activityStates, edges: edges })
      ).toBe(true)

      // Then verify task-c is also skipped (cascading)
      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-c',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(true)
    })

    it('returns true when all incoming nodes are completed but node never started', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-3', sourceHandle: 'source', targetHandle: 'target' },
        { id: '2', source: 'task-2', target: 'task-3', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-1',
          {
            activityId: 'task-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        [
          'task-2',
          {
            activityId: 'task-2',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        // task-3 never started - both parents completed but didn't reach it
      ])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-3',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(true)
    })

    it('returns true for original-run nodes when allowlist includes them', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-skipped', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-1',
          {
            activityId: 'task-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
      ])
      const allowlist = new Set(['task-1', 'task-skipped'])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-skipped',
        activityStates,
        edges,
        visited: new Set(),
        skipInferenceActivityIds: allowlist,
      })

      expect(result).toBe(true)
    })

    it('returns false for nodes added after copy-to-editor (outside allowlist)', () => {
      // New nodes after copy must not inherit inferred Skipped status
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-new', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-1',
          {
            activityId: 'task-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
      ])
      const allowlist = new Set(['task-1'])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-new',
        activityStates,
        edges,
        visited: new Set(),
        skipInferenceActivityIds: allowlist,
      })

      expect(result).toBe(false)
    })

    it('handles cycles without infinite recursion', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
        { id: '2', source: 'task-2', target: 'task-1', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>()

      // Should not throw or hang
      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-1',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(false)
    })

    it('returns false when incoming node is running', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        ['task-1', { activityId: 'task-1', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null }],
      ])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-2',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(false) // Parent is running, child could still execute
    })

    it('returns false when incoming node is pending', () => {
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-1', target: 'task-2', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        ['task-1', { activityId: 'task-1', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = WorkflowTraversal.shouldMarkAsSkipped({
        activityId: 'task-2',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toBe(false) // Parent is pending, child could still execute
    })
  })
})
