import { TriggerTypeEnum, type WorkflowAPI } from '@syntara/contracts'

import { workflowFetchClient } from '../../../client'
import { getErrorMessage } from '../../../utils/apiErrors'

export type KafkaPublishedSource = WorkflowAPI.components['schemas']['KafkaSubscriptionSourceRead']
type Definition = Record<string, unknown>

export function kafkaPublicationQueryKey(workflowId?: string | null) {
  return ['get', '/workflows/{workflow_id}', { workflowId, scope: 'kafka-consumer-settings' }] as const
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export async function readKafkaPublication(workflowId: string) {
  const { data, error } = await workflowFetchClient.GET('/workflows/{workflow_id}', {
    params: { path: { workflow_id: workflowId } },
  })
  if (error) throw new Error(getErrorMessage(error), { cause: error })
  if (!data || !Array.isArray(data.kafka_subscription_sources)) {
    throw new Error('Published consumer group metadata is unavailable. Refresh and try again.')
  }
  return data
}

export function matchingKafkaSource(
  sources: readonly KafkaPublishedSource[],
  triggerId: string,
  integrationId?: string,
  topic?: string
) {
  return sources.find(
    (source) =>
      source.trigger_node_id === triggerId && source.integration_id === integrationId && source.topic === topic
  )
}

export function configuredKafkaGroup(source: KafkaPublishedSource) {
  return source.group_id_is_generated ? null : source.group_id
}

export type KafkaGroupConflict = {
  triggerId: string
  triggerName?: string
  draftGroup: string
  source: KafkaPublishedSource
}

export function reconcileKafkaGroups(definition: Definition, sources: readonly KafkaPublishedSource[]) {
  const conflicts: KafkaGroupConflict[] = []
  let changed = false
  if (!Array.isArray(definition.triggers)) return { definition, conflicts, changed }
  const triggers = definition.triggers.map((trigger: unknown) => {
    if (!isRecord(trigger) || trigger.type !== TriggerTypeEnum.EVENT_SUBSCRIBE || !isRecord(trigger.parameters))
      return trigger
    const parameters = trigger.parameters
    const source = sources.find(
      (item) =>
        item.trigger_node_id === trigger.id &&
        item.integration_id === parameters.integration_id &&
        item.topic === parameters.topic
    )
    if (!source) return trigger
    const configuredGroup = configuredKafkaGroup(source)
    if (parameters.group_id === configuredGroup || (configuredGroup === null && parameters.group_id == null))
      return trigger
    if (
      typeof parameters.group_id === 'string' &&
      parameters.group_id !== '' &&
      parameters.group_id !== source.group_id
    ) {
      const triggerName = typeof trigger.name === 'string' && trigger.name.trim() ? trigger.name : undefined
      conflicts.push({ triggerId: source.trigger_node_id, triggerName, draftGroup: parameters.group_id, source })
    }
    changed = true
    return { ...trigger, parameters: { ...parameters, group_id: configuredGroup } }
  })
  return { definition: changed ? { ...definition, triggers } : definition, conflicts, changed }
}

export function kafkaSourceRevision(sources: readonly KafkaPublishedSource[]) {
  return JSON.stringify(
    sources.map((source) => [
      source.source_id,
      source.generation,
      source.configuration_revision,
      source.group_id,
      source.group_id_is_generated,
    ])
  )
}
