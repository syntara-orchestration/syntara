import { TriggerTypeEnum, type WorkflowAPI } from '@syntara/contracts'
import { v4 as uuidv4 } from 'uuid'

type Source = WorkflowAPI.components['schemas']['KafkaSubscriptionSourceRead']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function projectKafkaSources(workflowId: string, definition: unknown, previous: readonly Source[]) {
  const sources: Source[] = []
  if (!isRecord(definition) || !Array.isArray(definition.triggers)) return sources
  let generation = Math.max(0, ...previous.map((source) => source.generation))
  for (const trigger of definition.triggers) {
    if (!isRecord(trigger) || trigger.type !== TriggerTypeEnum.EVENT_SUBSCRIBE || !isRecord(trigger.parameters))
      continue
    const { integration_id: integrationId, topic, group_id: groupId } = trigger.parameters
    if (typeof trigger.id !== 'string' || typeof integrationId !== 'string' || typeof topic !== 'string') continue
    const existing = previous.find(
      (source) =>
        source.trigger_node_id === trigger.id && source.integration_id === integrationId && source.topic === topic
    )
    if (existing) {
      if (groupId != null && groupId !== existing.group_id) {
        throw new Error('Event Subscribe group_id is fixed after the first successful publication')
      }
      sources.push({ ...existing, configuration_revision: existing.configuration_revision + 1 })
    } else {
      generation++
      sources.push({
        trigger_node_id: trigger.id,
        source_id: uuidv4(),
        generation,
        configuration_revision: 1,
        integration_id: integrationId,
        topic,
        group_id_is_generated: !(typeof groupId === 'string' && groupId),
        group_id: typeof groupId === 'string' && groupId ? groupId : `syntara.mock.${workflowId}.${uuidv4()}`,
      })
    }
  }
  return sources
}
