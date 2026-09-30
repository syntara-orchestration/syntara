import { ActivityTypeEnum, ExecutorTypeEnum, type TaskActivity } from '@syntara/contracts'

import { AAP_STEP_IDS, FlowNodeType, RegistryStepId } from '../../../constants'

import { detectTaskExecutorType, DetectedExecutorType } from './nodes/common/detectTaskExecutorType'

/**
 * PatternFly theme tokens for workflow step type indicators on the canvas (UX-aligned).
 * Used for the colored bar and icon on each step. Chosen to match UX spec:
 * Logic F89B78 → orange, Task agent 92C5F9 → blue, Action B6A6E9 → purple,
 * Approval 9AD8D8 → teal, AAP E0E0E0 → gray. Approved/Rejected use success/danger.
 */
export const STEP_TYPE_COLORS = {
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

export type StepTypeColorKey = keyof typeof STEP_TYPE_COLORS

/**
 * Returns the color token for the colored bar at the top of a workflow step.
 * In v2, task step type maps to its executor (e.g. 'script', 'http_request', 'agentic', 'aap_job_template', 'approval').
 */
export function getStepTypeColor(nodeType: string, data?: { type?: string }): string {
  if (nodeType === FlowNodeType.TRIGGER) {
    return STEP_TYPE_COLORS.trigger
  }
  if (nodeType === ActivityTypeEnum.APPROVAL) {
    return STEP_TYPE_COLORS.approval
  }
  if (
    nodeType === ActivityTypeEnum.CONDITION ||
    nodeType === ActivityTypeEnum.LOOP ||
    nodeType === ActivityTypeEnum.CONVERGE ||
    nodeType === ActivityTypeEnum.SWITCH ||
    nodeType === ActivityTypeEnum.WAIT
  ) {
    return STEP_TYPE_COLORS.logic
  }
  if (nodeType === FlowNodeType.GENERIC) {
    return STEP_TYPE_COLORS.generic
  }
  if (nodeType === FlowNodeType.TASK || nodeType === FlowNodeType.TASK_REVERSED) {
    return getTaskStepColor(data as TaskActivity | undefined)
  }
  return STEP_TYPE_COLORS.actionDefault
}

function getTaskStepColor(data: TaskActivity | undefined): string {
  if (!data?.type) {
    return STEP_TYPE_COLORS.actionDefault
  }
  const { actualExecutor } = detectTaskExecutorType(data)
  if (actualExecutor === ExecutorTypeEnum.SCRIPT) {
    return STEP_TYPE_COLORS.actionScript
  }
  if (actualExecutor === ExecutorTypeEnum.HTTP_REQUEST) {
    return STEP_TYPE_COLORS.actionHttpRequest
  }
  if (
    actualExecutor === ExecutorTypeEnum.AAP_JOB_TEMPLATE ||
    actualExecutor === ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE ||
    actualExecutor === DetectedExecutorType.AAP
  ) {
    return STEP_TYPE_COLORS.actionAap
  }
  if (actualExecutor === ExecutorTypeEnum.AGENTIC) {
    return STEP_TYPE_COLORS.actionAgentic
  }
  return STEP_TYPE_COLORS.actionDefault
}

const ADD_PANEL_TRIGGER_IDS: ReadonlySet<string> = new Set([
  RegistryStepId.TRIGGER,
  RegistryStepId.TRIGGER_MANUAL,
  RegistryStepId.TRIGGER_SCHEDULED,
  RegistryStepId.TRIGGER_WEBHOOK,
  RegistryStepId.TRIGGER_EDA,
])

const ADD_PANEL_LOGIC_IDS: ReadonlySet<string> = new Set([
  RegistryStepId.LOGIC,
  RegistryStepId.LOGIC_CONDITION,
  RegistryStepId.LOGIC_CONVERGE,
  RegistryStepId.LOGIC_LOOP,
  RegistryStepId.LOGIC_SWITCH,
  RegistryStepId.LOGIC_WAIT,
])

const ADD_PANEL_ACTION_IDS: ReadonlySet<string> = new Set([
  RegistryStepId.ACTION,
  RegistryStepId.ACTION_SCRIPT,
  RegistryStepId.ACTION_API,
])

/**
 * Returns the accent color for a card in the Add step panel (registry step type or subtype id).
 * Trigger has no accent; AAP uses gray; other types match canvas node colors.
 */
export function getAddStepPanelColor(registryStepId: string): string | undefined {
  if (!registryStepId) return undefined
  if (ADD_PANEL_TRIGGER_IDS.has(registryStepId)) return undefined
  if (ADD_PANEL_LOGIC_IDS.has(registryStepId)) return STEP_TYPE_COLORS.logic
  if (registryStepId === RegistryStepId.APPROVAL) return STEP_TYPE_COLORS.approval
  if (ADD_PANEL_ACTION_IDS.has(registryStepId)) return STEP_TYPE_COLORS.actionScript
  if (registryStepId === RegistryStepId.AGENT) return STEP_TYPE_COLORS.actionAgentic
  // AAP category and all AAP subtypes use the same color
  if (AAP_STEP_IDS.has(registryStepId as (typeof RegistryStepId)[keyof typeof RegistryStepId])) {
    return STEP_TYPE_COLORS.actionAap
  }
  return undefined
}
