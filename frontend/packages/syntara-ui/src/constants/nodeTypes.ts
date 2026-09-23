import type { ValueOf } from './types'

/**
 * React Flow node type identifiers.
 * These match the keys in nodeTypes registry.
 *
 * @example
 * import { FlowNodeType } from '@/constants/nodeTypes'
 *
 * if (node.type === FlowNodeType.TRIGGER) {
 *   // Handle trigger step (React Flow node)
 * }
 */
export const FlowNodeType = {
  TRIGGER: 'trigger',
  TASK: 'task',
  /** Loop-back path: same data as task, handles reversed for layout */
  TASK_REVERSED: 'task-reversed',
  APPROVAL: 'approval',
  CONDITION: 'condition',
  CONVERGE: 'converge',
  LOOP: 'loop',
  SWITCH: 'switch',
  WAIT: 'wait',
  /** Placeholder until user picks a real step type */
  GENERIC: 'generic',
  PLACEHOLDER: 'placeholder',
} as const

/** Union of FlowNodeType values */
export type FlowNodeTypeUnion = ValueOf<typeof FlowNodeType>

/**
 * Node type categories for menu actions and workflow operations.
 * Groups FlowNodeTypes into categories for menu handling.
 *
 * @example
 * import { MenuNodeType } from '@/constants/nodeTypes'
 *
 * if (nodeType === MenuNodeType.ACTIVITY) {
 *   // Handle activity steps (Task, Condition, Converge, Loop, Parallel)
 * }
 */
export const MenuNodeType = {
  /** Activity steps: Task, Approval, and other executor nodes */
  ACTIVITY: 'activity',
  /** Control flow nodes: Condition, Loop, Converge, Switch, Wait */
  CONTROL_FLOW: 'control-flow',
  /** Trigger nodes: Manual, Scheduled, Webhook, etc. */
  TRIGGER: 'trigger',
} as const

/** Union of MenuNodeType values ('activity' | 'trigger') */
export type MenuNodeTypeUnion = ValueOf<typeof MenuNodeType>
