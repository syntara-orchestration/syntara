import { ActivityTypeEnum, ExecutorTypeEnum, type TaskActivity } from '@syntara/contracts'

import { AAP_NODE_IDS, FlowNodeType, RegistryNodeId } from '../../../constants'

import { detectTaskNodeType, DetectedExecutorType } from './nodes/common/detectTaskNodeType'

/**
 * PatternFly theme tokens for workflow step type indicators on the canvas (UX-aligned).
 * Used for the colored bar and icon on each node. Chosen to match UX spec:
 * Logic F89B78 → orange, Task agent 92C5F9 → blue, Action B6A6E9 → purple,
 * Approval 9AD8D8 → teal, AAP E0E0E0 → gray. Approved/Rejected use success/danger.
 */
export const NODE_TYPE_COLORS = {
  trigger: 'var(--pf-t--global--color--nonstatus--gray--300)',
  logic: 'var(--pf-t--global--color--nonstatus--orangered--200)',
  approval: 'var(--pf-t--global--color--nonstatus--teal--100)',
  actionScript: 'var(--pf-t--global--color--nonstatus--purple--200)',
  actionHttpRequest: 'var(--pf-t--global--color--nonstatus--purple--200)',
  actionAap: 'var(--pf-t--global--color--nonstatus--gray--100)',
  actionAgentic: 'var(--pf-t--global--color--nonstatus--blue--200)',
  actionDefault: 'var(--pf-t--global--color--nonstatus--purple--200)',
  generic: 'var(--pf-t--global--color--nonstatus--gray--300)',
} as const

export type NodeTypeColorKey = keyof typeof NODE_TYPE_COLORS

/**
 * Returns the color token for the colored bar at the top of a workflow step.
 * In v2, node type IS the executor (e.g. 'script', 'http_request', 'agentic', 'aap_job_template', 'approval').
 */
export function getNodeTypeColor(nodeType: string, data?: { type?: string }): string {
  if (nodeType === FlowNodeType.TRIGGER) {
    return NODE_TYPE_COLORS.trigger
  }
  if (nodeType === ActivityTypeEnum.APPROVAL) {
    return NODE_TYPE_COLORS.approval
  }
  if (
    nodeType === ActivityTypeEnum.CONDITION ||
    nodeType === ActivityTypeEnum.LOOP ||
    nodeType === ActivityTypeEnum.CONVERGE ||
    nodeType === ActivityTypeEnum.SWITCH ||
    nodeType === ActivityTypeEnum.WAIT
  ) {
    return NODE_TYPE_COLORS.logic
  }
  if (nodeType === FlowNodeType.GENERIC) {
    return NODE_TYPE_COLORS.generic
  }
  if (nodeType === FlowNodeType.TASK || nodeType === FlowNodeType.TASK_REVERSED) {
    return getTaskNodeColor(data as TaskActivity | undefined)
  }
  return NODE_TYPE_COLORS.actionDefault
}

function getTaskNodeColor(data: TaskActivity | undefined): string {
  if (!data?.type) {
    return NODE_TYPE_COLORS.actionDefault
  }
  const { actualExecutor } = detectTaskNodeType(data)
  if (actualExecutor === ExecutorTypeEnum.SCRIPT) {
    return NODE_TYPE_COLORS.actionScript
  }
  if (actualExecutor === ExecutorTypeEnum.HTTP_REQUEST) {
    return NODE_TYPE_COLORS.actionHttpRequest
  }
  if (
    actualExecutor === ExecutorTypeEnum.AAP_JOB_TEMPLATE ||
    actualExecutor === ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE ||
    actualExecutor === DetectedExecutorType.AAP
  ) {
    return NODE_TYPE_COLORS.actionAap
  }
  if (actualExecutor === ExecutorTypeEnum.AGENTIC) {
    return NODE_TYPE_COLORS.actionAgentic
  }
  return NODE_TYPE_COLORS.actionDefault
}

const ADD_PANEL_TRIGGER_IDS: ReadonlySet<string> = new Set([
  RegistryNodeId.TRIGGER,
  RegistryNodeId.TRIGGER_MANUAL,
  RegistryNodeId.TRIGGER_SCHEDULED,
  RegistryNodeId.TRIGGER_WEBHOOK,
  RegistryNodeId.TRIGGER_EDA,
])

const ADD_PANEL_LOGIC_IDS: ReadonlySet<string> = new Set([
  RegistryNodeId.LOGIC,
  RegistryNodeId.LOGIC_CONDITION,
  RegistryNodeId.LOGIC_CONVERGE,
  RegistryNodeId.LOGIC_LOOP,
  RegistryNodeId.LOGIC_SWITCH,
  RegistryNodeId.LOGIC_WAIT,
])

const ADD_PANEL_ACTION_IDS: ReadonlySet<string> = new Set([
  RegistryNodeId.ACTION,
  RegistryNodeId.ACTION_SCRIPT,
  RegistryNodeId.ACTION_API,
])

/**
 * Returns the accent color for a card in the Add step panel (registry node type or subtype id).
 * Trigger has no accent; AAP uses gray; other types match canvas node colors.
 */
export function getAddNodePanelColor(registryNodeId: string): string | undefined {
  if (!registryNodeId) return undefined
  if (ADD_PANEL_TRIGGER_IDS.has(registryNodeId)) return undefined
  if (ADD_PANEL_LOGIC_IDS.has(registryNodeId)) return NODE_TYPE_COLORS.logic
  if (registryNodeId === RegistryNodeId.APPROVAL) return NODE_TYPE_COLORS.approval
  if (ADD_PANEL_ACTION_IDS.has(registryNodeId)) return NODE_TYPE_COLORS.actionScript
  if (registryNodeId === RegistryNodeId.AGENT) return NODE_TYPE_COLORS.actionAgentic
  // AAP category and all AAP subtypes use the same color
  if (AAP_NODE_IDS.has(registryNodeId as (typeof RegistryNodeId)[keyof typeof RegistryNodeId])) {
    return NODE_TYPE_COLORS.actionAap
  }
  return undefined
}
