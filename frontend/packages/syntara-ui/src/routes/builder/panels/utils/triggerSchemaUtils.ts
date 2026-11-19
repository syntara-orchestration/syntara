import type { OutputFieldDef } from '@syntara/contracts'

import { parseTriggerIndex } from '../../../../utils/triggerNodeIds'

import { mapJsonSchemaType } from './jsonSchemaPreviewUtils'

type InputSchemaProperties = Record<string, { type?: string; description?: string }>

export function getTriggerInputSchemaFields(
  nodeId: string,
  triggersList: { id: string; parameters?: Record<string, unknown> }[] | undefined
): OutputFieldDef[] | null {
  let trigger = triggersList?.find((t) => t.id === nodeId)
  if (!trigger) {
    const displayIndex = parseTriggerIndex(nodeId)
    if (displayIndex !== undefined && triggersList?.[displayIndex]) {
      trigger = triggersList[displayIndex]
    }
  }
  if (!trigger) return null
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
