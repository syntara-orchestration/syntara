import { TriggerTypeEnum, type OutputFieldDef } from '@syntara/contracts'

import { parseTriggerIndex } from '../../../../utils/triggerNodeIds'

type InputSchemaProperties = Record<string, { type?: string; description?: string }>

const JSON_SCHEMA_TYPE_MAP: Record<string, OutputFieldDef['type']> = {
  string: 'string',
  number: 'number',
  integer: 'number',
  boolean: 'boolean',
  object: 'object',
  array: 'array',
}

function mapJsonSchemaType(type?: string): OutputFieldDef['type'] {
  return type ? (JSON_SCHEMA_TYPE_MAP[type] ?? 'unknown') : 'unknown'
}

export function getTriggerInputSchemaFields(
  nodeId: string,
  triggersList: { id: string; type?: string; parameters?: Record<string, unknown> }[] | undefined
): OutputFieldDef[] | null {
  let trigger = triggersList?.find((t) => t.id === nodeId)
  if (!trigger) {
    const displayIndex = parseTriggerIndex(nodeId)
    if (displayIndex !== undefined && triggersList?.[displayIndex]) {
      trigger = triggersList[displayIndex]
    }
  }
  if (!trigger) return null
  if (trigger.type === TriggerTypeEnum.EVENT_SUBSCRIBE) {
    return [
      { name: 'envelope_version', type: 'number', description: 'Event envelope version' },
      {
        name: 'payload',
        type: 'unknown',
        description: 'Kafka message payload; the optional input schema validates this value',
      },
      { name: 'original', type: 'object', description: 'Original message bytes and headers in JSON-safe form' },
      { name: 'metadata', type: 'object', description: 'Kafka source metadata' },
    ]
  }
  const inputSchema = trigger.parameters?.input_schema as Record<string, unknown> | undefined
  if (!inputSchema || typeof inputSchema !== 'object') return null
  const properties = inputSchema.properties as InputSchemaProperties | undefined
  if (!properties || Object.keys(properties).length === 0) return null
  return Object.entries(properties).map(([name, prop]) => ({
    name,
    type: mapJsonSchemaType(prop.type),
    description: prop.description ?? `Input parameter: ${name}`,
  }))
}
