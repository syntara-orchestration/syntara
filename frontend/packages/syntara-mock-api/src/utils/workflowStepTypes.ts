export function getWorkflowStepTypes(definitions: unknown[]): string[] {
  const stepTypes = new Set<string>()
  for (const definition of definitions) {
    if (!definition || typeof definition !== 'object') continue
    for (const collection of ['nodes', 'triggers']) {
      const items = Reflect.get(definition, collection)
      if (!Array.isArray(items)) continue
      for (const item of items) {
        if (item && typeof item === 'object' && 'type' in item && typeof item.type === 'string') {
          stepTypes.add(item.type)
        }
      }
    }
  }
  return [...stepTypes].sort()
}
