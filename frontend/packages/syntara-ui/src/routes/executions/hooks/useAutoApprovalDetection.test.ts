import type { Approval } from '@syntara/contracts'
import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

import { useAutoApprovalDetection } from './useAutoApprovalDetection'

vi.mock('../../workflows/stores/useExecutionStore', () => {
  const activityStates = new Map<string, { status: string }>()
  const subscribers = new Set<() => void>()

  return {
    useExecutionStore: Object.assign(
      vi.fn(() => ({ activityStates })),
      {
        getState: () => ({ activityStates }),
        subscribe: (fn: () => void) => {
          subscribers.add(fn)
          return () => subscribers.delete(fn)
        },
        __test__: {
          activityStates,
          subscribers,
          setStatus: (nodeId: string, status: string) => {
            activityStates.set(nodeId, { status })
            for (const fn of subscribers) fn()
          },
          clear: () => {
            activityStates.clear()
            subscribers.clear()
          },
        },
      }
    ),
  }
})

const testHelpers = (
  useExecutionStore as unknown as {
    __test__: {
      activityStates: Map<string, { status: string }>
      subscribers: Set<() => void>
      setStatus: (nodeId: string, status: string) => void
      clear: () => void
    }
  }
).__test__

const mockApproval: Approval = {
  id: 'approval-1',
  project_id: 'project-1',
  name: 'Test Approval',
  status: 'pending',
  execution_id: 'exec-1',
  approval_node_id: 'approval-node-1',
  workflow_context: {
    workflow_id: 'wfv-1',
    workflow_name: 'Test Workflow',
    inputs: {},
  },
  next_step_approved: { id: 'step-a', name: 'Approved Step', type: 'task' },
  next_step_rejected: { id: 'step-r', name: 'Rejected Step', type: 'task' },
  created_at: '2026-01-01T00:00:00Z',
}

describe('useAutoApprovalDetection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    testHelpers.clear()
  })

  afterEach(() => {
    testHelpers.clear()
  })

  it('fetches approval when any node enters waiting status', async () => {
    const fetchForNode = vi.fn().mockResolvedValue(mockApproval)
    const onApprovalDetected = vi.fn()

    renderHook(() =>
      useAutoApprovalDetection({
        executionId: 'exec-1',
        fetchForNode,
        onApprovalDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('approval-node-1', 'waiting')
    })

    await vi.waitFor(() => expect(fetchForNode).toHaveBeenCalledWith('approval-node-1'))
    await vi.waitFor(() => expect(onApprovalDetected).toHaveBeenCalledWith(mockApproval))
  })

  it('does not re-fetch for the same node after initial detection', async () => {
    const fetchForNode = vi.fn().mockResolvedValue(mockApproval)
    const onApprovalDetected = vi.fn()

    renderHook(() =>
      useAutoApprovalDetection({
        executionId: 'exec-1',
        fetchForNode,
        onApprovalDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('approval-node-1', 'waiting')
    })

    await vi.waitFor(() => expect(fetchForNode).toHaveBeenCalledTimes(1))

    act(() => {
      testHelpers.setStatus('approval-node-1', 'waiting')
    })

    expect(fetchForNode).toHaveBeenCalledTimes(1)
  })

  it('does not trigger for non-waiting statuses', () => {
    const fetchForNode = vi.fn()
    const onApprovalDetected = vi.fn()

    renderHook(() =>
      useAutoApprovalDetection({
        executionId: 'exec-1',
        fetchForNode,
        onApprovalDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('task-1', 'running')
    })

    expect(fetchForNode).not.toHaveBeenCalled()
  })

  it('does nothing when executionId is undefined', () => {
    const fetchForNode = vi.fn()
    const onApprovalDetected = vi.fn()

    renderHook(() =>
      useAutoApprovalDetection({
        executionId: undefined,
        fetchForNode,
        onApprovalDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('approval-node-1', 'waiting')
    })

    expect(fetchForNode).not.toHaveBeenCalled()
  })

  it('ignores nodes with completed or running status', () => {
    const fetchForNode = vi.fn()
    const onApprovalDetected = vi.fn()

    renderHook(() =>
      useAutoApprovalDetection({
        executionId: 'exec-1',
        fetchForNode,
        onApprovalDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('node-a', 'completed')
      testHelpers.setStatus('node-b', 'running')
      testHelpers.setStatus('node-c', 'pending')
    })

    expect(fetchForNode).not.toHaveBeenCalled()
    expect(onApprovalDetected).not.toHaveBeenCalled()
  })

  it('re-fetches when a node leaves waiting and enters waiting again', async () => {
    const fetchForNode = vi.fn().mockResolvedValue(mockApproval)
    const onApprovalDetected = vi.fn()

    renderHook(() =>
      useAutoApprovalDetection({
        executionId: 'exec-1',
        fetchForNode,
        onApprovalDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('approval-node-1', 'waiting')
    })
    await vi.waitFor(() => expect(onApprovalDetected).toHaveBeenCalledTimes(1))

    act(() => {
      testHelpers.setStatus('approval-node-1', 'completed')
    })
    act(() => {
      testHelpers.setStatus('approval-node-1', 'waiting')
    })

    await vi.waitFor(() => expect(fetchForNode).toHaveBeenCalledTimes(2))
  })
})
