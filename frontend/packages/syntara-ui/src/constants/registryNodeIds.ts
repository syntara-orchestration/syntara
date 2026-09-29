import type { ValueOf } from './types'

/**
 * Node type and subtype identifiers for the builder NodeRegistry (Add step panel).
 * Use these constants instead of string literals when comparing or registering registry ids.
 *
 * @example
 * import { RegistryNodeId } from '@/constants/registryNodeIds'
 *
 * if (nodeTypeId === RegistryNodeId.TRIGGER) { ... }
 * NodeRegistry.register({ id: RegistryNodeId.ACTION, ... })
 */
export const RegistryNodeId = {
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

/** Union of registry node id values */
export type RegistryNodeIdUnion = ValueOf<typeof RegistryNodeId>

/**
 * Set of all AAP (Ansible Automation Platform) node type IDs.
 * Use this to check if a node is any AAP variant instead of manually checking each type.
 *
 * @example
 * if (AAP_NODE_IDS.has(nodeId as RegistryNodeId)) {
 *   // Handle AAP node (custom icon, colors, etc.)
 * }
 */
export const AAP_NODE_IDS = new Set<RegistryNodeIdUnion>([
  RegistryNodeId.AAP_EXECUTION,
  RegistryNodeId.AAP_JOB_TEMPLATE,
  RegistryNodeId.AAP_WORKFLOW_TEMPLATE,
])
