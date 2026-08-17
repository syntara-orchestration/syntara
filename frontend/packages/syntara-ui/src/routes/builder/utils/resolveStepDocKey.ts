import { ExecutorTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import type { Node } from '@xyflow/react'

import { FlowNodeType, RegistryNodeId } from '../../../constants'
import { docsUrls } from '../../../utils/docs/loadDocsConfig'
import type { DocKey } from '../../../utils/docs/types'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

const FALLBACK_DOC_KEY: DocKey = 'builder'

/** Registry / executor ids that intentionally have no step documentation link. */
const STEPS_WITHOUT_DOCUMENTATION = new Set<string>([RegistryNodeId.ACTION_SCRIPT, ExecutorTypeEnum.SCRIPT])

/** Registry subtype / leaf ids → step-type documentation keys (must match docsUrls.json / overlay). */
const REGISTRY_SUBTYPE_DOC_KEYS: Readonly<Record<string, string>> = {
  [RegistryNodeId.TRIGGER_MANUAL]: 'manualTrigger',
  [RegistryNodeId.TRIGGER_SCHEDULED]: 'scheduleTrigger',
  [RegistryNodeId.TRIGGER_WEBHOOK]: 'webhookTrigger',
  [RegistryNodeId.TRIGGER_EDA]: 'eventDrivenAnsibleTrigger',
  [RegistryNodeId.ACTION_API]: 'restApi',
  [RegistryNodeId.AGENT]: 'taskAgent',
  [RegistryNodeId.APPROVAL]: 'approval',
  [RegistryNodeId.LOGIC_CONDITION]: 'conditional',
  [RegistryNodeId.LOGIC_CONVERGE]: 'converge',
  [RegistryNodeId.LOGIC_LOOP]: 'loop',
  [RegistryNodeId.LOGIC_SWITCH]: 'switch',
  [RegistryNodeId.LOGIC_WAIT]: 'wait',
  [RegistryNodeId.AAP_JOB_TEMPLATE]: 'launchAapJobTemplate',
  [RegistryNodeId.AAP_WORKFLOW_TEMPLATE]: 'launchAapWorkflowTemplate',
}

const TRIGGER_TYPE_DOC_KEYS: Readonly<Record<string, string>> = {
  [TriggerTypeEnum.MANUAL_TRIGGER]: 'manualTrigger',
  [TriggerTypeEnum.SCHEDULED]: 'scheduleTrigger',
  [TriggerTypeEnum.WEBHOOK_TRIGGER]: 'webhookTrigger',
  [TriggerTypeEnum.EDA_TRIGGER]: 'eventDrivenAnsibleTrigger',
}

const EXECUTOR_TYPE_DOC_KEYS: Readonly<Record<string, string>> = {
  [ExecutorTypeEnum.HTTP_REQUEST]: 'restApi',
  [ExecutorTypeEnum.AGENTIC]: 'taskAgent',
  [ExecutorTypeEnum.AAP_JOB_TEMPLATE]: 'launchAapJobTemplate',
  [ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE]: 'launchAapWorkflowTemplate',
  [ExecutorTypeEnum.APPROVAL]: 'approval',
}

const FLOW_TYPE_DOC_KEYS: Readonly<Record<string, string>> = {
  [FlowNodeType.APPROVAL]: 'approval',
  [FlowNodeType.CONDITION]: 'conditional',
  [FlowNodeType.CONVERGE]: 'converge',
  [FlowNodeType.LOOP]: 'loop',
  [FlowNodeType.SWITCH]: 'switch',
  [FlowNodeType.WAIT]: 'wait',
}

export type ResolveStepDocKeyInput = {
  mode: 'add' | 'edit' | null
  nodeTypeId: string | null
  nodeSubtypeId: string | null
  selectedNode: Node<NodeType['data']> | null
}

function isDocKey(value: string): value is DocKey {
  return Object.hasOwn(docsUrls, value)
}

function toDocKey(value: string): DocKey {
  return isDocKey(value) ? value : FALLBACK_DOC_KEY
}

function lookup(map: Readonly<Record<string, string>>, id: string | null | undefined): DocKey | undefined {
  if (!id) return undefined
  const key = map[id]
  return key === undefined ? undefined : toDocKey(key)
}

function isWithoutDocumentation(...ids: Array<string | null | undefined>): boolean {
  return ids.some((id) => id != null && STEPS_WITHOUT_DOCUMENTATION.has(id))
}

function resolveFromRegistryIds(nodeTypeId: string | null, nodeSubtypeId: string | null): DocKey | undefined {
  return lookup(REGISTRY_SUBTYPE_DOC_KEYS, nodeSubtypeId) ?? lookup(REGISTRY_SUBTYPE_DOC_KEYS, nodeTypeId)
}

function resolveFromSelectedNode(node: Node<NodeType['data']>): DocKey | undefined {
  const flowType = node.type

  if (flowType === FlowNodeType.TRIGGER) {
    const triggerType = (node.data as { triggerType?: string }).triggerType
    return lookup(TRIGGER_TYPE_DOC_KEYS, triggerType) ?? toDocKey('manualTrigger')
  }

  if (flowType === FlowNodeType.TASK || flowType === FlowNodeType.TASK_REVERSED) {
    const executor = (node.data as { type?: string }).type
    return lookup(EXECUTOR_TYPE_DOC_KEYS, executor)
  }

  return lookup(FLOW_TYPE_DOC_KEYS, flowType)
}

/**
 * Maps the open step detail panel context to a documentation key.
 * Returns `null` when the step type has no documentation (e.g. script).
 * Falls back to `builder` when the step type is unknown or only a category is selected.
 */
export function resolveStepDocKey(input: ResolveStepDocKeyInput): DocKey | null {
  const { mode, nodeTypeId, nodeSubtypeId, selectedNode } = input

  if (mode === 'add') {
    if (isWithoutDocumentation(nodeSubtypeId, nodeTypeId)) {
      return null
    }
    return resolveFromRegistryIds(nodeTypeId, nodeSubtypeId) ?? FALLBACK_DOC_KEY
  }

  if (mode === 'edit' && selectedNode) {
    const executor =
      selectedNode.type === FlowNodeType.TASK || selectedNode.type === FlowNodeType.TASK_REVERSED
        ? (selectedNode.data as { type?: string }).type
        : undefined
    if (isWithoutDocumentation(executor)) {
      return null
    }
    return resolveFromSelectedNode(selectedNode) ?? FALLBACK_DOC_KEY
  }

  return FALLBACK_DOC_KEY
}
