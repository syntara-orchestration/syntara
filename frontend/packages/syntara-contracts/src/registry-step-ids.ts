import { ActivityTypeEnum, TriggerTypeEnum } from './interfaces.js'

/** Concrete palette IDs use backend step types; groups and placeholders are frontend-only. */
export const RegistryStepId = {
  TRIGGER: 'trigger',
  TRIGGER_MANUAL: TriggerTypeEnum.MANUAL_TRIGGER,
  TRIGGER_SCHEDULED: TriggerTypeEnum.SCHEDULED,
  TRIGGER_WEBHOOK: TriggerTypeEnum.WEBHOOK_TRIGGER,
  TRIGGER_EDA: TriggerTypeEnum.EDA_TRIGGER,
  ACTION: 'action',
  ACTION_SCRIPT: ActivityTypeEnum.SCRIPT,
  ACTION_API: ActivityTypeEnum.HTTP_REQUEST,
  APPROVAL: ActivityTypeEnum.APPROVAL,
  LOGIC: 'logic',
  LOGIC_CONDITION: ActivityTypeEnum.CONDITION,
  LOGIC_CONVERGE: ActivityTypeEnum.CONVERGE,
  LOGIC_LOOP: ActivityTypeEnum.LOOP,
  LOGIC_SWITCH: ActivityTypeEnum.SWITCH,
  LOGIC_WAIT: ActivityTypeEnum.WAIT,
  AGENT: ActivityTypeEnum.AGENTIC,
  AAP_EXECUTION: 'aap-execution',
  AAP_JOB_TEMPLATE: ActivityTypeEnum.AAP_JOB_TEMPLATE,
  AAP_WORKFLOW_TEMPLATE: ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE,
  GENERIC: 'generic',
} as const

export type RegistryStepIdUnion = (typeof RegistryStepId)[keyof typeof RegistryStepId]
