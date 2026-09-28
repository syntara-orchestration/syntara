import { EdgeHandleEnum } from '@syntara/contracts'

import { isSwitchCasePort } from '../switchCaseHelpers'

/**
 * Constants and utilities for execution state management.
 *
 * This module centralizes constant values used across the execution state system
 * to prevent duplication, ensure consistency, and avoid typos.
 */

/**
 * Source handles that indicate branching in the workflow.
 *
 * These handles are used on edges to indicate which branch of a conditional,
 * approval, or loop node an edge represents.
 */
export const BRANCH_HANDLES = [
  EdgeHandleEnum.TRUE,
  EdgeHandleEnum.FALSE,
  EdgeHandleEnum.APPROVED,
  EdgeHandleEnum.REJECTED,
  EdgeHandleEnum.DONE,
  EdgeHandleEnum.LOOP,
  EdgeHandleEnum.DEFAULT,
] as const

export type BranchHandle = (typeof BRANCH_HANDLES)[number]

/**
 * Check if a source handle indicates a branch (conditional, approval, loop, or switch).
 *
 * @param handle - The source handle to check
 * @returns true if the handle is a branch handle
 *
 * @example
 * isBranchHandle('true')     // true
 * isBranchHandle('false')    // true
 * isBranchHandle('approved') // true
 * isBranchHandle('done')     // true
 * isBranchHandle('case_0')   // true
 * isBranchHandle('default')  // true
 * isBranchHandle('source')   // false
 * isBranchHandle(null)       // false
 */
export function isBranchHandle(handle: string | null | undefined): boolean {
  if (handle === null || handle === undefined) {
    return false
  }
  if (isSwitchCasePort(handle)) return true
  return BRANCH_HANDLES.includes(handle as BranchHandle)
}

/**
 * Activity type literal values used in workflow structure (v2 schema).
 *
 * These constants represent the different types of activities that can appear
 * in a v2 workflow definition. Using these constants instead of string literals
 * prevents typos and provides better type safety.
 *
 * @example
 * if (activity.type === ACTIVITY_TYPES.CONDITION) {
 *   // Handle condition activity
 * }
 */
export const ACTIVITY_TYPES = {
  TASK: 'task',
  LOOP: 'loop',
  CONDITION: 'condition',
  CONVERGE: 'converge',
  APPROVAL: 'approval',
  SWITCH: 'switch',
} as const

export type ActivityTypeValue = (typeof ACTIVITY_TYPES)[keyof typeof ACTIVITY_TYPES]

/**
 * Activity status values used in execution state management.
 *
 * These constants represent the different states an activity can be in during execution.
 * Using these constants instead of string literals prevents typos and provides better type safety.
 *
 * @example
 * if (activityState.status === ACTIVITY_STATUS.COMPLETED) {
 *   // Handle completed activity
 * }
 */
export const ACTIVITY_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  WAITING: 'waiting',
  COMPLETED: 'completed',
  FAILED: 'failed',
  RETRYING: 'retrying',
  SKIPPED: 'skipped',
  CANCELLED: 'cancelled',
} as const

export type ActivityStatusValue = (typeof ACTIVITY_STATUS)[keyof typeof ACTIVITY_STATUS]

/**
 * Terminal activity statuses that indicate the activity has finished execution.
 *
 * These are states where the activity will not change anymore during the current execution.
 * Used for edge status determination and skip logic.
 */
export const TERMINAL_ACTIVITY_STATUSES: readonly ActivityStatusValue[] = [
  ACTIVITY_STATUS.COMPLETED,
  ACTIVITY_STATUS.FAILED,
  ACTIVITY_STATUS.CANCELLED,
] as const

/**
 * Check if a status is a terminal state (execution completed, no further changes).
 *
 * Terminal states are: completed, failed, or cancelled.
 *
 * @param status - The activity status to check
 * @returns true if the status is terminal
 *
 * @example
 * if (isTerminalState(activity.status)) {
 *   // Activity won't change anymore
 * }
 */
export function isTerminalState(status: string): boolean {
  return TERMINAL_ACTIVITY_STATUSES.includes(status as ActivityStatusValue)
}
