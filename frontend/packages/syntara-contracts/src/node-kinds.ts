import { ActivityTypeEnum, TriggerTypeEnum } from './interfaces.js'

/** Builder palette identifiers, including containers and the internal placeholder. */
export const RegistryStepId = {
  TRIGGER: 'trigger',
  TRIGGER_MANUAL: 'trigger-manual',
  TRIGGER_SCHEDULED: 'trigger-scheduled',
  TRIGGER_WEBHOOK: 'trigger-webhook',
  TRIGGER_EDA: 'trigger-eda',
  ACTION: 'action',
  ACTION_SCRIPT: 'action-script',
  ACTION_API: 'action-api',
  APPROVAL: 'approval',
  LOGIC: 'logic',
  LOGIC_CONDITION: 'logic-condition',
  LOGIC_CONVERGE: 'logic-converge',
  LOGIC_LOOP: 'logic-loop',
  LOGIC_SWITCH: 'logic-switch',
  LOGIC_WAIT: 'logic-wait',
  AGENT: 'agent',
  AAP_EXECUTION: 'aap-execution',
  AAP_JOB_TEMPLATE: 'aap-job-template',
  AAP_WORKFLOW_TEMPLATE: 'aap-workflow-template',
  GENERIC: 'generic',
} as const

export type RegistryStepIdUnion = (typeof RegistryStepId)[keyof typeof RegistryStepId]

/** Concrete palette entry to backend NodeType value (the policy's kind label). */
export const NODE_KIND_BY_REGISTRY_ID = {
  [RegistryStepId.TRIGGER_MANUAL]: TriggerTypeEnum.MANUAL_TRIGGER,
  [RegistryStepId.TRIGGER_SCHEDULED]: TriggerTypeEnum.SCHEDULED,
  [RegistryStepId.TRIGGER_WEBHOOK]: TriggerTypeEnum.WEBHOOK_TRIGGER,
  [RegistryStepId.TRIGGER_EDA]: TriggerTypeEnum.EDA_TRIGGER,
  [RegistryStepId.ACTION_SCRIPT]: ActivityTypeEnum.SCRIPT,
  [RegistryStepId.ACTION_API]: ActivityTypeEnum.HTTP_REQUEST,
  [RegistryStepId.APPROVAL]: ActivityTypeEnum.APPROVAL,
  [RegistryStepId.AGENT]: ActivityTypeEnum.AGENTIC,
  [RegistryStepId.LOGIC_CONDITION]: ActivityTypeEnum.CONDITION,
  [RegistryStepId.LOGIC_CONVERGE]: ActivityTypeEnum.CONVERGE,
  [RegistryStepId.LOGIC_LOOP]: ActivityTypeEnum.LOOP,
  [RegistryStepId.LOGIC_SWITCH]: ActivityTypeEnum.SWITCH,
  [RegistryStepId.LOGIC_WAIT]: ActivityTypeEnum.WAIT,
  [RegistryStepId.AAP_JOB_TEMPLATE]: ActivityTypeEnum.AAP_JOB_TEMPLATE,
  [RegistryStepId.AAP_WORKFLOW_TEMPLATE]: ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE,
} as const
