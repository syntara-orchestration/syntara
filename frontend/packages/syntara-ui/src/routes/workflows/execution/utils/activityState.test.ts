/**
 * Activity State Utilities Tests
 *
 * Comprehensive tests for JSON Patch operations and activity state management
 */

import { describe, it, expect } from 'vitest'

import type { ActivityState, JsonPatchOperation } from '../types'

import {
  parseActivityPath,
  parseCompositeKey,
  latestActivityStateForCanvasNode,
  applyOperation,
  applyJsonPatch,
  buildActivityStateMap,
  buildLatestIterationMap,
  extractActivityMaps,
  extractApprovalAudit,
} from './activityState'

// ============================================================================
// Path Parsing Tests
// ============================================================================

describe('parseActivityPath', () => {
  it('parses activity ID path correctly', () => {
    const result = parseActivityPath('/activities/fetch_data/status')
    expect(result).toEqual({
      activityId: 'fetch_data',
      field: 'status',
      arrayIndex: undefined,
    })
  })

  it('parses array index path correctly', () => {
    const result = parseActivityPath('/activities/0/status')
    expect(result).toEqual({
      activityId: '0',
      field: 'status',
      arrayIndex: 0,
    })
  })

  it('handles path without leading slash', () => {
    const result = parseActivityPath('activities/process_data/error_details')
    expect(result).toEqual({
      activityId: 'process_data',
      field: 'error_details',
      arrayIndex: undefined,
    })
  })

  it('throws error for invalid path format', () => {
    expect(() => parseActivityPath('/invalid/path')).toThrow('Invalid activity path format')
    expect(() => parseActivityPath('/activities')).toThrow('Invalid activity path format')
    expect(() => parseActivityPath('/activities/id')).toThrow('Invalid activity path format')
  })

  it('throws error for wrong root key', () => {
    expect(() => parseActivityPath('/executions/id/status')).toThrow('Invalid activity path format')
  })

  it('throws error for empty parts', () => {
    expect(() => parseActivityPath('/activities//status')).toThrow('Missing activity ID or field')
    expect(() => parseActivityPath('/activities/id/')).toThrow('Missing activity ID or field')
  })
})

// ============================================================================
// Apply Operation Tests
// ============================================================================

describe('applyOperation', () => {
  describe('add operation', () => {
    it('creates new activity with status', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'add',
        path: '/activities/fetch_data/status',
        value: 'running',
      }

      applyOperation(activities, operation)

      expect(activities.get('fetch_data')).toEqual({
        activityId: 'fetch_data',
        status: 'running',
      })
    })

    it('adds error_details to existing activity', () => {
      const activities = new Map<string, ActivityState>([
        ['fetch_data', { activityId: 'fetch_data', status: 'failed' }],
      ])
      const operation: JsonPatchOperation = {
        op: 'add',
        path: '/activities/fetch_data/error_details',
        value: 'Connection timeout',
      }

      applyOperation(activities, operation)

      expect(activities.get('fetch_data')?.errorDetails).toBe('Connection timeout')
    })

    it('throws error if value is missing', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'add',
        path: '/activities/fetch_data/status',
      }

      expect(() => applyOperation(activities, operation)).toThrow("Operation 'add' requires a value")
    })

    it('throws error when creating activity without status field', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'add',
        path: '/activities/fetch_data/error_details',
        value: 'Error',
      }

      expect(() => applyOperation(activities, operation)).toThrow("'status' is required first")
    })
  })

  describe('replace operation', () => {
    it('replaces activity status', () => {
      const activities = new Map<string, ActivityState>([
        ['process_data', { activityId: 'process_data', status: 'running' }],
      ])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/process_data/status',
        value: 'completed',
      }

      applyOperation(activities, operation)

      expect(activities.get('process_data')?.status).toBe('completed')
    })

    it('maps completed to success', () => {
      const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/task/status',
        value: 'completed',
      }

      applyOperation(activities, operation)

      expect(activities.get('task')?.status).toBe('completed')
    })

    it('maps failed to error', () => {
      const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/task/status',
        value: 'failed',
      }

      applyOperation(activities, operation)

      expect(activities.get('task')?.status).toBe('failed')
    })

    it('preserves retrying status without mapping', () => {
      const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'failed' }]])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/task/status',
        value: 'retrying',
      }

      applyOperation(activities, operation)

      expect(activities.get('task')?.status).toBe('retrying')
    })

    it('updates error_details', () => {
      const activities = new Map<string, ActivityState>([
        ['task', { activityId: 'task', status: 'failed', errorDetails: 'Old error' }],
      ])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/task/error_details',
        value: 'New error message',
      }

      applyOperation(activities, operation)

      expect(activities.get('task')?.errorDetails).toBe('New error message')
    })

    it('updates started_at timestamp', () => {
      const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/task/started_at',
        value: '2025-12-10T15:00:10Z',
      }

      applyOperation(activities, operation)

      expect(activities.get('task')?.startedAt).toBe('2025-12-10T15:00:10Z')
    })

    it('updates completed_at timestamp', () => {
      const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'completed' }]])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/task/completed_at',
        value: '2025-12-10T15:00:25Z',
      }

      applyOperation(activities, operation)

      expect(activities.get('task')?.completedAt).toBe('2025-12-10T15:00:25Z')
    })

    it('throws error if value is missing', () => {
      const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/task/status',
      }

      expect(() => applyOperation(activities, operation)).toThrow("Operation 'replace' requires a value")
    })

    it('throws error for unsupported field', () => {
      const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/task/unknown_field',
        value: 'value',
      }

      expect(() => applyOperation(activities, operation)).toThrow('Unsupported field')
    })

    it('creates activity when replacing status on non-existent activity', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/missing/status',
        value: 'running',
      }

      applyOperation(activities, operation)

      expect(activities.get('missing')).toEqual({ activityId: 'missing', status: 'running' })
    })

    it('throws when replacing a non-status field on non-existent activity', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/missing/started_at',
        value: '2025-12-10T15:00:05Z',
      }

      expect(() => applyOperation(activities, operation)).toThrow(
        "Cannot replace field 'started_at' on non-existent activity 'missing'"
      )
    })
  })

  describe('remove operation', () => {
    it('removes error_details', () => {
      const activities = new Map<string, ActivityState>([
        ['task', { activityId: 'task', status: 'failed', errorDetails: 'Some error' }],
      ])
      const operation: JsonPatchOperation = {
        op: 'remove',
        path: '/activities/task/error_details',
      }

      applyOperation(activities, operation)

      expect(activities.get('task')?.errorDetails).toBeNull()
    })

    it('throws when removing from non-existent activity', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'remove',
        path: '/activities/nonexistent/error_details',
      }

      expect(() => applyOperation(activities, operation)).toThrow('non-existent activity')
    })

    it('throws error when removing unsupported field', () => {
      const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
      const operation: JsonPatchOperation = {
        op: 'remove',
        path: '/activities/task/status',
      }

      expect(() => applyOperation(activities, operation)).toThrow("Only 'error_details' can be removed")
    })
  })

  describe('array index operations', () => {
    it('applies operation using array index', () => {
      const activities = new Map<string, ActivityState>([
        ['fetch_data', { activityId: 'fetch_data', status: 'pending' }],
        ['process_data', { activityId: 'process_data', status: 'pending' }],
      ])
      const activityArray: ActivityState[] = [
        { activityId: 'fetch_data', status: 'pending' },
        { activityId: 'process_data', status: 'pending' },
      ]
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/1/status',
        value: 'running',
      }

      applyOperation(activities, operation, activityArray)

      expect(activities.get('process_data')?.status).toBe('running')
    })

    it('throws error for invalid array index', () => {
      const activities = new Map<string, ActivityState>()
      const activityArray: ActivityState[] = []
      const operation: JsonPatchOperation = {
        op: 'replace',
        path: '/activities/0/status',
        value: 'running',
      }

      expect(() => applyOperation(activities, operation, activityArray)).toThrow('Activity not found at index')
    })

    it('throws when array index given but no activityArray provided', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'add',
        path: '/activities/0/status',
        value: 'running',
      }

      expect(() => applyOperation(activities, operation)).toThrow('Cannot resolve array index')
    })
  })

  describe('unsupported operations', () => {
    it('throws error for move operation', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'move',
        path: '/activities/task/status',
        from: '/activities/other/status',
      }

      expect(() => applyOperation(activities, operation)).toThrow("Operation 'move' is not supported")
    })

    it('throws error for copy operation', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'copy',
        path: '/activities/task/status',
        from: '/activities/other/status',
      }

      expect(() => applyOperation(activities, operation)).toThrow("Operation 'copy' is not supported")
    })

    it('throws error for test operation', () => {
      const activities = new Map<string, ActivityState>()
      const operation: JsonPatchOperation = {
        op: 'test',
        path: '/activities/task/status',
        value: 'running',
      }

      expect(() => applyOperation(activities, operation)).toThrow("Operation 'test' is not supported")
    })
  })
})

// ============================================================================
// Apply JSON Patch Tests
// ============================================================================

describe('applyJsonPatch', () => {
  it('applies multiple operations sequentially', () => {
    const activities = new Map<string, ActivityState>()
    const operations: JsonPatchOperation[] = [
      { op: 'add', path: '/activities/fetch_data/status', value: 'running' },
      { op: 'add', path: '/activities/process_data/status', value: 'pending' },
      { op: 'replace', path: '/activities/fetch_data/status', value: 'completed' },
    ]

    applyJsonPatch(activities, operations)

    expect(activities.get('fetch_data')?.status).toBe('completed')
    expect(activities.get('process_data')?.status).toBe('pending')
  })

  it('applies activity status change with error', () => {
    const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
    const operations: JsonPatchOperation[] = [
      { op: 'replace', path: '/activities/task/status', value: 'failed' },
      { op: 'add', path: '/activities/task/error_details', value: 'Connection timeout' },
    ]

    applyJsonPatch(activities, operations)

    expect(activities.get('task')).toEqual({
      activityId: 'task',
      status: 'failed',
      errorDetails: 'Connection timeout',
    })
  })

  it('throws error with context when operation fails', () => {
    const activities = new Map<string, ActivityState>()
    const operations: JsonPatchOperation[] = [
      { op: 'replace', path: '/activities/task/status' }, // Missing value
    ]

    expect(() => applyJsonPatch(activities, operations)).toThrow('Failed to apply operation replace')
    expect(() => applyJsonPatch(activities, operations)).toThrow('requires a value')
  })

  it('handles empty operations array', () => {
    const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])

    applyJsonPatch(activities, [])

    expect(activities.get('task')?.status).toBe('running')
  })

  it('applies output_data replace operation', () => {
    const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
    const operations: JsonPatchOperation[] = [
      { op: 'replace', path: '/activities/task/output_data', value: { job_id: 123, job_url: 'https://aap/jobs/123' } },
    ]

    applyJsonPatch(activities, operations)

    expect(activities.get('task')?.outputData).toEqual({ job_id: 123, job_url: 'https://aap/jobs/123' })
  })

  it('applies output_data add operation', () => {
    const activities = new Map<string, ActivityState>([['task', { activityId: 'task', status: 'running' }]])
    const operations: JsonPatchOperation[] = [
      { op: 'add', path: '/activities/task/output_data', value: { job_id: 456 } },
    ]

    applyJsonPatch(activities, operations)

    expect(activities.get('task')?.outputData).toEqual({ job_id: 456 })
  })
})

// ============================================================================
// Helper Function Tests
// ============================================================================

describe('buildActivityStateMap', () => {
  it('converts API activity data to map', () => {
    const apiActivities = [
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
    ]

    const map = buildActivityStateMap(apiActivities)

    expect(map.size).toBe(2)
    expect(map.get('fetch_data')).toEqual({
      activityId: 'fetch_data',
      status: 'completed',
      errorDetails: null,
      startedAt: '2025-12-10T15:00:05Z',
      completedAt: '2025-12-10T15:00:10Z',
    })
    expect(map.get('process_data')).toEqual({
      activityId: 'process_data',
      status: 'running',
      errorDetails: null,
      startedAt: '2025-12-10T15:00:10Z',
      completedAt: null,
    })
  })

  it('maps failed status to error', () => {
    const apiActivities = [
      {
        activity_id: 'task',
        status: 'failed' as const,
        error_details: 'Connection timeout',
        started_at: '2025-12-10T15:00:05Z',
        completed_at: '2025-12-10T15:00:10Z',
      },
    ]

    const map = buildActivityStateMap(apiActivities)

    expect(map.get('task')?.status).toBe('failed')
    expect(map.get('task')?.errorDetails).toBe('Connection timeout')
  })

  it('includes output_data in activity state', () => {
    const apiActivities = [
      {
        activity_id: 'aap_step',
        status: 'running' as const,
        error_details: null,
        output_data: { job_id: 789, job_url: 'https://aap.example.com/jobs/789' },
        started_at: '2025-12-10T15:00:05Z',
        completed_at: null,
      },
    ]

    const map = buildActivityStateMap(apiActivities)

    expect(map.get('aap_step')?.outputData).toEqual({
      job_id: 789,
      job_url: 'https://aap.example.com/jobs/789',
    })
  })

  it('handles empty array', () => {
    const map = buildActivityStateMap([])
    expect(map.size).toBe(0)
  })
})

describe('extractActivityMaps', () => {
  it('extracts status and error maps', () => {
    const activities = new Map<string, ActivityState>([
      ['fetch_data', { activityId: 'fetch_data', status: 'completed' }],
      ['process_data', { activityId: 'process_data', status: 'failed', errorDetails: 'Failed to process' }],
      ['send_notification', { activityId: 'send_notification', status: 'pending' }],
    ])

    const [statusMap, errorMap] = extractActivityMaps(activities)

    expect(statusMap.size).toBe(3)
    expect(statusMap.get('fetch_data')).toBe('completed')
    expect(statusMap.get('process_data')).toBe('failed')
    expect(statusMap.get('send_notification')).toBe('pending')

    expect(errorMap.size).toBe(1)
    expect(errorMap.get('process_data')).toBe('Failed to process')
  })

  it('handles activities without errors', () => {
    const activities = new Map<string, ActivityState>([
      ['task1', { activityId: 'task1', status: 'completed' }],
      ['task2', { activityId: 'task2', status: 'running' }],
    ])

    const [statusMap, errorMap] = extractActivityMaps(activities)

    expect(statusMap.size).toBe(2)
    expect(errorMap.size).toBe(0)
  })

  it('handles empty map', () => {
    const activities = new Map<string, ActivityState>()
    const [statusMap, errorMap] = extractActivityMaps(activities)

    expect(statusMap.size).toBe(0)
    expect(errorMap.size).toBe(0)
  })
})

describe('extractApprovalAudit', () => {
  it('returns null for null/undefined output', () => {
    expect(extractApprovalAudit(null)).toBeNull()
    expect(extractApprovalAudit(undefined)).toBeNull()
  })

  it('returns null when required fields are missing', () => {
    expect(extractApprovalAudit({ status: 'completed' })).toBeNull()
    expect(extractApprovalAudit({ decision: 'approved' })).toBeNull()
    expect(extractApprovalAudit({ decision: 'approved', decided_by: 'jsmith' })).toBeNull()
  })

  it('extracts approval audit from valid output data', () => {
    const result = extractApprovalAudit({
      status: 'completed',
      decision: 'approved',
      decided_by: 'jsmith',
      decided_at: '2026-06-15T08:00:01.000Z',
      decision_notes: 'LGTM',
    })

    expect(result).toEqual({
      decision: 'approved',
      decidedBy: 'jsmith',
      decidedAt: '2026-06-15T08:00:01.000Z',
      decisionNotes: 'LGTM',
    })
  })

  it('returns null for decision_notes when not present', () => {
    const result = extractApprovalAudit({
      decision: 'rejected',
      decided_by: 'admin',
      decided_at: '2026-06-15T09:00:00.000Z',
    })

    expect(result).toEqual({
      decision: 'rejected',
      decidedBy: 'admin',
      decidedAt: '2026-06-15T09:00:00.000Z',
      decisionNotes: null,
    })
  })

  it('returns null when decided_by is not a string', () => {
    expect(
      extractApprovalAudit({
        decision: 'approved',
        decided_by: 123,
        decided_at: '2026-06-15T08:00:01.000Z',
      })
    ).toBeNull()
  })
})

describe('parseCompositeKey', () => {
  it('returns base ID for non-composite key', () => {
    expect(parseCompositeKey('action-node')).toEqual({ baseId: 'action-node' })
  })

  it('returns base ID without iteration for plain node IDs', () => {
    const result = parseCompositeKey('fetch_data')
    expect(result.baseId).toBe('fetch_data')
    expect(result.iteration).toBeUndefined()
  })

  it('parses composite key with iteration number', () => {
    expect(parseCompositeKey('body-node#iter-0')).toEqual({ baseId: 'body-node', iteration: 0 })
  })

  it('parses composite key with higher iteration', () => {
    expect(parseCompositeKey('body-node#iter-5')).toEqual({ baseId: 'body-node', iteration: 5 })
  })

  it('handles node IDs containing hyphens', () => {
    expect(parseCompositeKey('my-complex-node-id#iter-2')).toEqual({
      baseId: 'my-complex-node-id',
      iteration: 2,
    })
  })

  it('does not split on hash without iter- prefix', () => {
    expect(parseCompositeKey('node#other')).toEqual({ baseId: 'node#other' })
  })
})

describe('latestActivityStateForCanvasNode', () => {
  it('returns the bare canvas record when there are no composite keys', () => {
    const canvas = { activityId: 'node-1', status: 'waiting' } as ActivityState
    const states = new Map<string, ActivityState>([['node-1', canvas]])
    expect(latestActivityStateForCanvasNode(states, 'node-1')).toBe(canvas)
  })

  it('prefers the highest #iter-N over a completed canvas record', () => {
    const canvas = { activityId: 'node-1', status: 'completed' } as ActivityState
    const iter3 = { activityId: 'node-1#iter-3', status: 'waiting', iteration: 3 } as ActivityState
    const states = new Map<string, ActivityState>([
      ['node-1', canvas],
      ['node-1#iter-0', { activityId: 'node-1#iter-0', status: 'completed', iteration: 0 }],
      ['node-1#iter-3', iter3],
    ])
    expect(latestActivityStateForCanvasNode(states, 'node-1')).toBe(iter3)
  })
})

describe('applyOperation — append', () => {
  it('appends a full activity record via /activities/- path', () => {
    const activities = new Map<string, ActivityState>()
    const operation: JsonPatchOperation = {
      op: 'add',
      path: '/activities/-',
      value: {
        activity_id: 'body-node#iter-1',
        status: 'running',
        error_details: null,
        output_data: null,
        started_at: '2026-07-01T10:00:00Z',
        completed_at: null,
        iteration: 1,
      },
    }

    applyOperation(activities, operation)

    expect(activities.get('body-node#iter-1')).toEqual({
      activityId: 'body-node#iter-1',
      status: 'running',
      errorDetails: null,
      outputData: null,
      startedAt: '2026-07-01T10:00:00Z',
      completedAt: null,
      iteration: 1,
    })
  })

  it('defaults missing fields to null/pending', () => {
    const activities = new Map<string, ActivityState>()
    const operation: JsonPatchOperation = {
      op: 'add',
      path: '/activities/-',
      value: { activity_id: 'minimal-node' },
    }

    applyOperation(activities, operation)

    const state = activities.get('minimal-node')
    expect(state?.status).toBe('pending')
    expect(state?.errorDetails).toBeNull()
    expect(state?.outputData).toBeNull()
    expect(state?.startedAt).toBeNull()
    expect(state?.completedAt).toBeNull()
    expect(state?.iteration).toBeNull()
  })

  it('throws when value is not an object', () => {
    const activities = new Map<string, ActivityState>()
    const operation: JsonPatchOperation = {
      op: 'add',
      path: '/activities/-',
      value: 'not-an-object',
    }

    expect(() => applyOperation(activities, operation)).toThrow('requires an activity object')
  })

  it('throws when value is null', () => {
    const activities = new Map<string, ActivityState>()
    const operation: JsonPatchOperation = {
      op: 'add',
      path: '/activities/-',
      value: null,
    }

    expect(() => applyOperation(activities, operation)).toThrow('requires an activity object')
  })

  it('throws when activity_id is missing', () => {
    const activities = new Map<string, ActivityState>()
    const operation: JsonPatchOperation = {
      op: 'add',
      path: '/activities/-',
      value: { status: 'running' },
    }

    expect(() => applyOperation(activities, operation)).toThrow('missing activity_id')
  })
})

describe('iteration field handling', () => {
  it('applyOperation replaces iteration field', () => {
    const activities = new Map<string, ActivityState>([
      ['loop-body', { activityId: 'loop-body', status: 'running', iteration: 0 }],
    ])
    const operation: JsonPatchOperation = {
      op: 'replace',
      path: '/activities/loop-body/iteration',
      value: 2,
    }

    applyOperation(activities, operation)

    expect(activities.get('loop-body')?.iteration).toBe(2)
  })

  it('buildActivityStateMap includes iteration field', () => {
    const apiActivities = [
      {
        activity_id: 'body-node#iter-0',
        status: 'completed' as const,
        error_details: null,
        started_at: '2026-07-01T10:00:00Z',
        completed_at: '2026-07-01T10:00:05Z',
        iteration: 0,
      },
      {
        activity_id: 'body-node#iter-1',
        status: 'running' as const,
        error_details: null,
        started_at: '2026-07-01T10:00:06Z',
        completed_at: null,
        iteration: 1,
      },
    ]

    const map = buildActivityStateMap(apiActivities)

    expect(map.get('body-node#iter-0')?.iteration).toBe(0)
    expect(map.get('body-node#iter-1')?.iteration).toBe(1)
  })

  it('buildActivityStateMap defaults iteration to undefined when absent', () => {
    const apiActivities = [
      {
        activity_id: 'plain-node',
        status: 'completed' as const,
        error_details: null,
        started_at: null,
        completed_at: null,
      },
    ]

    const map = buildActivityStateMap(apiActivities)

    expect(map.get('plain-node')?.iteration).toBeUndefined()
  })
})

describe('buildLatestIterationMap', () => {
  it('returns empty map when no composite keys exist', () => {
    const states = new Map<string, ActivityState>([['nodeA', { activityId: 'nodeA', status: 'completed' }]])
    expect(buildLatestIterationMap(states).size).toBe(0)
  })

  it('returns latest iteration state per base ID', () => {
    const states = new Map<string, ActivityState>([
      ['nodeA#iter-0', { activityId: 'nodeA#iter-0', status: 'completed', iteration: 0 }],
      ['nodeA#iter-1', { activityId: 'nodeA#iter-1', status: 'running', iteration: 1 }],
    ])
    const result = buildLatestIterationMap(states)
    expect(result.get('nodeA')?.status).toBe('running')
    expect(result.get('nodeA')?.iteration).toBe(1)
  })

  it('resets behind-iteration siblings to pending', () => {
    const states = new Map<string, ActivityState>([
      ['Script2#iter-0', { activityId: 'Script2#iter-0', status: 'completed', iteration: 0 }],
      ['Script2#iter-1', { activityId: 'Script2#iter-1', status: 'running', iteration: 1 }],
      ['Script4#iter-0', { activityId: 'Script4#iter-0', status: 'completed', iteration: 0 }],
    ])
    const result = buildLatestIterationMap(states)

    expect(result.get('Script2')?.status).toBe('running')
    expect(result.get('Script4')?.status).toBe('pending')
    expect(result.get('Script4')?.iteration).toBe(1)
  })

  it('does not reset when all nodes are on the same iteration', () => {
    const states = new Map<string, ActivityState>([
      ['Script2#iter-1', { activityId: 'Script2#iter-1', status: 'running', iteration: 1 }],
      ['Script4#iter-1', { activityId: 'Script4#iter-1', status: 'pending', iteration: 1 }],
    ])
    const result = buildLatestIterationMap(states)

    expect(result.get('Script2')?.status).toBe('running')
    expect(result.get('Script4')?.status).toBe('pending')
  })

  it('ignores non-composite keys', () => {
    const states = new Map<string, ActivityState>([
      ['nodeA', { activityId: 'nodeA', status: 'completed' }],
      ['nodeA#iter-0', { activityId: 'nodeA#iter-0', status: 'running', iteration: 0 }],
    ])
    const result = buildLatestIterationMap(states)

    expect(result.size).toBe(1)
    expect(result.get('nodeA')?.status).toBe('running')
  })

  it('resets loop body nodes with only base records when sibling has higher iteration', () => {
    const loopBodyGroups = new Map([['loop-1', new Set(['Script2', 'Script4'])]])
    const states = new Map<string, ActivityState>([
      ['Script2', { activityId: 'Script2', status: 'completed' }],
      ['Script4', { activityId: 'Script4', status: 'completed' }],
      ['Script2#iter-1', { activityId: 'Script2#iter-1', status: 'running', iteration: 1 }],
    ])
    const result = buildLatestIterationMap(states, loopBodyGroups)

    expect(result.get('Script2')?.status).toBe('running')
    expect(result.get('Script4')?.status).toBe('pending')
    expect(result.get('Script4')?.iteration).toBe(1)
  })

  it('does not reset non-loop nodes even when loop iteration is active', () => {
    const loopBodyGroups = new Map([['loop-1', new Set(['Script2', 'Script4'])]])
    const states = new Map<string, ActivityState>([
      ['pre-loop-task', { activityId: 'pre-loop-task', status: 'completed' }],
      ['Script2', { activityId: 'Script2', status: 'completed' }],
      ['Script4', { activityId: 'Script4', status: 'completed' }],
      ['Script2#iter-1', { activityId: 'Script2#iter-1', status: 'running', iteration: 1 }],
    ])
    const result = buildLatestIterationMap(states, loopBodyGroups)

    expect(result.has('pre-loop-task')).toBe(false)
    expect(result.get('Script4')?.status).toBe('pending')
  })

  it('does not reset loop body nodes when no composite keys exist (first iteration)', () => {
    const loopBodyGroups = new Map([['loop-1', new Set(['Script2', 'Script4'])]])
    const states = new Map<string, ActivityState>([
      ['Script2', { activityId: 'Script2', status: 'running' }],
      ['Script4', { activityId: 'Script4', status: 'pending' }],
    ])
    const result = buildLatestIterationMap(states, loopBodyGroups)

    expect(result.size).toBe(0)
  })

  it('does not cross-contaminate iterations between independent loops', () => {
    const loopBodyGroups = new Map([
      ['loopA', new Set(['A1', 'A2'])],
      ['loopB', new Set(['B1', 'B2'])],
    ])
    const states = new Map<string, ActivityState>([
      ['A1#iter-1', { activityId: 'A1#iter-1', status: 'completed', iteration: 1 }],
      ['A1#iter-2', { activityId: 'A1#iter-2', status: 'completed', iteration: 2 }],
      ['A1#iter-3', { activityId: 'A1#iter-3', status: 'running', iteration: 3 }],
      ['A2#iter-1', { activityId: 'A2#iter-1', status: 'completed', iteration: 1 }],
      ['A2#iter-2', { activityId: 'A2#iter-2', status: 'completed', iteration: 2 }],
      ['B1#iter-1', { activityId: 'B1#iter-1', status: 'completed', iteration: 1 }],
      ['B2#iter-1', { activityId: 'B2#iter-1', status: 'running', iteration: 1 }],
    ])
    const result = buildLatestIterationMap(states, loopBodyGroups)

    // Loop A at iteration 3: A2 behind → PENDING
    expect(result.get('A1')?.status).toBe('running')
    expect(result.get('A1')?.iteration).toBe(3)
    expect(result.get('A2')?.status).toBe('pending')
    expect(result.get('A2')?.iteration).toBe(3)

    // Loop B at iteration 1: both at max → keep real status
    expect(result.get('B1')?.status).toBe('completed')
    expect(result.get('B2')?.status).toBe('running')
  })
})
