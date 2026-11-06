/**
 * Execution Store Tests
 *
 * Comprehensive tests for execution visualization store
 */

import { renderHook } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'

import type { Execution } from '../execution/types'

import {
  useExecutionStore,
  createPendingActivityState,
  selectExecutionId,
  selectVisualization,
  selectActivityStatus,
  selectActivityError,
  selectConnectionState,
  selectIsComplete,
  selectLastEventId,
  selectError,
  selectIsLoaded,
  useExecutionWithLiveStatus,
} from './useExecutionStore'

// ============================================================================
// Test Helpers
// ============================================================================

function createMockExecution(overrides?: Partial<Execution>): Execution {
  return {
    id: 'exec-123',
    createdAt: '2025-12-10T15:00:00Z',
    updatedAt: '2025-12-10T15:00:00Z',
    workflow_id: 'workflow-456',
    workflow_version_id: 'version-789',
    status: 'running',
    started_at: '2025-12-10T15:00:05Z',
    completed_at: null,
    workflow_definition: { workflow: { activities: [] } },
    activities: [
      {
        activity_id: 'fetch_data',
        status: 'completed',
        error_details: null,
        started_at: '2025-12-10T15:00:05Z',
        completed_at: '2025-12-10T15:00:10Z',
      },
      {
        activity_id: 'process_data',
        status: 'running',
        error_details: null,
        started_at: '2025-12-10T15:00:10Z',
        completed_at: null,
      },
      {
        activity_id: 'send_notification',
        status: 'pending',
        error_details: null,
        started_at: null,
        completed_at: null,
      },
    ],
    ...overrides,
  } as Execution
}

// ============================================================================
// Store Tests
// ============================================================================

describe('useExecutionStore', () => {
  beforeEach(() => {
    // Reset store before each test
    useExecutionStore.getState().reset()
  })

  describe('initial state', () => {
    it('has correct initial state', () => {
      const state = useExecutionStore.getState()

      expect(state.executionId).toBeNull()
      expect(state.visualization).toBeNull()
      expect(state.activityStates.size).toBe(0)
      expect(state.activityErrors.size).toBe(0)
      expect(state.isConnected).toBe(false)
      expect(state.isStale).toBe(false)
      expect(state.isComplete).toBe(false)
      expect(state.lastEventId).toBeNull()
      expect(state.error).toBeNull()
    })
  })

  describe('setExecution', () => {
    it('sets execution data correctly', () => {
      const execution = createMockExecution()

      useExecutionStore.getState().setExecution(execution)

      const state = useExecutionStore.getState()
      expect(state.executionId).toBe('exec-123')
      expect(state.visualization).not.toBeNull()
      expect(state.visualization?.executionId).toBe('exec-123')
      expect(state.visualization?.workflowId).toBe('workflow-456')
      expect(state.visualization?.status).toBe('running')
    })

    it('builds activity state map from execution', () => {
      const execution = createMockExecution()

      useExecutionStore.getState().setExecution(execution)

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(3)
      expect(state.activityStates.get('fetch_data')?.status).toBe('completed')
      expect(state.activityStates.get('process_data')?.status).toBe('running')
      expect(state.activityStates.get('send_notification')?.status).toBe('pending')
    })

    it('stores full ActivityState objects', () => {
      const execution = createMockExecution()

      useExecutionStore.getState().setExecution(execution)

      const state = useExecutionStore.getState()
      const fetchDataState = state.activityStates.get('fetch_data')
      expect(fetchDataState).toBeDefined()
      expect(fetchDataState?.activityId).toBe('fetch_data')
      expect(fetchDataState?.status).toBe('completed')
      expect(fetchDataState?.startedAt).toBe('2025-12-10T15:00:05Z')
      expect(fetchDataState?.completedAt).toBe('2025-12-10T15:00:10Z')
      expect(fetchDataState?.errorDetails).toBeNull()
    })

    it('stores completed status without conversion', () => {
      const execution = createMockExecution()

      useExecutionStore.getState().setExecution(execution)

      const state = useExecutionStore.getState()
      expect(state.activityStates.get('fetch_data')?.status).toBe('completed')
    })

    it('extracts activity errors', () => {
      const execution = createMockExecution({
        activities: [
          {
            activity_id: 'failed_task',
            status: 'failed',
            error_details: 'Connection timeout',
            started_at: '2025-12-10T15:00:05Z',
            completed_at: '2025-12-10T15:00:10Z',
          },
        ],
      })

      useExecutionStore.getState().setExecution(execution)

      const state = useExecutionStore.getState()
      expect(state.activityStates.get('failed_task')?.status).toBe('failed')
      expect(state.activityErrors.get('failed_task')).toBe('Connection timeout')
    })

    it('handles execution without activities', () => {
      const execution = createMockExecution({
        activities: [],
      })

      useExecutionStore.getState().setExecution(execution)

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(0)
      expect(state.activityErrors.size).toBe(0)
    })

    it('clears previous error on successful load', () => {
      useExecutionStore.getState().setError(new Error('Previous error'))

      const execution = createMockExecution()
      useExecutionStore.getState().setExecution(execution)

      const state = useExecutionStore.getState()
      expect(state.error).toBeNull()
    })

    it('updates visualization with workflow definition', () => {
      const execution = createMockExecution({
        workflow_definition: { workflow: { activities: [{ id: 'task1' }] } },
      } as unknown as Partial<Execution>)

      useExecutionStore.getState().setExecution(execution)

      const state = useExecutionStore.getState()
      expect(state.visualization?.workflowDefinition).toEqual({
        workflow: { activities: [{ id: 'task1' }] },
      })
    })
  })

  describe('setActivityExecutions', () => {
    it('converts ActivityExecution array to ActivityState map', () => {
      useExecutionStore.getState().setActivityExecutions([
        {
          id: 'task1-exec',
          created_at: '2025-12-10T15:00:05Z',
          updated_at: '2025-12-10T15:00:05Z',
          execution_id: 'exec-123',
          temporal_activity_id: 'temporal-task1',
          activity_name: 'task1',
          node_type: 'internal_activity',
          status: 'completed' as const,
          error_details: null,
          started_at: '2025-12-10T15:00:05Z',
          completed_at: '2025-12-10T15:00:10Z',
        },
        {
          id: 'task2-exec',
          created_at: '2025-12-10T15:00:10Z',
          updated_at: '2025-12-10T15:00:10Z',
          execution_id: 'exec-123',
          temporal_activity_id: 'temporal-task2',
          activity_name: 'task2',
          node_type: 'internal_activity',
          status: 'running' as const,
          error_details: null,
          started_at: '2025-12-10T15:00:10Z',
          completed_at: null,
        },
      ])

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(2)
      expect(state.activityStates.get('task1')?.status).toBe('completed')
      expect(state.activityStates.get('task2')?.status).toBe('running')
    })

    it('preserves original ActivityStatus from backend', () => {
      useExecutionStore.getState().setActivityExecutions([
        {
          id: 'task1-exec',
          created_at: '2025-12-10T15:00:05Z',
          updated_at: '2025-12-10T15:00:05Z',
          execution_id: 'exec-123',
          temporal_activity_id: 'temporal-task1',
          activity_name: 'task1',
          node_type: 'internal_activity',
          status: 'completed' as const,
          error_details: null,
          started_at: '2025-12-10T15:00:05Z',
          completed_at: '2025-12-10T15:00:10Z',
        },
      ])

      const state = useExecutionStore.getState()
      // Should preserve backend status without conversion
      expect(state.activityStates.get('task1')?.status).toBe('completed')
    })

    it('extracts errors from activity executions', () => {
      useExecutionStore.getState().setActivityExecutions([
        {
          id: 'failed_task-exec',
          created_at: '2025-12-10T15:00:05Z',
          updated_at: '2025-12-10T15:00:05Z',
          execution_id: 'exec-123',
          temporal_activity_id: 'temporal-failed',
          activity_name: 'failed_task',
          node_type: 'internal_activity',
          status: 'failed' as const,
          error_details: 'Connection timeout',
          started_at: '2025-12-10T15:00:05Z',
          completed_at: '2025-12-10T15:00:10Z',
        },
      ])

      const state = useExecutionStore.getState()
      expect(state.activityErrors.get('failed_task')).toBe('Connection timeout')
    })

    it('clears all activity states when called with empty array', () => {
      useExecutionStore.getState().injectPendingStates(['task1', 'task2'])
      expect(useExecutionStore.getState().activityStates.size).toBe(2)

      useExecutionStore.getState().setActivityExecutions([])

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(0)
      expect(state.activityErrors.size).toBe(0)
    })

    it('handles ActivityData from Execution.activities (activity_id shape)', () => {
      useExecutionStore.getState().setActivityExecutions([
        {
          activity_id: 'fetch_data',
          status: 'completed' as const,
          error_details: null,
          started_at: '2025-12-10T15:00:05Z',
          completed_at: '2025-12-10T15:00:10Z',
        },
        {
          activity_id: 'process_data',
          status: 'running' as const,
          error_details: null,
          started_at: '2025-12-10T15:00:10Z',
          completed_at: null,
        },
      ])

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(2)
      expect(state.activityStates.get('fetch_data')?.status).toBe('completed')
      expect(state.activityStates.get('process_data')?.status).toBe('running')
    })
  })

  describe('setComplete', () => {
    it('marks execution as complete', () => {
      useExecutionStore.getState().setComplete(true)

      const state = useExecutionStore.getState()
      expect(state.isComplete).toBe(true)
    })

    it('can unmark execution as complete', () => {
      useExecutionStore.getState().setComplete(true)
      useExecutionStore.getState().setComplete(false)

      const state = useExecutionStore.getState()
      expect(state.isComplete).toBe(false)
    })
  })

  describe('setConnectionState', () => {
    it('sets connection state', () => {
      useExecutionStore.getState().setConnectionState(true, false)

      const state = useExecutionStore.getState()
      expect(state.isConnected).toBe(true)
      expect(state.isStale).toBe(false)
    })

    it('sets stale state', () => {
      useExecutionStore.getState().setConnectionState(false, true)

      const state = useExecutionStore.getState()
      expect(state.isConnected).toBe(false)
      expect(state.isStale).toBe(true)
    })
  })

  describe('setLastEventId', () => {
    it('sets last event ID', () => {
      useExecutionStore.getState().setLastEventId('1691431234567-0')

      const state = useExecutionStore.getState()
      expect(state.lastEventId).toBe('1691431234567-0')
    })

    it('updates last event ID', () => {
      useExecutionStore.getState().setLastEventId('1691431234567-0')
      useExecutionStore.getState().setLastEventId('1691431234567-1')

      const state = useExecutionStore.getState()
      expect(state.lastEventId).toBe('1691431234567-1')
    })
  })

  describe('setError', () => {
    it('sets error', () => {
      const error = new Error('Test error')
      useExecutionStore.getState().setError(error)

      const state = useExecutionStore.getState()
      expect(state.error).toBe(error)
    })

    it('clears error', () => {
      useExecutionStore.getState().setError(new Error('Test error'))
      useExecutionStore.getState().setError(null)

      const state = useExecutionStore.getState()
      expect(state.error).toBeNull()
    })
  })

  describe('reset', () => {
    it('resets to initial state', () => {
      const execution = createMockExecution()
      useExecutionStore.getState().setExecution(execution)
      useExecutionStore.getState().setConnectionState(true, false)
      useExecutionStore.getState().setComplete(true)
      useExecutionStore.getState().setLastEventId('1691431234567-0')
      useExecutionStore.getState().setError(new Error('Test error'))

      useExecutionStore.getState().reset()

      const state = useExecutionStore.getState()
      expect(state.executionId).toBeNull()
      expect(state.visualization).toBeNull()
      expect(state.activityStates.size).toBe(0)
      expect(state.activityErrors.size).toBe(0)
      expect(state.isConnected).toBe(false)
      expect(state.isStale).toBe(false)
      expect(state.isComplete).toBe(false)
      expect(state.lastEventId).toBeNull()
      expect(state.error).toBeNull()
    })
  })

  // ============================================================================
  // Selector Tests
  // ============================================================================

  describe('selectors', () => {
    beforeEach(() => {
      const execution = createMockExecution()
      useExecutionStore.getState().setExecution(execution)
    })

    it('selectExecutionId returns execution ID', () => {
      const executionId = selectExecutionId(useExecutionStore.getState())
      expect(executionId).toBe('exec-123')
    })

    it('selectVisualization returns visualization', () => {
      const visualization = selectVisualization(useExecutionStore.getState())
      expect(visualization).not.toBeNull()
      expect(visualization?.executionId).toBe('exec-123')
    })

    it('selectActivityStatus returns activity status', () => {
      const status = selectActivityStatus('fetch_data')(useExecutionStore.getState())
      expect(status).toBe('completed')
    })

    it('selectActivityStatus returns undefined for unknown activity', () => {
      const status = selectActivityStatus('unknown')(useExecutionStore.getState())
      expect(status).toBeUndefined()
    })

    it('selectActivityError returns error', () => {
      const execution = createMockExecution({
        activities: [
          {
            activity_id: 'failed_task',
            status: 'failed',
            error_details: 'Connection timeout',
            started_at: '2025-12-10T15:00:05Z',
            completed_at: '2025-12-10T15:00:10Z',
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      const error = selectActivityError('failed_task')(useExecutionStore.getState())
      expect(error).toBe('Connection timeout')
    })

    it('selectConnectionState returns connection state', () => {
      useExecutionStore.getState().setConnectionState(true, false)

      const connectionState = selectConnectionState(useExecutionStore.getState())
      expect(connectionState.isConnected).toBe(true)
      expect(connectionState.isStale).toBe(false)
    })

    it('selectIsComplete returns completion state', () => {
      useExecutionStore.getState().setComplete(true)

      const isComplete = selectIsComplete(useExecutionStore.getState())
      expect(isComplete).toBe(true)
    })

    it('selectLastEventId returns last event ID', () => {
      useExecutionStore.getState().setLastEventId('1691431234567-0')

      const lastEventId = selectLastEventId(useExecutionStore.getState())
      expect(lastEventId).toBe('1691431234567-0')
    })

    it('selectError returns error', () => {
      const error = new Error('Test error')
      useExecutionStore.getState().setError(error)

      const stateError = selectError(useExecutionStore.getState())
      expect(stateError).toBe(error)
    })

    it('selectIsLoaded returns true when execution loaded', () => {
      const isLoaded = selectIsLoaded(useExecutionStore.getState())
      expect(isLoaded).toBe(true)
    })

    it('selectIsLoaded returns false when no execution', () => {
      useExecutionStore.getState().reset()

      const isLoaded = selectIsLoaded(useExecutionStore.getState())
      expect(isLoaded).toBe(false)
    })
  })

  describe('applyExecutionPatch', () => {
    it('updates visualization status from execution_patch', () => {
      const execution = createMockExecution({ status: 'pending' })
      useExecutionStore.getState().setExecution(execution)

      expect(useExecutionStore.getState().visualization?.status).toBe('pending')

      useExecutionStore
        .getState()
        .applyExecutionPatch([{ op: 'replace', path: '/status', value: 'running' }], 'event-1')

      expect(useExecutionStore.getState().visualization?.status).toBe('running')
      expect(useExecutionStore.getState().lastEventId).toBe('event-1')
    })

    it('updates status from running to paused', () => {
      const execution = createMockExecution({ status: 'running' })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore.getState().applyExecutionPatch([{ op: 'replace', path: '/status', value: 'paused' }], 'event-2')

      expect(useExecutionStore.getState().visualization?.status).toBe('paused')
    })

    it('no-ops when visualization is null', () => {
      useExecutionStore.getState().reset()

      useExecutionStore
        .getState()
        .applyExecutionPatch([{ op: 'replace', path: '/status', value: 'running' }], 'event-3')

      expect(useExecutionStore.getState().visualization).toBeNull()
    })

    it('ignores non-status paths', () => {
      const execution = createMockExecution({ status: 'running' })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore
        .getState()
        .applyExecutionPatch([{ op: 'replace', path: '/unknown_field', value: 'something' }], 'event-4')

      expect(useExecutionStore.getState().visualization?.status).toBe('running')
      expect(useExecutionStore.getState().lastEventId).toBe('event-4')
    })

    it('preserves other visualization fields when updating status', () => {
      const execution = createMockExecution({ status: 'pending' })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore
        .getState()
        .applyExecutionPatch([{ op: 'replace', path: '/status', value: 'running' }], 'event-5')

      const viz = useExecutionStore.getState().visualization
      expect(viz?.status).toBe('running')
      expect(viz?.executionId).toBe('exec-123')
      expect(viz?.workflowId).toBe('workflow-456')
      expect(viz?.activities.size).toBe(3)
    })

    it('updates approval_pending from execution_patch', () => {
      const execution = createMockExecution({ approval_pending: false })
      useExecutionStore.getState().setExecution(execution)

      expect(useExecutionStore.getState().visualization?.approval_pending).toBe(false)

      useExecutionStore
        .getState()
        .applyExecutionPatch([{ op: 'replace', path: '/approval_pending', value: true }], 'event-6')

      expect(useExecutionStore.getState().visualization?.approval_pending).toBe(true)
      expect(useExecutionStore.getState().lastEventId).toBe('event-6')
    })

    it('updates approval_pending from true to false', () => {
      const execution = createMockExecution({ approval_pending: true })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore
        .getState()
        .applyExecutionPatch([{ op: 'replace', path: '/approval_pending', value: false }], 'event-7')

      expect(useExecutionStore.getState().visualization?.approval_pending).toBe(false)
    })

    it('updates both status and approval_pending in single patch', () => {
      const execution = createMockExecution({ status: 'running', approval_pending: false })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore.getState().applyExecutionPatch(
        [
          { op: 'replace', path: '/status', value: 'paused' },
          { op: 'replace', path: '/approval_pending', value: true },
        ],
        'event-8'
      )

      const viz = useExecutionStore.getState().visualization
      expect(viz?.status).toBe('paused')
      expect(viz?.approval_pending).toBe(true)
    })
  })

  describe('applyPatch', () => {
    it('applies JSON patch operations to activity states', () => {
      const execution = createMockExecution({
        status: 'running',
        activities: [
          {
            activity_id: 'task1',
            status: 'pending',
            error_details: null,
            started_at: null,
            completed_at: null,
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore
        .getState()
        .applyPatch([{ op: 'replace', path: '/activities/task1/status', value: 'running' }], 'event-1')

      const state = useExecutionStore.getState()
      expect(state.activityStates.get('task1')?.status).toBe('running')
      expect(state.lastEventId).toBe('event-1')
    })

    it('updates activity error when error_details is patched', () => {
      const execution = createMockExecution({
        status: 'running',
        activities: [
          {
            activity_id: 'task1',
            status: 'running',
            error_details: null,
            started_at: '2025-12-10T15:00:05Z',
            completed_at: null,
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore.getState().applyPatch(
        [
          { op: 'replace', path: '/activities/task1/status', value: 'failed' },
          { op: 'replace', path: '/activities/task1/error_details', value: 'Task failed' },
        ],
        'event-2'
      )

      const state = useExecutionStore.getState()
      expect(state.activityStates.get('task1')?.status).toBe('failed')
      expect(state.activityErrors.get('task1')).toBe('Task failed')
    })

    it('creates activity from patch when no activities are loaded', () => {
      useExecutionStore.getState().reset()

      useExecutionStore
        .getState()
        .applyPatch([{ op: 'replace', path: '/activities/task1/status', value: 'running' }], 'event-3')

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(1)
      expect(state.activityStates.get('task1')?.status).toBe('running')
      expect(state.lastEventId).toBe('event-3')
    })

    it('updates visualization.activities when visualization exists', () => {
      const execution = createMockExecution({
        status: 'running',
        activities: [
          {
            activity_id: 'task1',
            status: 'pending',
            error_details: null,
            started_at: null,
            completed_at: null,
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore
        .getState()
        .applyPatch([{ op: 'replace', path: '/activities/task1/status', value: 'completed' }], 'event-4')

      const viz = useExecutionStore.getState().visualization
      expect(viz?.activities.get('task1')?.status).toBe('completed')
    })

    it('falls back to activityStates when visualization is null', () => {
      // Set activities directly without visualization
      useExecutionStore.getState().setActivityExecutions([
        {
          id: 'task1-exec',
          created_at: '2025-12-10T15:00:05Z',
          updated_at: '2025-12-10T15:00:05Z',
          execution_id: 'exec-123',
          temporal_activity_id: 'temporal-task1',
          activity_name: 'task1',
          node_type: 'internal_activity',
          status: 'pending' as const,
          error_details: null,
          started_at: null,
          completed_at: null,
        },
      ])

      useExecutionStore
        .getState()
        .applyPatch([{ op: 'replace', path: '/activities/task1/status', value: 'running' }], 'event-5')

      const state = useExecutionStore.getState()
      expect(state.activityStates.get('task1')?.status).toBe('running')
      expect(state.visualization).toBeNull()
    })

    it('clears error state on successful patch', () => {
      const execution = createMockExecution({
        status: 'running',
        activities: [
          {
            activity_id: 'task1',
            status: 'pending',
            error_details: null,
            started_at: null,
            completed_at: null,
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)
      useExecutionStore.getState().setError(new Error('Previous error'))

      useExecutionStore
        .getState()
        .applyPatch([{ op: 'replace', path: '/activities/task1/status', value: 'running' }], 'event-6')

      expect(useExecutionStore.getState().error).toBeNull()
    })
  })

  describe('injectPreResolvedStates', () => {
    it('injects SKIPPED states for missing node IDs', () => {
      useExecutionStore.getState().injectPreResolvedStates(['node1', 'node2'])

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(2)
      expect(state.activityStates.get('node1')?.status).toBe('skipped')
      expect(state.activityStates.get('node2')?.status).toBe('skipped')
    })

    it('does not overwrite existing activity states', () => {
      const execution = createMockExecution({
        status: 'running',
        activities: [
          {
            activity_id: 'task1',
            status: 'completed',
            error_details: null,
            started_at: '2025-12-10T15:00:05Z',
            completed_at: '2025-12-10T15:00:10Z',
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore.getState().injectPreResolvedStates(['task1', 'task2'])

      const state = useExecutionStore.getState()
      expect(state.activityStates.get('task1')?.status).toBe('completed') // Not overwritten
      expect(state.activityStates.get('task2')?.status).toBe('skipped') // Newly injected
    })

    it('no-ops when empty array is provided', () => {
      const execution = createMockExecution({
        status: 'running',
        activities: [
          {
            activity_id: 'task1',
            status: 'completed',
            error_details: null,
            started_at: '2025-12-10T15:00:05Z',
            completed_at: '2025-12-10T15:00:10Z',
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore.getState().injectPreResolvedStates([])

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(1)
    })

    it('sets all SKIPPED state fields correctly', () => {
      useExecutionStore.getState().injectPreResolvedStates(['node1'])

      const node1State = useExecutionStore.getState().activityStates.get('node1')
      expect(node1State).toEqual({
        activityId: 'node1',
        status: 'skipped',
        startedAt: null,
        completedAt: null,
        errorDetails: null,
      })
    })
  })

  describe('createPendingActivityState', () => {
    it('creates a pending ActivityState with the given node ID', () => {
      const state = createPendingActivityState('node-1')
      expect(state).toEqual({
        activityId: 'node-1',
        status: 'pending',
        startedAt: null,
        completedAt: null,
        errorDetails: null,
      })
    })
  })

  describe('injectPendingStates', () => {
    it('injects pending states for node IDs', () => {
      useExecutionStore.getState().injectPendingStates(['node-1', 'node-2'])

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(2)
      expect(state.activityStates.get('node-1')?.status).toBe('pending')
      expect(state.activityStates.get('node-2')?.status).toBe('pending')
    })

    it('does not overwrite existing activity states with higher rank', () => {
      const execution = createMockExecution({
        activities: [
          {
            activity_id: 'task1',
            status: 'completed',
            error_details: null,
            started_at: '2025-12-10T15:00:05Z',
            completed_at: '2025-12-10T15:00:10Z',
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      useExecutionStore.getState().injectPendingStates(['task1', 'task2'])

      const state = useExecutionStore.getState()
      expect(state.activityStates.get('task1')?.status).toBe('completed')
      expect(state.activityStates.get('task2')?.status).toBe('pending')
    })

    it('no-ops when empty array is provided', () => {
      useExecutionStore.getState().injectPendingStates([])

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(0)
    })

    it('preserves definition order of injected node IDs', () => {
      useExecutionStore.getState().injectPendingStates(['trigger-1', 'step-2', 'step-1'])

      const keys = Array.from(useExecutionStore.getState().activityStates.keys())
      expect(keys).toEqual(['trigger-1', 'step-2', 'step-1'])
    })

    it('pending states are replaced when real activity data arrives via setActivityExecutions', () => {
      useExecutionStore.getState().injectPendingStates(['task1', 'task2'])
      expect(useExecutionStore.getState().activityStates.get('task1')?.status).toBe('pending')
      expect(useExecutionStore.getState().activityStates.get('task2')?.status).toBe('pending')

      useExecutionStore.getState().setActivityExecutions([
        {
          activity_id: 'task1',
          status: 'completed',
          error_details: null,
          started_at: '2025-12-10T15:00:05Z',
          completed_at: '2025-12-10T15:00:10Z',
        },
        {
          activity_id: 'task2',
          status: 'running',
          error_details: null,
          started_at: '2025-12-10T15:00:11Z',
          completed_at: null,
        },
      ])

      const state = useExecutionStore.getState()
      expect(state.activityStates.size).toBe(2)
      expect(state.activityStates.get('task1')?.status).toBe('completed')
      expect(state.activityStates.get('task2')?.status).toBe('running')
    })
  })

  describe('setExecutionMetadata', () => {
    it('sets execution metadata', () => {
      const metadata = {
        mode: 'test',
        pre_resolved_nodes: {
          node1: { output: { result: 'mocked' } },
        },
      }

      useExecutionStore.getState().setExecutionMetadata(metadata)

      expect(useExecutionStore.getState().executionMetadata).toEqual(metadata)
    })

    it('clears execution metadata when null is provided', () => {
      const metadata = { mode: 'test' }
      useExecutionStore.getState().setExecutionMetadata(metadata)

      useExecutionStore.getState().setExecutionMetadata(null)

      expect(useExecutionStore.getState().executionMetadata).toBeNull()
    })
  })

  describe('useExecutionWithLiveStatus', () => {
    it('returns data as-is when data is undefined', () => {
      const { result } = renderHook(() => useExecutionWithLiveStatus(undefined))
      expect(result.current).toBeUndefined()
    })

    it('returns data as-is when no visualization is present', () => {
      useExecutionStore.getState().reset()

      const mockData: Execution = {
        ...createMockExecution({ status: 'pending', approval_pending: false }),
        id: 'exec-1',
      }

      const { result } = renderHook(() => useExecutionWithLiveStatus(mockData))
      expect(result.current).toEqual(mockData)
    })

    it('overlays visualization status when visualization is present', () => {
      const execution = createMockExecution({ status: 'running', approval_pending: false })
      useExecutionStore.getState().setExecution(execution)

      const mockData: Execution = {
        ...createMockExecution({ status: 'pending', approval_pending: false }),
        id: 'exec-123',
      }

      const { result } = renderHook(() => useExecutionWithLiveStatus(mockData))
      expect(result.current.status).toBe('running') // From visualization
    })

    it('uses data.approval_pending when visualization.approval_pending is undefined', () => {
      const execution = createMockExecution({ status: 'running' })
      useExecutionStore.getState().setExecution(execution)

      // Manually clear approval_pending from visualization
      const viz = useExecutionStore.getState().visualization
      if (viz) {
        useExecutionStore.getState().visualization = { ...viz, approval_pending: undefined }
      }

      const mockData: Execution = {
        ...createMockExecution({ status: 'pending', approval_pending: true }),
        id: 'exec-123',
      }

      const { result } = renderHook(() => useExecutionWithLiveStatus(mockData))
      expect(result.current.approval_pending).toBe(true) // Falls back to data
    })

    it('uses visualization.approval_pending when it is defined', () => {
      const execution = createMockExecution({ status: 'running', approval_pending: true })
      useExecutionStore.getState().setExecution(execution)

      const mockData: Execution = {
        ...createMockExecution({ status: 'pending', approval_pending: false }),
        id: 'exec-123',
      }

      const { result } = renderHook(() => useExecutionWithLiveStatus(mockData))
      expect(result.current.approval_pending).toBe(true) // From visualization
    })
  })

  describe('mergeActivityStates', () => {
    it('rejects incoming activity with lower status rank', () => {
      const execution = createMockExecution({
        activities: [
          {
            activity_id: 'wait_node',
            status: 'waiting',
            error_details: null,
            started_at: '2025-12-10T15:00:05Z',
            completed_at: null,
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      // Second call with stale 'running' (rank 1 < waiting rank 2)
      const staleExecution = createMockExecution({
        activities: [
          {
            activity_id: 'wait_node',
            status: 'running',
            error_details: null,
            started_at: '2025-12-10T15:00:05Z',
            completed_at: null,
          },
        ],
      })
      useExecutionStore.getState().setExecution(staleExecution)

      expect(useExecutionStore.getState().activityStates.get('wait_node')?.status).toBe('waiting')
    })

    it('early patch then snapshot preserves most advanced state', () => {
      useExecutionStore.getState().reset()

      // Patch arrives before snapshot
      useExecutionStore
        .getState()
        .applyPatch([{ op: 'replace', path: '/activities/wait_node/status', value: 'waiting' }], 'patch-1')

      // Snapshot arrives with stale 'pending'
      const execution = createMockExecution({
        activities: [
          { activity_id: 'wait_node', status: 'pending', error_details: null, started_at: null, completed_at: null },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      expect(useExecutionStore.getState().activityStates.get('wait_node')?.status).toBe('waiting')
    })

    it('preserves error details when failed status survives merge', () => {
      const execution = createMockExecution({
        activities: [
          {
            activity_id: 'http_req',
            status: 'failed',
            error_details: 'timeout',
            started_at: '2025-12-10T15:00:05Z',
            completed_at: '2025-12-10T15:00:10Z',
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      // REST re-fetch with stale 'running' — should be rejected
      useExecutionStore.getState().setActivityExecutions([
        {
          activity_id: 'http_req',
          status: 'running',
          error_details: null,
          started_at: '2025-12-10T15:00:05Z',
          completed_at: null,
        },
      ])

      const state = useExecutionStore.getState()
      expect(state.activityStates.get('http_req')?.status).toBe('failed')
      expect(state.activityErrors.get('http_req')).toBe('timeout')
    })

    it('preserves startedAt when equal-rank merge receives null timestamps', () => {
      const execution = createMockExecution({
        activities: [
          {
            activity_id: 'wait_node',
            status: 'waiting',
            error_details: null,
            started_at: '2025-12-10T15:00:05Z',
            completed_at: null,
          },
        ],
      })
      useExecutionStore.getState().setExecution(execution)

      // Same-rank REST re-fetch with null startedAt must not wipe the patch value
      useExecutionStore.getState().setActivityExecutions([
        {
          activity_id: 'wait_node',
          status: 'waiting',
          error_details: null,
          started_at: null,
          completed_at: null,
        },
      ])

      expect(useExecutionStore.getState().activityStates.get('wait_node')).toMatchObject({
        status: 'waiting',
        startedAt: '2025-12-10T15:00:05Z',
      })
    })

    it('preserves existing key iteration order when merging same keys in different order', () => {
      useExecutionStore.getState().setActivityExecutions([
        { activity_id: 'task-a', status: 'pending', error_details: null, started_at: null, completed_at: null },
        { activity_id: 'task-b', status: 'pending', error_details: null, started_at: null, completed_at: null },
        { activity_id: 'task-c', status: 'pending', error_details: null, started_at: null, completed_at: null },
      ])

      expect(Array.from(useExecutionStore.getState().activityStates.keys())).toEqual(['task-a', 'task-b', 'task-c'])

      // Merge with same keys in reversed order and upgraded statuses
      useExecutionStore.getState().setActivityExecutions([
        {
          activity_id: 'task-c',
          status: 'running',
          error_details: null,
          started_at: '2025-12-10T15:00:05Z',
          completed_at: null,
        },
        {
          activity_id: 'task-a',
          status: 'running',
          error_details: null,
          started_at: '2025-12-10T15:00:06Z',
          completed_at: null,
        },
        {
          activity_id: 'task-b',
          status: 'completed',
          error_details: null,
          started_at: '2025-12-10T15:00:07Z',
          completed_at: '2025-12-10T15:00:10Z',
        },
      ])

      // Key iteration order must be preserved from original insertion
      expect(Array.from(useExecutionStore.getState().activityStates.keys())).toEqual(['task-a', 'task-b', 'task-c'])
    })
  })
})
