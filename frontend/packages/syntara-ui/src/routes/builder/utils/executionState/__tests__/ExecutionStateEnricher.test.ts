import { EdgeHandleEnum, type Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { ActivityState } from '../../../../workflows/execution/types'
import type { EdgeConnection } from '../../../types/edge'
import { ExecutionStateEnricher } from '../ExecutionStateEnricher'

describe('ExecutionStateEnricher', () => {
  const enricher = new ExecutionStateEnricher()

  describe('enrichActivity', () => {
    it('returns activity as-is when not in execution view', () => {
      const activity: Activity = {
        id: 'task-1',
        name: 'Task 1',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
      const edges: EdgeConnection[] = []
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: null,
        activityStates: activityStates,
        edges: edges,
      })

      expect(result).toEqual(activity)
      expect(result.__executionState).toBeUndefined()
    })

    it('adds execution badge flag to metadata', () => {
      const activity: Activity = {
        id: 'task-1',
        name: 'Task 1',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
      const edges: EdgeConnection[] = []
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      expect(
        ((result as Record<string, unknown>).metadata as Record<string, unknown> | undefined)?.__showExecutionBadge
      ).toBe(true)
    })

    it('preserves existing metadata when adding badge flag', () => {
      const activity = {
        id: 'task-1',
        name: 'Task 1',
        type: 'script',
        parameters: { language: 'python', code: '' },
        metadata: { customProp: 'value' },
      } as unknown as Activity
      const edges: EdgeConnection[] = []
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result.metadata).toEqual({
        customProp: 'value',
        __showExecutionBadge: true,
      })
    })

    it('adds backend state when available in activityStates', () => {
      const activity: Activity = {
        id: 'task-1',
        name: 'Task 1',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
      const edges: EdgeConnection[] = []
      const activityStates = new Map<string, ActivityState>([
        ['task-1', { activityId: 'task-1', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null }],
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result.__executionState).toEqual({
        status: 'running',
        started_at: '2024-01-01T00:00:00Z',
        completed_at: undefined,
        error_details: undefined,
      })
    })

    it('uses backend status for loop node', () => {
      const activity: Activity = {
        id: 'loop-1',
        name: 'Loop',
        type: 'loop',
        parameters: { type: 'for_each', items: '[1,2,3]' },
      }
      const edges: EdgeConnection[] = [
        { id: '1', source: 'loop-1', target: 'task-body', sourceHandle: 'loop', targetHandle: 'target' },
        { id: '2', source: 'loop-1', target: 'task-after', sourceHandle: 'done', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        ['loop-1', { activityId: 'loop-1', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null }],
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result.__executionState?.status).toBe('running')
    })

    it('does NOT infer status from downstream for loop node', () => {
      const activity: Activity = {
        id: 'loop-1',
        name: 'Loop',
        type: 'loop',
        parameters: { type: 'for_each', items: '[1,2,3]' },
      }
      const edges: EdgeConnection[] = [
        { id: '1', source: 'loop-1', target: 'task-body', sourceHandle: 'loop', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-body',
          { activityId: 'task-body', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null },
        ],
        // loop-1 has NO backend state
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      // Should NOT infer 'running' from downstream - should have no execution state
      expect(result.__executionState).toBeUndefined()
    })

    it('uses backend status for converge node', () => {
      const activity: Activity = {
        id: 'converge-1',
        name: 'Converge',
        type: 'converge',
        parameters: { strategy: 'all' },
      }
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-a', target: 'converge-1', sourceHandle: 'source', targetHandle: 'target' },
        { id: '2', source: 'task-b', target: 'converge-1', sourceHandle: 'source', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'converge-1',
          {
            activityId: 'converge-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result.__executionState?.status).toBe('completed')
    })

    it('does NOT infer status from upstream for converge node', () => {
      const activity: Activity = {
        id: 'converge-1',
        name: 'Converge',
        type: 'converge',
        parameters: { strategy: 'all' },
      }
      const edges: EdgeConnection[] = [
        { id: '1', source: 'task-a', target: 'converge-1', sourceHandle: 'source', targetHandle: 'target' },
        { id: '2', source: 'task-b', target: 'converge-1', sourceHandle: 'source', targetHandle: 'target' },
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
        ['task-b', { activityId: 'task-b', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null }],
        // converge-1 has NO backend state
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      // Should NOT infer status from upstream - should have no execution state
      expect(result.__executionState).toBeUndefined()
    })

    it('uses backend status for conditional node', () => {
      const activity: Activity = {
        id: 'cond-1',
        name: 'Conditional',
        type: 'condition',
        parameters: { condition: 'x > 5' },
      }
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
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result.__executionState?.status).toBe('completed')
    })

    it('does NOT infer status from downstream for conditional node', () => {
      const activity: Activity = {
        id: 'cond-1',
        name: 'Conditional',
        type: 'condition',
        parameters: { condition: 'x > 5' },
      }
      const edges: EdgeConnection[] = [
        { id: '1', source: 'cond-1', target: 'task-true', sourceHandle: 'true', targetHandle: 'target' },
        { id: '2', source: 'cond-1', target: 'task-false', sourceHandle: 'false', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-true',
          { activityId: 'task-true', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null },
        ],
        // cond-1 has NO backend state
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      // Should NOT infer 'completed' from downstream - should have no execution state
      expect(result.__executionState).toBeUndefined()
    })

    it('marks node as skipped when on non-taken branch', () => {
      const activity: Activity = {
        id: 'task-false',
        name: 'Task False',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
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
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result.__executionState?.status).toBe('skipped')
    })

    it('keeps skipped status for original-run nodes in the copy allowlist', () => {
      const activity: Activity = {
        id: 'task-false',
        name: 'Task False',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
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
      ])
      const allowlist = new Set(['cond-1', 'task-true', 'task-false'])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'completed',
        activityStates: activityStates,
        edges: edges,
        options: {
          skipInferenceActivityIds: allowlist,
        },
      })

      expect(result.__executionState?.status).toBe('skipped')
    })

    it('does not attach execution state for nodes added after copy-to-editor', () => {
      // Newly added nodes after copy-to-editor must have no status / indicators
      const activity: Activity = {
        id: 'task-new',
        name: 'New Task',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
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

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'completed',
        activityStates: activityStates,
        edges: edges,
        options: {
          skipInferenceActivityIds: allowlist,
        },
      })

      expect(result.__executionState).toBeUndefined()
      expect(
        ((result as Record<string, unknown>).metadata as Record<string, unknown> | undefined)?.__showExecutionBadge
      ).toBeUndefined()
    })

    it('does not set pending state for control nodes with no backend state', () => {
      const activity: Activity = {
        id: 'loop-1',
        name: 'Loop',
        type: 'loop',
        parameters: { type: 'for_each', items: '[1,2,3]' },
      }
      const edges: EdgeConnection[] = [
        { id: '1', source: 'loop-1', target: 'task-body', sourceHandle: 'loop', targetHandle: 'target' },
        { id: '2', source: 'loop-1', target: 'task-after', sourceHandle: 'done', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      // Control nodes without backend state should not get a pending badge
      expect(result.__executionState).toBeUndefined()
    })

    it('preserves failed status for loop node when body has back-edges', () => {
      const activity: Activity = {
        id: 'loop-1',
        name: 'Loop',
        type: 'loop',
        parameters: { type: 'for_each', items: '[1,2,3]' },
      }
      const edges: EdgeConnection[] = [
        { id: '1', source: 'loop-1', target: 'body-1', sourceHandle: 'loop', targetHandle: 'target' },
        { id: '2', source: 'body-1', target: 'body-2', sourceHandle: 'source', targetHandle: 'target' },
        { id: '3', source: 'body-2', target: 'loop-1', sourceHandle: 'source', targetHandle: 'end' },
        { id: '4', source: 'loop-1', target: 'task-after', sourceHandle: 'done', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'loop-1',
          {
            activityId: 'loop-1',
            status: 'failed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:05:00Z',
            errorDetails: 'max_iterations exceeded',
          },
        ],
        [
          'body-1',
          {
            activityId: 'body-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:01Z',
            completedAt: '2024-01-01T00:00:02Z',
          },
        ],
        [
          'body-1#iter-1',
          {
            activityId: 'body-1#iter-1',
            status: 'completed',
            startedAt: '2024-01-01T00:01:00Z',
            completedAt: '2024-01-01T00:01:01Z',
            iteration: 1,
          },
        ],
        [
          'body-2',
          {
            activityId: 'body-2',
            status: 'completed',
            startedAt: '2024-01-01T00:00:02Z',
            completedAt: '2024-01-01T00:00:03Z',
          },
        ],
        [
          'body-2#iter-1',
          {
            activityId: 'body-2#iter-1',
            status: 'completed',
            startedAt: '2024-01-01T00:01:01Z',
            completedAt: '2024-01-01T00:01:02Z',
            iteration: 1,
          },
        ],
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'failed',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result.__executionState?.status).toBe('failed')
      expect(result.__executionState?.error_details).toBe('max_iterations exceeded')
    })

    it('does not set pending state for regular task nodes', () => {
      const activity: Activity = {
        id: 'task-1',
        name: 'Task 1',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
      const edges: EdgeConnection[] = []
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      // Regular tasks without backend state shouldn't get a pending badge
      expect(result.__executionState).toBeUndefined()
    })

    it('uses backend status for approval nodes', () => {
      const activity: Activity = {
        id: 'approval-1',
        name: 'Approval',
        type: 'approval',
        parameters: {},
      }
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
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      expect(result.__executionState?.status).toBe('completed')
    })

    it('does NOT infer status from downstream for approval nodes', () => {
      const activity: Activity = {
        id: 'approval-1',
        name: 'Approval',
        type: 'approval',
        parameters: {},
      }
      const edges: EdgeConnection[] = [
        { id: '1', source: 'approval-1', target: 'task-approved', sourceHandle: 'approved', targetHandle: 'target' },
        { id: '2', source: 'approval-1', target: 'task-rejected', sourceHandle: 'rejected', targetHandle: 'target' },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'task-approved',
          { activityId: 'task-approved', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null },
        ],
        // approval-1 has NO backend state
      ])

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
      })

      // Should NOT infer 'completed' from downstream - should have no execution state
      expect(result.__executionState).toBeUndefined()
    })
  })

  describe('enrichActivity with preResolvedNodes', () => {
    it('marks node with __mockDataPinned when in preResolvedNodes set', () => {
      const activity: Activity = {
        id: 'task-1',
        name: 'Task 1',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
      const preResolvedNodes = new Set(['task-1'])
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
      const edges: EdgeConnection[] = []

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
        options: { preResolvedNodes },
      })

      expect(result.metadata?.__mockDataPinned).toBe(true)
      expect(result.metadata?.__showExecutionBadge).toBe(true)
    })

    it('forces SKIPPED status for pre-resolved node without backend state', () => {
      const activity: Activity = {
        id: 'task-1',
        name: 'Task 1',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
      const preResolvedNodes = new Set(['task-1'])
      const activityStates = new Map<string, ActivityState>()
      const edges: EdgeConnection[] = []

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
        options: { preResolvedNodes },
      })

      expect(result.__executionState?.status).toBe('skipped')
      expect(result.metadata?.__mockDataPinned).toBe(true)
    })

    it('uses backend state over forced SKIPPED when activityState exists', () => {
      const activity: Activity = {
        id: 'task-1',
        name: 'Task 1',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
      const preResolvedNodes = new Set(['task-1'])
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
      const edges: EdgeConnection[] = []

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
        options: { preResolvedNodes },
      })

      expect(result.__executionState?.status).toBe('completed')
      expect(result.metadata?.__mockDataPinned).toBe(true)
    })

    it('does not mark node when not in preResolvedNodes set', () => {
      const activity: Activity = {
        id: 'task-2',
        name: 'Task 2',
        type: 'script',
        parameters: { language: 'python', code: '' },
      }
      const preResolvedNodes = new Set(['task-1'])
      const activityStates = new Map<string, ActivityState>()
      const edges: EdgeConnection[] = []

      const result = enricher.enrichActivity({
        activity: activity,
        executionStatus: 'running',
        activityStates: activityStates,
        edges: edges,
        options: { preResolvedNodes },
      })

      expect(result.metadata?.__mockDataPinned).toBeUndefined()
    })
  })

  describe('determineEdgeStatus', () => {
    it('returns pending when source is running (not terminal)', () => {
      const edge = { source: 'task-1', target: 'task-2' }
      const activityStates = new Map<string, ActivityState>([
        ['task-1', { activityId: 'task-1', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('returns passed when source has completed and target has started', () => {
      const edge = { source: 'task-1', target: 'task-2' }
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
        ['task-2', { activityId: 'task-2', status: 'running', startedAt: '2024-01-01T00:01:00Z', completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('passed')
    })

    it('returns pending when source completed but target is skipped', () => {
      const edge = { source: 'task-1', target: 'task-2' }
      const activityStates = new Map<string, ActivityState>([
        [
          'task-1',
          {
            activityId: 'task-1',
            status: 'failed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:01:00Z',
          },
        ],
        ['task-2', { activityId: 'task-2', status: 'skipped', startedAt: null, completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('returns pending when source has not started', () => {
      const edge = { source: 'task-1', target: 'task-2' }
      const activityStates = new Map<string, ActivityState>([
        ['task-1', { activityId: 'task-1', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('returns pending when source has no state', () => {
      const edge = { source: 'task-1', target: 'task-2' }
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('returns passed for branching edge when target has started', () => {
      const edge = { source: 'cond-1', target: 'task-true', sourceHandle: 'true' }
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
          { activityId: 'task-true', status: 'running', startedAt: '2024-01-01T00:01:00Z', completedAt: null },
        ],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('passed')
    })

    it('returns pending for branching edge when target has not started', () => {
      const edge = { source: 'cond-1', target: 'task-true', sourceHandle: 'true' }
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
        ['task-true', { activityId: 'task-true', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('returns pending for branching edge when target is skipped', () => {
      const edge = { source: 'cond-1', target: 'task-false', sourceHandle: 'false' }
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
        ['task-false', { activityId: 'task-false', status: 'skipped', startedAt: null, completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('returns passed for trigger edges when trigger completed and target has started', () => {
      const edge = { source: 'trigger-0', target: 'task-1', sourceHandle: null }
      const triggerMap = new Map([['trigger-0', 'real-trigger-id']])
      const activityStates = new Map<string, ActivityState>([
        [
          'real-trigger-id',
          {
            activityId: 'real-trigger-id',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:00:01Z',
          },
        ],
        ['task-1', { activityId: 'task-1', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: triggerMap,
        edges: [],
      })

      expect(result).toBe('passed')
    })

    it('returns pending for trigger edges when target is pending', () => {
      const edge = { source: 'trigger-0', target: 'task-1', sourceHandle: null }
      const activityStates = new Map<string, ActivityState>([
        ['task-1', { activityId: 'task-1', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('returns pending for trigger edges when target has no state', () => {
      const edge = { source: 'trigger-0', target: 'task-1', sourceHandle: null }
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('returns passed for converge outgoing edge when target has started', () => {
      const edge = { source: 'converge-1', target: 'task-after', sourceHandle: null }
      const activityStates = new Map<string, ActivityState>([
        [
          'task-after',
          { activityId: 'task-after', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null },
        ],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('passed')
    })

    it('returns pending for converge outgoing edge when target is pending', () => {
      const edge = { source: 'converge-1', target: 'task-after', sourceHandle: null }
      const activityStates = new Map<string, ActivityState>([
        ['task-after', { activityId: 'task-after', status: 'pending', startedAt: null, completedAt: null }],
      ])

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('pending')
    })

    it('detects converge outgoing edge when activities list omits source but id has converge prefix', () => {
      const edge = { source: 'converge-abc', target: 'task-after', sourceHandle: null }
      const activityStates = new Map<string, ActivityState>([
        [
          'task-after',
          { activityId: 'task-after', status: 'running', startedAt: '2024-01-01T00:00:00Z', completedAt: null },
        ],
      ])
      const activities: Activity[] = []

      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: activities,
        triggerDisplayToRealId: undefined,
        edges: [],
      })

      expect(result).toBe('passed')
    })

    it('uses latest iteration state for loop body edges with composite keys', () => {
      const edges: EdgeConnection[] = [
        { id: 'e-loop-body1', source: 'loop-1', target: 'body-1', sourceHandle: EdgeHandleEnum.LOOP },
        { id: 'e-body1-body2', source: 'body-1', target: 'body-2', sourceHandle: EdgeHandleEnum.SOURCE },
      ]
      const activityStates = new Map<string, ActivityState>([
        [
          'loop-1',
          {
            activityId: 'loop-1',
            status: 'running',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: null,
          },
        ],
        [
          'body-1',
          {
            activityId: 'body-1',
            status: 'completed',
            startedAt: '2024-01-01T00:00:01Z',
            completedAt: '2024-01-01T00:00:02Z',
            iteration: 0,
          },
        ],
        [
          'body-1#iter-1',
          {
            activityId: 'body-1#iter-1',
            status: 'running',
            startedAt: '2024-01-01T00:01:00Z',
            completedAt: null,
            iteration: 1,
          },
        ],
        [
          'body-2',
          {
            activityId: 'body-2',
            status: 'completed',
            startedAt: '2024-01-01T00:00:02Z',
            completedAt: '2024-01-01T00:00:03Z',
            iteration: 0,
          },
        ],
      ])

      const edge = { source: 'body-1', target: 'body-2', sourceHandle: EdgeHandleEnum.SOURCE }
      const result = enricher.determineEdgeStatus({
        edge: edge,
        activityStates: activityStates,
        activities: undefined,
        triggerDisplayToRealId: undefined,
        edges: edges,
      })

      // body-1's latest iteration (#iter-1) is running, not terminal — edge should be pending
      expect(result).toBe('pending')
    })
  })

  describe('enrichTriggerNode', () => {
    it('returns trigger data as-is when not in execution view', () => {
      const triggerData = { name: 'Manual trigger', details: 'Manual', triggerType: 'manual' }
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichTriggerNode('trigger-real-id', triggerData, null, activityStates)

      expect(result).toEqual(triggerData)
      expect(result.__executionState).toBeUndefined()
    })

    it('uses trigger status from activityStates when available', () => {
      const triggerData = { name: 'Manual trigger', details: 'Manual', triggerType: 'manual' }
      const activityStates = new Map<string, ActivityState>([
        [
          'trigger-real-id',
          {
            activityId: 'trigger-real-id',
            status: 'completed',
            startedAt: '2024-01-01T00:00:00Z',
            completedAt: '2024-01-01T00:00:01Z',
          },
        ],
      ])

      const result = enricher.enrichTriggerNode('trigger-real-id', triggerData, 'running', activityStates)

      expect(result.__executionState?.status).toBe('completed')
      expect(result.__executionState?.started_at).toBe('2024-01-01T00:00:00Z')
      expect(
        ((result as Record<string, unknown>).metadata as Record<string, unknown> | undefined)?.__showExecutionBadge
      ).toBe(true)
    })

    it('marks trigger as skipped when activityStates reports skipped', () => {
      const triggerData = { name: 'Webhook trigger', details: 'Webhook', triggerType: 'webhook' }
      const activityStates = new Map<string, ActivityState>([
        ['trigger-b-id', { activityId: 'trigger-b-id', status: 'skipped', startedAt: null, completedAt: null }],
      ])

      const result = enricher.enrichTriggerNode('trigger-b-id', triggerData, 'completed', activityStates)

      expect(result.__executionState?.status).toBe('skipped')
    })

    it('marks trigger as pending when not found in activityStates', () => {
      const triggerData = { name: 'Manual trigger', details: 'Manual', triggerType: 'manual' }
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichTriggerNode('trigger-real-id', triggerData, 'pending', activityStates)

      expect(result.__executionState?.status).toBe('pending')
      expect(
        ((result as Record<string, unknown>).metadata as Record<string, unknown> | undefined)?.__showExecutionBadge
      ).toBe(true)
    })

    it('falls back to completed when triggerRealId is undefined and execution has started', () => {
      const triggerData = { name: 'Manual trigger', details: 'Manual', triggerType: 'manual' }
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichTriggerNode(undefined, triggerData, 'running', activityStates)

      expect(result.__executionState?.status).toBe('completed')
    })

    it('preserves existing metadata when adding execution badge', () => {
      const triggerData = {
        name: 'Manual trigger',
        details: 'Manual',
        triggerType: 'manual',
        metadata: { customProp: 'value' },
      }
      const activityStates = new Map<string, ActivityState>()

      const result = enricher.enrichTriggerNode('trigger-real-id', triggerData, 'running', activityStates)

      expect(result.metadata).toEqual({
        customProp: 'value',
        __showExecutionBadge: true,
      })
    })
  })
})
