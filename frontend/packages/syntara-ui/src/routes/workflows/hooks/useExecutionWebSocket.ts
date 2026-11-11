/**
 * Execution WebSocket Hook
 *
 * React hook for real-time execution streaming via WebSocket.
 * Handles initial_snapshot, activity_patch, execution_patch, and final_snapshot messages.
 * Supports auto-reconnection with event replay from last known state.
 */

import { useEffect, useCallback, useState, useMemo } from 'react'

import { buildExecutionChannelPath } from '../../../lib/websocket/channels'
import { useWebSocket } from '../../../lib/websocket/hooks'
import type { WebSocketMessage } from '../execution/types'
import { useExecutionStore } from '../stores/useExecutionStore'

// ============================================================================
// Hook Options
// ============================================================================

export type UseExecutionWebSocketOptions = {
  /**
   * Whether to enable WebSocket connection
   * @default true
   */
  enabled?: boolean

  /**
   * Whether to replay from beginning (sends replay=0)
   * If false, only streams new events after connection
   * @default true
   */
  replayFromBeginning?: boolean

  /**
   * Callback when connection state changes
   */
  onConnectionStateChange?: (connected: boolean, stale: boolean) => void

  /**
   * Callback when execution completes (final_snapshot received)
   */
  onExecutionComplete?: () => void
}

// ============================================================================
// Hook Return Type
// ============================================================================

export type UseExecutionWebSocketReturn = {
  /** Whether WebSocket is connected */
  isConnected: boolean
  /** Whether connection is stale (disconnected but reconnecting) */
  isStale: boolean
  /** Whether execution is complete (final_snapshot received) */
  isComplete: boolean
  /** Last error */
  error: string | undefined
  /** Manually connect to WebSocket */
  connect: () => void
  /** Manually disconnect from WebSocket */
  disconnect: () => void
}

// ============================================================================
// Hook Implementation
// ============================================================================

/**
 * Hook to stream execution updates via WebSocket
 *
 * Message Flow:
 * 1. Connect with replay=0 to receive full state
 * 2. Receive initial_snapshot (full execution state)
 * 3. Receive activity_patch messages (incremental updates)
 * 4. Receive final_snapshot when execution completes
 * 5. Server disconnects after final_snapshot
 *
 * Auto-reconnection:
 * - On disconnect, sets isStale=true and attempts reconnection
 * - Reconnects with replay=lastEventId to resume from last known state
 * - Exponential backoff: 1s, 2s, 4s, 8s, max 30s (configured in WebSocket store)
 *
 * @param executionId - Execution ID to stream
 * @param options - Hook options
 * @returns WebSocket connection state
 *
 * @example
 * ```tsx
 * function ExecutionVisualization({ executionId }: Props) {
 *   const { isConnected, isStale, isComplete } = useExecutionWebSocket(executionId, {
 *     onExecutionComplete: () => console.log('Execution finished!')
 *   })
 *
 *   if (isComplete) {
 *     return <CompletedBadge />
 *   }
 *
 *   return (
 *     <>
 *       {isStale && <StaleWarning />}
 *       <ExecutionGraph />
 *     </>
 *   )
 * }
 * ```
 */
export function useExecutionWebSocket(
  executionId: string,
  options: UseExecutionWebSocketOptions = {}
): UseExecutionWebSocketReturn {
  const { enabled = true, replayFromBeginning = true, onConnectionStateChange, onExecutionComplete } = options

  // Store actions
  const setExecution = useExecutionStore((state) => state.setExecution)
  const applyPatch = useExecutionStore((state) => state.applyPatch)
  const applyExecutionPatch = useExecutionStore((state) => state.applyExecutionPatch)
  const setComplete = useExecutionStore((state) => state.setComplete)
  const setConnectionState = useExecutionStore((state) => state.setConnectionState)
  const setLastEventId = useExecutionStore((state) => state.setLastEventId)

  // Store selectors
  const lastEventId = useExecutionStore((state) => state.lastEventId)
  const isComplete = useExecutionStore((state) => state.isComplete)

  // Track reconnection state
  const [isReconnecting, setIsReconnecting] = useState(false)

  // Determine replay parameter
  // - First connection: replay from beginning (if enabled)
  // - Reconnection: replay from last event ID
  const replayParam = useMemo(() => {
    if (isReconnecting && lastEventId) {
      return lastEventId
    }
    if (replayFromBeginning) {
      return '0'
    }
    return undefined
  }, [isReconnecting, lastEventId, replayFromBeginning])

  // Build channel configuration with replay support
  const channel = useMemo(() => buildExecutionChannelPath(executionId, replayParam), [executionId, replayParam])

  // Handle incoming WebSocket messages
  const handleMessage = useCallback(
    (message: WebSocketMessage) => {
      const msg = message as unknown as Record<string, unknown>

      // Server error envelope: {event_type: 'error', data: {code: ...}}
      // Distinct from the typed streaming messages which use the `type` field.
      if (msg['event_type'] === 'error') {
        const code = (msg['data'] as Record<string, unknown> | undefined)?.['code']
        if (code === 'EVENTS_EXPIRED') {
          // Stream events have expired — the execution completed before we connected.
          // REST API has the final state; trigger a refetch and stop streaming.
          setComplete(true)
          onExecutionComplete?.()
        }
        // INTERNAL_ERROR / STREAM_TIMEOUT: server will close the connection;
        // the reconnect loop handles transient failures.
        return
      }

      switch ((msg as unknown as WebSocketMessage).type) {
        case 'initial_snapshot': {
          const snapshot = msg as unknown as WebSocketMessage & { type: 'initial_snapshot' }
          setExecution(snapshot.execution)
          setLastEventId(snapshot.event_id)
          setIsReconnecting(false)
          break
        }

        case 'activity_patch': {
          const patch = msg as unknown as WebSocketMessage & { type: 'activity_patch' }
          applyPatch(patch.ops, patch.event_id)
          break
        }

        case 'execution_patch': {
          const patch = msg as unknown as WebSocketMessage & { type: 'execution_patch' }
          applyExecutionPatch(patch.ops, patch.event_id)
          break
        }

        case 'final_snapshot': {
          const snapshot = msg as unknown as WebSocketMessage & { type: 'final_snapshot' }
          setExecution(snapshot.execution)
          setLastEventId(snapshot.event_id)
          setComplete(true)
          onExecutionComplete?.()
          break
        }

        default:
          break
      }
    },
    [setExecution, applyPatch, applyExecutionPatch, setComplete, setLastEventId, onExecutionComplete, setIsReconnecting]
  )

  // Handle connection state changes
  const handleStateChange = useCallback(
    (state: 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'failed') => {
      switch (state) {
        case 'connected':
          setConnectionState(true, false)
          onConnectionStateChange?.(true, false)
          break

        case 'reconnecting':
          // Mark as reconnecting to use lastEventId for replay
          setIsReconnecting(true)
          setConnectionState(false, true)
          onConnectionStateChange?.(false, true)
          break

        case 'disconnected':
        case 'failed':
          // Disconnect after final_snapshot should not mark the UI as stale.
          if (isComplete) {
            setConnectionState(false, false)
            onConnectionStateChange?.(false, false)
          } else {
            setConnectionState(false, true)
            onConnectionStateChange?.(false, true)
          }
          break

        case 'connecting':
          // Don't change state during initial connection
          break
      }
    },
    [setConnectionState, onConnectionStateChange, isComplete]
  )

  // Use WebSocket hook
  const {
    connectionState,
    isConnected: wsConnected,
    connect,
    disconnect,
    error,
  } = useWebSocket(channel, {
    onMessage: handleMessage as (message: unknown) => void,
    onStateChange: handleStateChange,
    autoConnect: enabled && !isComplete,
    autoDisconnect: true,
  })

  // Determine stale state
  // Disconnected is NOT stale if execution is complete (intentional disconnect after final_snapshot)
  const isStale =
    connectionState === 'reconnecting' ||
    connectionState === 'failed' ||
    (connectionState === 'disconnected' && !isComplete)

  // Disconnect when execution completes
  useEffect(() => {
    if (isComplete && wsConnected) {
      disconnect()
    }
  }, [isComplete, wsConnected, disconnect])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsConnected) {
        disconnect()
      }
    }
  }, [wsConnected, disconnect])

  return {
    isConnected: wsConnected,
    isStale,
    isComplete,
    error,
    connect,
    disconnect,
  }
}
