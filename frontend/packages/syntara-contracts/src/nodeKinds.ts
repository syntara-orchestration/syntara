import { ActivityTypeEnum, TriggerTypeEnum } from './interfaces.js'

/**
 * Backend `NodeType` values — the step types usable as `kind` labels on
 * `workflow_node` policy statements.
 *
 * Mirrors the backend node-kind registry (`syntara.workflows.node_kinds`).
 * `internal_activity` has no builder palette entry — it is created only
 * programmatically — so it never appears in `NODE_KIND_BY_REGISTRY_ID`.
 */
export type NodeKind =
  | 'manual_trigger'
  | 'scheduled_trigger'
  | 'webhook_trigger'
  | 'eda_trigger'
  | 'condition'
  | 'converge'
  | 'loop'
  | 'switch'
  | 'wait'
  | 'aap_job_template'
  | 'aap_workflow_job_template'
  | 'agentic'
  | 'approval'
  | 'http_request'
  | 'internal_activity'
  | 'script'

/**
 * Builder registry node id (palette entry) → backend node kind
 * (a `NodeType` value).
 *
 * Keys are string literals matching the UI's `RegistryNodeId` values — this
 * package cannot import UI constants, so key validity is enforced by the
 * co-located unit test against `RegistryNodeId`.
 *
 * Container ids (`trigger`, `action`, `logic`, `aap-execution`) only open a
 * subtype list and the programmatic-only `generic` entry has no backend node
 * kind, so none of them appear here.
 */
export const NODE_KIND_BY_REGISTRY_ID: Readonly<Record<string, NodeKind>> = {
  'trigger-manual': TriggerTypeEnum.MANUAL_TRIGGER,
  'trigger-scheduled': TriggerTypeEnum.SCHEDULED,
  'trigger-webhook': TriggerTypeEnum.WEBHOOK_TRIGGER,
  'trigger-eda': TriggerTypeEnum.EDA_TRIGGER,
  'action-script': ActivityTypeEnum.SCRIPT,
  'action-api': ActivityTypeEnum.HTTP_REQUEST,
  approval: ActivityTypeEnum.APPROVAL,
  agent: ActivityTypeEnum.AGENTIC,
  'logic-condition': ActivityTypeEnum.CONDITION,
  'logic-converge': ActivityTypeEnum.CONVERGE,
  'logic-loop': ActivityTypeEnum.LOOP,
  'logic-switch': ActivityTypeEnum.SWITCH,
  'logic-wait': ActivityTypeEnum.WAIT,
  'aap-job-template': ActivityTypeEnum.AAP_JOB_TEMPLATE,
  'aap-workflow-template': ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE,
}
