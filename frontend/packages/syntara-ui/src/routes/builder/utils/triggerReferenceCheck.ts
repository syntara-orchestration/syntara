function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export function hasNonEmptyInputSchema(schema?: unknown): boolean {
  if (!isRecord(schema)) return false
  const properties = schema.properties
  if (isRecord(properties)) {
    return Object.keys(properties).length > 0
  }
  const required = schema.required
  if (Array.isArray(required) && required.length > 0) return true
  return false
}

const VARIABLE_REF_PATTERN = /\$\{([^}]+)\}/g

function collectStringValues(obj: unknown, acc: string[] = []): string[] {
  if (typeof obj === 'string') {
    acc.push(obj)
  } else if (Array.isArray(obj)) {
    for (const item of obj) collectStringValues(item, acc)
  } else if (obj !== null && typeof obj === 'object') {
    for (const val of Object.values(obj)) collectStringValues(val, acc)
  }
  return acc
}

export function activitiesReferenceTrigger(
  activities: { parameters?: Record<string, unknown> }[],
  triggerNodeIds: string[]
): boolean {
  const triggerNamespaces = new Set(['trigger', ...triggerNodeIds])
  for (const activity of activities) {
    if (!activity.parameters) continue
    const strings = collectStringValues(activity.parameters)
    for (const str of strings) {
      for (const match of str.matchAll(VARIABLE_REF_PATTERN)) {
        const namespace = match[1].trim().split('.')[0]
        if (triggerNamespaces.has(namespace)) return true
      }
    }
  }
  return false
}
