/**
 * Execution Visualization Types
 *
 * TypeScript type definitions for execution visualization including nodes,
 * edges, and WebSocket messages for real-time activity streaming.
 */

import type { ExecutionsAPI } from '@syntara/contracts'

// ============================================================================
// API Type Imports
// ============================================================================

/** Execution schema from REST API */
export type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']

/** Activity data from REST API */
export type ActivityData = ExecutionsAPI.components['schemas']['ActivityExecution']

/** Activity status from API */
export type ActivityStatus = ExecutionsAPI.components['schemas']['ActivityStatus']

/** Execution status from API */
export type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']

// ============================================================================
// UI Status Types
// ============================================================================

/**
 * Edge status derived from source activity status
 */
export type EdgeStatus = 'pending' | 'passed'

// ============================================================================
// JSON Patch Types
// ============================================================================

/**
 * JSON Patch operation per RFC 6902
 * Supports add, replace, and remove operations for activity updates
 */
export type JsonPatchOperation = {
  /** Operation type */
  op: 'add' | 'replace' | 'remove' | 'move' | 'copy' | 'test'
  /** JSON Pointer path (e.g., "/activities/0/status") */
  path: string
  /** Value for add/replace/test operations */
  value?: unknown
  /** Source path for move/copy operations */
  from?: string
}

// ============================================================================
// WebSocket Message Types
// ============================================================================

/**
 * Base message fields common to all WebSocket messages
 */
type BaseWebSocketMessage = {
  /** Valkey stream ID for replay support (format: {milliseconds}-{sequence}) */
  event_id: string
  /** Workflow execution ID */
  execution_id: string
  /** Timestamp when message was generated */
  timestamp: string
}

/**
 * Execution snapshot message
 * Sent as first message (type="initial_snapshot") on replay from beginning,
 * and as last message (type="final_snapshot") when execution completes.
 */
export type ExecutionSnapshotMessage = {
  type: 'initial_snapshot' | 'final_snapshot'
  /**
   * Execution object with same structure as REST API
   * GET /executions/{id}?include=activities
   */
  execution: Execution
} & BaseWebSocketMessage

/**
 * Activity patch message
 * Activity status change using JSON Patch format for incremental updates
 */
export type ActivityPatchMessage = {
  type: 'activity_patch'
  /** One or more JSON Patch operations */
  ops: JsonPatchOperation[]
} & BaseWebSocketMessage

/**
 * Execution patch message
 * Execution-level field updates (e.g. status) using JSON Patch format
 */
export type ExecutionPatchMessage = {
  type: 'execution_patch'
  /** One or more JSON Patch operations */
  ops: JsonPatchOperation[]
} & BaseWebSocketMessage

/**
 * Union of all possible WebSocket message types
 */
export type WebSocketMessage = ExecutionSnapshotMessage | ActivityPatchMessage | ExecutionPatchMessage

// ============================================================================
// Visualization State Types
// ============================================================================

/**
 * Activity state for visualization
 */
export type ActivityState = {
  /** Activity ID from workflow definition */
  activityId: string
  /** Current status */
  status: ActivityStatus
  /** Error message if status is 'failed' */
  errorDetails?: string | null
  /** Activity output data (API response body, status code, etc.) */
  outputData?: Record<string, unknown> | null
  /** When activity started execution */
  startedAt?: string | null
  /** When activity reached terminal state */
  completedAt?: string | null
  /** Loop iteration number (0-indexed), null for non-loop activities */
  iteration?: number | null
}

/**
 * Execution visualization data structure
 * Contains the workflow definition and execution metadata needed for visualization
 */
export type ExecutionVisualization = {
  /** Execution ID */
  executionId: string
  /** Workflow ID */
  workflowId: string
  /** Overall execution status */
  status: ExecutionStatus
  /** Whether this execution has pending approval requests */
  approval_pending?: boolean
  /** Workflow definition for building graph */
  workflowDefinition: unknown // TODO: Type from workflow-definition.schema
  /** Activity states keyed by activity_id */
  activities: Map<string, ActivityState>
  /** When execution was created */
  createdAt: string
  /** When execution started */
  startedAt?: string | null
  /** When execution completed */
  completedAt?: string | null
  /** Set when this execution was created by retrying another one. */
  retriedFromExecutionId?: string | null
}

// ============================================================================
// Store State Types
// ============================================================================

/**
 * Connection state for WebSocket
 */
export type ConnectionState = {
  /** Whether WebSocket is currently connected */
  isConnected: boolean
  /**
   * Whether connection is stale (disconnected but attempting to reconnect)
   * UI should show warning indicator when true
   */
  isStale: boolean
}

/**
 * Execution store state
 * Manages all state for execution visualization
 */
export type ExecutionStoreState = {
  /** Current execution ID being visualized */
  executionId: string | null
  /** Execution visualization data */
  visualization: ExecutionVisualization | null
  /** Activity states keyed by activity_id (for fast lookup) */
  activityStates: Map<string, ActivityStatus>
  /** Activity errors keyed by activity_id */
  activityErrors: Map<string, string>
  /** WebSocket connection state */
  isConnected: boolean
  /** Whether connection is stale (disconnected but reconnecting) */
  isStale: boolean
  /** Whether execution is complete (final_snapshot received) */
  isComplete: boolean
  /** Last event ID received (for replay on reconnection) */
  lastEventId: string | null
  /** Error state */
  error: Error | null
}
