import { getNodeOutputSchema, type OutputFieldDef } from '@syntara/contracts'

export type OutputSourceOption = {
  expression: string
  fieldName: string
  stepName: string
  type: OutputFieldDef['type']
  sourceDescription: string
  allowsDynamicDescendants: boolean
}

type Activity = {
  id: string
  name?: string | null
  type: string
  output_schema?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isOutputType(value: unknown): value is OutputFieldDef['type'] {
  return (
    value === 'string' ||
    value === 'number' ||
    value === 'boolean' ||
    value === 'object' ||
    value === 'array' ||
    value === 'unknown'
  )
}

function isOutputFieldDef(value: unknown): value is OutputFieldDef {
  if (!isRecord(value)) return false
  return (
    typeof value['name'] === 'string' &&
    isOutputType(value['type']) &&
    typeof value['description'] === 'string' &&
    (value['children'] === undefined || (Array.isArray(value['children']) && value['children'].every(isOutputFieldDef)))
  )
}

function flattenOutputFields(
  stepId: string,
  stepName: string,
  fields: OutputFieldDef[],
  prefix: string[] = []
): OutputSourceOption[] {
  return fields.flatMap((field) => {
    const path = [...prefix, field.name]
    const fieldName = path.join('.')
    const option: OutputSourceOption = {
      expression: '${' + stepId + '.' + fieldName + '}',
      fieldName,
      stepName,
      type: field.type,
      sourceDescription: field.description,
      allowsDynamicDescendants: field.type === 'unknown' || field.additionalProperties !== undefined,
    }
    return [option, ...(field.children ? flattenOutputFields(stepId, stepName, field.children, path) : [])]
  })
}

export function isDynamicOutputExpression(expression: string, sourceOptions: OutputSourceOption[]): boolean {
  const match = /^\$\{([^{}]+)\}$/.exec(expression.trim())
  if (!match) return false
  const segments = match[1]?.split('.') ?? []
  if (segments.length < 3) return false

  for (let prefixLength = 2; prefixLength < segments.length; prefixLength += 1) {
    const prefix = '${' + segments.slice(0, prefixLength).join('.') + '}'
    if (sourceOptions.some((option) => option.expression === prefix && option.allowsDynamicDescendants)) return true
  }

  return false
}

function outputFieldsForActivity(activity: Activity): OutputFieldDef[] {
  const declaredFields = Array.isArray(activity.output_schema) ? activity.output_schema.filter(isOutputFieldDef) : []
  return declaredFields.length > 0 ? declaredFields : (getNodeOutputSchema(activity.type) ?? [])
}

export function getStepOutputChoices(
  activities: Activity[],
  edges: Array<{ source: string; target: string }>,
  triggerId: string,
  triggerIndex: number
): OutputSourceOption[] {
  const reachable = new Set([triggerId, `trigger-${triggerIndex}`])
  let previousSize = -1
  while (reachable.size !== previousSize) {
    previousSize = reachable.size
    for (const edge of edges) {
      if (reachable.has(edge.source)) reachable.add(edge.target)
    }
  }

  return activities.flatMap((activity) => {
    if (!reachable.has(activity.id)) return []
    const stepName = activity.name || activity.id
    return flattenOutputFields(activity.id, stepName, outputFieldsForActivity(activity))
  })
}
