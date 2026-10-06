import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

import { useAutoWaitingNodeDetection } from './useAutoWaitingNodeDetection'

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
      setStatus: (nodeId: string, status: string) => void
      clear: () => void
    }
  }
).__test__

describe('useAutoWaitingNodeDetection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    testHelpers.clear()
  })

  afterEach(() => {
    testHelpers.clear()
  })

  it('fetches when a node enters waiting status', async () => {
    const fetchForNode = vi.fn().mockResolvedValue({ id: 'task-1' })
    const onDetected = vi.fn()

    renderHook(() =>
      useAutoWaitingNodeDetection({
        executionId: 'exec-1',
        fetchForNode,
        onDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('node-1', 'waiting')
    })

    await vi.waitFor(() => expect(fetchForNode).toHaveBeenCalledWith('node-1'))
    await vi.waitFor(() => expect(onDetected).toHaveBeenCalledWith({ id: 'task-1' }))
  })

  it('respects shouldDetectNode filter', async () => {
    const fetchForNode = vi.fn().mockResolvedValue({ id: 'fp-1' })
    const onDetected = vi.fn()

    renderHook(() =>
      useAutoWaitingNodeDetection({
        executionId: 'exec-1',
        shouldDetectNode: (nodeId) => nodeId.startsWith('form_'),
        fetchForNode,
        onDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('approval-1', 'waiting')
    })

    expect(fetchForNode).not.toHaveBeenCalled()

    act(() => {
      testHelpers.setStatus('form_collect', 'waiting')
    })

    await vi.waitFor(() => expect(fetchForNode).toHaveBeenCalledWith('form_collect'))
  })

  it('does nothing when executionId is undefined', () => {
    const fetchForNode = vi.fn()
    const onDetected = vi.fn()

    renderHook(() =>
      useAutoWaitingNodeDetection({
        executionId: undefined,
        fetchForNode,
        onDetected,
      })
    )

    act(() => {
      testHelpers.setStatus('node-1', 'waiting')
    })

    expect(fetchForNode).not.toHaveBeenCalled()
  })
})
