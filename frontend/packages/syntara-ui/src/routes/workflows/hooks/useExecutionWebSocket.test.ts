/**
 * Execution WebSocket Hook Tests
 *
 * Integration tests for WebSocket connection lifecycle and message handling
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'

import * as websocketModule from '../../../lib/websocket/hooks'
import type { ConnectionState } from '../../../lib/websocket/types'
import type { ExecutionSnapshotMessage, ActivityPatchMessage, Execution } from '../execution/types'
import { useExecutionStore } from '../stores/useExecutionStore'

import { useExecutionWebSocket } from './useExecutionWebSocket'

// ============================================================================
// Mock Setup
// ============================================================================

vi.mock('../../../lib/websocket/hooks', () => ({
  useWebSocket: vi.fn(),
  buildExecutionChannelPath: (executionId: string, replay?: string) => ({
    id: `execution_${executionId}`,
    path: replay
      ? `/ws/workflows/v1/executions/${executionId}?replay=${replay}`
      : `/ws/workflows/v1/executions/${executionId}`,
  }),
}))

// ============================================================================
// Test Helpers
// ============================================================================

function createInitialSnapshotMessage(): ExecutionSnapshotMessage {
  return {
    type: 'initial_snapshot',
    execution_id: 'exec-123',
    event_id: '1691431234567-0',
    timestamp: '2025-12-10T15:00:05Z',
    execution: {
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
      ],
    } as unknown as Execution,
  }
}

function createActivityPatchMessage(): ActivityPatchMessage {
  return {
    type: 'activity_patch',
    execution_id: 'exec-123',
    event_id: '1691431234568-0',
    timestamp: '2025-12-10T15:00:15Z',
    ops: [
      {
        op: 'replace',
        path: '/activities/process_data/status',
        value: 'completed',
      },
    ],
  }
}

function createFinalSnapshotMessage(): ExecutionSnapshotMessage {
  return {
    type: 'final_snapshot',
    execution_id: 'exec-123',
    event_id: '1691431234599-0',
    timestamp: '2025-12-10T15:05:30Z',
    execution: {
      id: 'exec-123',
      createdAt: '2025-12-10T15:00:00Z',
      updatedAt: '2025-12-10T15:05:30Z',
      workflow_id: 'workflow-456',
      workflow_version_id: 'version-789',
      status: 'completed',
      started_at: '2025-12-10T15:00:05Z',
      completed_at: '2025-12-10T15:05:30Z',
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
          status: 'completed',
          error_details: null,
          started_at: '2025-12-10T15:00:10Z',
          completed_at: '2025-12-10T15:00:25Z',
        },
      ],
    } as unknown as Execution,
  }
}

// ============================================================================
// Tests
// ============================================================================

describe('useExecutionWebSocket', () => {
  let mockOnMessage: ((message: unknown) => void) | undefined
  let mockOnStateChange: ((state: ConnectionState) => void) | undefined

  beforeEach(() => {
    useExecutionStore.getState().reset()
    vi.clearAllMocks()

    // Setup mock WebSocket hook
    vi.mocked(websocketModule.useWebSocket).mockImplementation((_channel, options) => {
      mockOnMessage = options?.onMessage as ((message: unknown) => void) | undefined
      mockOnStateChange = options?.onStateChange as ((state: ConnectionState) => void) | undefined

      return {
        sendWrapped: vi.fn(),
        sendRaw: vi.fn(),
        connectionState: 'connected',
        isConnected: true,
        connect: vi.fn(),
        disconnect: vi.fn(),
        error: undefined,
      }
    })
  })

  describe('initialization', () => {
    it('connects to WebSocket on mount', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      expect(websocketModule.useWebSocket).toHaveBeenCalled()
    })

    it('requests replay from beginning by default', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      const callArgs = vi.mocked(websocketModule.useWebSocket).mock.calls[0]
      expect(callArgs[0].path).toContain('?replay=0')
    })

    it('does not request replay when replayFromBeginning is false', () => {
      renderHook(() => useExecutionWebSocket('exec-123', { replayFromBeginning: false }))

      const callArgs = vi.mocked(websocketModule.useWebSocket).mock.calls[0]
      expect(callArgs[0].path).not.toContain('replay')
    })

    it('does not connect when enabled is false', () => {
      renderHook(() => useExecutionWebSocket('exec-123', { enabled: false }))

      const callArgs = vi.mocked(websocketModule.useWebSocket).mock.calls[0]
      expect(callArgs[1]?.autoConnect).toBe(false)
    })
  })

  describe('initial_snapshot message', () => {
    it('loads execution state from initial_snapshot', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      const message = createInitialSnapshotMessage()
      act(() => {
        mockOnMessage?.(message)
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.executionId).toBe('exec-123')
      expect(storeState.visualization).not.toBeNull()
      expect(storeState.activityStates.size).toBe(2)
    })

    it('sets last event ID from initial_snapshot', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      const message = createInitialSnapshotMessage()
      act(() => {
        mockOnMessage?.(message)
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.lastEventId).toBe('1691431234567-0')
    })

    it('maps activity statuses correctly', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      const message = createInitialSnapshotMessage()
      act(() => {
        mockOnMessage?.(message)
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.activityStates.get('fetch_data')?.status).toBe('completed')
      expect(storeState.activityStates.get('process_data')?.status).toBe('running')
    })
  })

  describe('activity_patch message', () => {
    function setupWithInitialState() {
      renderHook(() => useExecutionWebSocket('exec-123'))

      const initialMessage = createInitialSnapshotMessage()
      act(() => {
        mockOnMessage?.(initialMessage)
      })
    }

    it('applies JSON Patch operations', () => {
      setupWithInitialState()
      const patchMessage = createActivityPatchMessage()
      act(() => {
        mockOnMessage?.(patchMessage)
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.activityStates.get('process_data')?.status).toBe('completed')
    })

    it('updates last event ID', () => {
      setupWithInitialState()
      const patchMessage = createActivityPatchMessage()
      act(() => {
        mockOnMessage?.(patchMessage)
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.lastEventId).toBe('1691431234568-0')
    })

    it('applies multiple patches sequentially', () => {
      setupWithInitialState()
      act(() => {
        mockOnMessage?.(createActivityPatchMessage())
        mockOnMessage?.({
          type: 'activity_patch',
          execution_id: 'exec-123',
          event_id: '1691431234568-1',
          timestamp: '2025-12-10T15:00:16Z',
          ops: [
            {
              op: 'replace',
              path: '/activities/fetch_data/status',
              value: 'failed',
            },
            {
              op: 'add',
              path: '/activities/fetch_data/error_details',
              value: 'Connection timeout',
            },
          ],
        })
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.activityStates.get('process_data')?.status).toBe('completed')
      expect(storeState.activityStates.get('fetch_data')?.status).toBe('failed')
      expect(storeState.activityErrors.get('fetch_data')).toBe('Connection timeout')
    })
  })

  describe('final_snapshot message', () => {
    it('loads final execution state', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      const message = createFinalSnapshotMessage()
      act(() => {
        mockOnMessage?.(message)
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.visualization?.status).toBe('completed')
    })

    it('marks execution as complete', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      const message = createFinalSnapshotMessage()
      act(() => {
        mockOnMessage?.(message)
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.isComplete).toBe(true)
    })

    it('calls onExecutionComplete callback', () => {
      const onComplete = vi.fn()
      renderHook(() => useExecutionWebSocket('exec-123', { onExecutionComplete: onComplete }))

      const message = createFinalSnapshotMessage()
      act(() => {
        mockOnMessage?.(message)
      })

      expect(onComplete).toHaveBeenCalled()
    })

    it('sets last event ID', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      const message = createFinalSnapshotMessage()
      act(() => {
        mockOnMessage?.(message)
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.lastEventId).toBe('1691431234599-0')
    })
  })

  describe('connection state management', () => {
    it('sets connected state', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      act(() => {
        mockOnStateChange?.('connected')
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.isConnected).toBe(true)
      expect(storeState.isStale).toBe(false)
    })

    it('sets stale state on reconnecting', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      act(() => {
        mockOnStateChange?.('reconnecting')
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.isConnected).toBe(false)
      expect(storeState.isStale).toBe(true)
    })

    it('sets stale state on disconnected', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      act(() => {
        mockOnStateChange?.('disconnected')
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.isConnected).toBe(false)
      expect(storeState.isStale).toBe(true)
    })

    it('sets stale state on failed', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      act(() => {
        mockOnStateChange?.('failed')
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.isConnected).toBe(false)
      expect(storeState.isStale).toBe(true)
    })

    it('does not mark stale after disconnect when execution is complete', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      act(() => {
        mockOnMessage?.(createFinalSnapshotMessage())
      })
      act(() => {
        mockOnStateChange?.('disconnected')
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.isComplete).toBe(true)
      expect(storeState.isConnected).toBe(false)
      expect(storeState.isStale).toBe(false)
    })

    it('calls onConnectionStateChange callback', () => {
      const onStateChange = vi.fn()
      renderHook(() => useExecutionWebSocket('exec-123', { onConnectionStateChange: onStateChange }))

      act(() => {
        mockOnStateChange?.('connected')
      })

      expect(onStateChange).toHaveBeenCalledWith(true, false)
    })
  })

  describe('message flow', () => {
    it('handles complete execution flow', () => {
      const onComplete = vi.fn()
      renderHook(() => useExecutionWebSocket('exec-123', { onExecutionComplete: onComplete }))

      // 1. Initial snapshot
      act(() => {
        mockOnMessage?.(createInitialSnapshotMessage())
      })

      let storeState = useExecutionStore.getState()
      expect(storeState.activityStates.get('process_data')?.status).toBe('running')

      // 2. Activity patch
      act(() => {
        mockOnMessage?.(createActivityPatchMessage())
      })

      storeState = useExecutionStore.getState()
      expect(storeState.activityStates.get('process_data')?.status).toBe('completed')

      // 3. Final snapshot
      act(() => {
        mockOnMessage?.(createFinalSnapshotMessage())
      })

      storeState = useExecutionStore.getState()
      expect(storeState.isComplete).toBe(true)
      expect(onComplete).toHaveBeenCalled()
    })

    it('handles multiple activity updates', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))

      // Initial state
      act(() => {
        mockOnMessage?.(createInitialSnapshotMessage())
      })

      // Multiple patches
      act(() => {
        mockOnMessage?.(createActivityPatchMessage())
        mockOnMessage?.({
          type: 'activity_patch',
          execution_id: 'exec-123',
          event_id: '1691431234568-1',
          timestamp: '2025-12-10T15:00:20Z',
          ops: [
            {
              op: 'add',
              path: '/activities/send_notification/status',
              value: 'running',
            },
          ],
        })
        mockOnMessage?.({
          type: 'activity_patch',
          execution_id: 'exec-123',
          event_id: '1691431234568-2',
          timestamp: '2025-12-10T15:00:25Z',
          ops: [
            {
              op: 'replace',
              path: '/activities/send_notification/status',
              value: 'completed',
            },
          ],
        })
      })

      const storeState = useExecutionStore.getState()
      expect(storeState.activityStates.get('process_data')?.status).toBe('completed')
      expect(storeState.activityStates.get('send_notification')?.status).toBe('completed')
      expect(storeState.lastEventId).toBe('1691431234568-2')
    })
  })

  describe('server error events', () => {
    function sendErrorEvent(code: string) {
      act(() => {
        mockOnMessage?.({ event_type: 'error', data: { code }, event_id: null, timestamp: '2025-12-10T15:00:00Z' })
      })
    }

    it('EVENTS_EXPIRED marks execution complete', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))
      sendErrorEvent('EVENTS_EXPIRED')
      expect(useExecutionStore.getState().isComplete).toBe(true)
    })

    it('EVENTS_EXPIRED calls onExecutionComplete callback', () => {
      const onComplete = vi.fn()
      renderHook(() => useExecutionWebSocket('exec-123', { onExecutionComplete: onComplete }))
      sendErrorEvent('EVENTS_EXPIRED')
      expect(onComplete).toHaveBeenCalledTimes(1)
    })

    it('INTERNAL_ERROR does not mark execution complete', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))
      sendErrorEvent('INTERNAL_ERROR')
      expect(useExecutionStore.getState().isComplete).toBe(false)
    })

    it('INTERNAL_ERROR does not call onExecutionComplete', () => {
      const onComplete = vi.fn()
      renderHook(() => useExecutionWebSocket('exec-123', { onExecutionComplete: onComplete }))
      sendErrorEvent('INTERNAL_ERROR')
      expect(onComplete).not.toHaveBeenCalled()
    })

    it('STREAM_TIMEOUT does not mark execution complete', () => {
      renderHook(() => useExecutionWebSocket('exec-123'))
      sendErrorEvent('STREAM_TIMEOUT')
      expect(useExecutionStore.getState().isComplete).toBe(false)
    })
  })

  describe('cleanup', () => {
    it('disconnects on unmount', () => {
      const mockDisconnect = vi.fn()

      vi.mocked(websocketModule.useWebSocket).mockReturnValue({
        sendWrapped: vi.fn(),
        sendRaw: vi.fn(),
        connectionState: 'connected',
        isConnected: true,
        connect: vi.fn(),
        disconnect: mockDisconnect,
        error: undefined,
      })

      const { unmount } = renderHook(() => useExecutionWebSocket('exec-123'))

      unmount()

      expect(mockDisconnect).toHaveBeenCalled()
    })
  })

  describe('return values', () => {
    it('returns connection state', () => {
      const { result } = renderHook(() => useExecutionWebSocket('exec-123'))

      expect(result.current.isConnected).toBe(true)
      expect(result.current.isStale).toBe(false)
      expect(result.current.isComplete).toBe(false)
    })

    it('provides connect and disconnect functions', () => {
      const { result } = renderHook(() => useExecutionWebSocket('exec-123'))

      expect(typeof result.current.connect).toBe('function')
      expect(typeof result.current.disconnect).toBe('function')
    })
  })
})
