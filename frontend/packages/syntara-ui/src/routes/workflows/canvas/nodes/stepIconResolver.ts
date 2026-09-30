import { ExecutorTypeEnum, TriggerTypeEnum, type TaskActivity } from '@syntara/contracts'
import type { Node } from '@xyflow/react'
import type { ComponentType } from 'react'

import { type RegistryStepIdUnion, RegistryStepId } from '../../../../constants'
import { parseTriggerIndex } from '../../../../utils/triggerNodeIds'

import { detectTaskExecutorType, DetectedExecutorType } from './common/detectTaskExecutorType'
import type { NodeType } from './NodeType'
import { executorMetadata, stepMetadata } from './stepMetadata'

export type IconDescriptor = {
  icon?: ComponentType<{ className?: string }>
  id?: string
}

export function getTaskIconDescriptor(taskData: TaskActivity): IconDescriptor {
  const { detectedExecutorType, actualExecutor } = detectTaskExecutorType(taskData)
  // In v2, activity.type IS the executor — use it directly for metadata lookup
  const executorMeta = executorMetadata[actualExecutor] ?? executorMetadata[taskData.type ?? '']
  let iconId: RegistryStepIdUnion = RegistryStepId.ACTION_SCRIPT

  if (
    detectedExecutorType === DetectedExecutorType.AAP ||
    actualExecutor === ExecutorTypeEnum.AAP_JOB_TEMPLATE ||
    actualExecutor === ExecutorTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE
  ) {
    iconId = RegistryStepId.AAP_EXECUTION
  } else if (actualExecutor === ExecutorTypeEnum.APPROVAL) {
    iconId = RegistryStepId.APPROVAL
  } else if (actualExecutor === ExecutorTypeEnum.AGENTIC) {
    iconId = RegistryStepId.AGENT
  } else if (actualExecutor === ExecutorTypeEnum.HTTP_REQUEST) {
    iconId = RegistryStepId.ACTION_API
  }
  return { icon: executorMeta?.icon, id: iconId }
}

export function getCanvasStepIconDescriptor(
  node: Pick<Node<NodeType['data']>, 'id' | 'type' | 'data'>,
  currentWorkflow?: { triggers?: Array<{ type?: string }> } | null
): IconDescriptor {
  if (node.type === 'trigger') {
    const triggerIndex = parseTriggerIndex(node.id) ?? 0
    const triggerType =
      currentWorkflow?.triggers?.[triggerIndex]?.type ?? (node.data as { triggerType?: string }).triggerType
    if (triggerType === TriggerTypeEnum.SCHEDULED) {
      return { icon: stepMetadata.scheduledTrigger.icon, id: RegistryStepId.TRIGGER_SCHEDULED }
    }
    if (triggerType === TriggerTypeEnum.WEBHOOK_TRIGGER) {
      return { icon: stepMetadata.webhookTrigger.icon, id: RegistryStepId.TRIGGER_WEBHOOK }
    }
    if (triggerType === TriggerTypeEnum.EDA_TRIGGER) {
      return { icon: stepMetadata.edaTrigger.icon, id: RegistryStepId.TRIGGER_EDA }
    }
    return { icon: stepMetadata.trigger.icon, id: RegistryStepId.TRIGGER_MANUAL }
  }

  if (node.type === 'condition') {
    return { icon: stepMetadata.condition.icon, id: RegistryStepId.LOGIC_CONDITION }
  }

  if (node.type === 'loop') {
    return { icon: stepMetadata.loop.icon, id: RegistryStepId.LOGIC_LOOP }
  }

  if (node.type === 'converge') {
    return { icon: stepMetadata.converge.icon, id: RegistryStepId.LOGIC_CONVERGE }
  }

  if (node.type === 'switch') {
    return { icon: stepMetadata.switch.icon, id: RegistryStepId.LOGIC_SWITCH }
  }

  if (node.type === 'approval') {
    return { icon: executorMetadata.approval.icon, id: RegistryStepId.APPROVAL }
  }

  if (node.type === 'wait') {
    return { icon: stepMetadata.wait.icon, id: RegistryStepId.LOGIC_WAIT }
  }

  if (node.type === 'task') {
    const taskData = node.data as TaskActivity
    return getTaskIconDescriptor(taskData)
  }

  return { icon: undefined, id: undefined }
}
