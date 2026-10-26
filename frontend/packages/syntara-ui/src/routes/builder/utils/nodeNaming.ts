import { RegistryNodeId } from '../../../constants'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { generateUUID } from '../../../utils/generateUUID'

function getExistingNodeNames(): string[] {
  const workflow = useWorkflowStore.getState().currentWorkflow
  const activities = workflow?.workflow?.activities ?? []
  const triggers = workflow?.triggers ?? []

  const activityNames = activities
    .map((activity) => activity.name)
    .filter((name): name is string => Boolean(name?.trim()))

  const triggerNames = triggers
    .map((trigger) => (trigger as { name?: string }).name)
    .filter((name): name is string => Boolean(name?.trim()))

  return [...activityNames, ...triggerNames]
}

function generateRandomSuffix(): string {
  return generateUUID().replace(/-/g, '').slice(0, 8)
}

export function makeUniqueName(baseName: string, existingNames: string[]): string {
  const normalizedBaseName = baseName.trim()
  if (!normalizedBaseName) {
    return `Node-${generateRandomSuffix()}`
  }

  const existingSet = new Set(existingNames)
  if (!existingSet.has(normalizedBaseName)) {
    return normalizedBaseName
  }

  let suffix = 2
  let candidate = `${normalizedBaseName}${suffix}`
  while (existingSet.has(candidate)) {
    suffix += 1
    candidate = `${normalizedBaseName}${suffix}`
  }

  return candidate
}

export function getNodeDisplayName(baseName: string, requestedName?: string): string {
  const trimmedRequestedName = requestedName?.trim()
  const existingNames = getExistingNodeNames()

  if (trimmedRequestedName) {
    return makeUniqueName(trimmedRequestedName, existingNames)
  }

  return makeUniqueName(baseName, existingNames)
}

export function getNodeDisplayNameForEdit(
  baseName: string,
  requestedName: string | undefined,
  currentName: string | undefined
): string {
  const trimmedRequestedName = requestedName?.trim()
  const trimmedCurrentName = currentName?.trim()
  const existingNames = trimmedCurrentName
    ? getExistingNodeNames().filter((name) => name !== trimmedCurrentName)
    : getExistingNodeNames()

  if (trimmedRequestedName) {
    return makeUniqueName(trimmedRequestedName, existingNames)
  }

  return makeUniqueName(baseName, existingNames)
}

export function getDefaultNodeBaseName({
  nodeTypeId,
  nodeSubtypeId,
  initialData,
  label,
}: {
  nodeTypeId: string
  nodeSubtypeId?: string | null
  initialData?: Record<string, unknown>
  label?: string
}): string {
  if (nodeTypeId === RegistryNodeId.TRIGGER) return 'Trigger'

  if (nodeTypeId === RegistryNodeId.LOGIC) {
    const logicType = initialData?.logicType as string | undefined
    const logicLabels: Record<string, string> = { condition: 'Condition', loop: 'Loop', switch: 'Switch', wait: 'Wait' }
    return (logicType && logicLabels[logicType]) ?? 'Converge'
  }

  if (nodeTypeId === RegistryNodeId.ACTION) {
    const executor = initialData?.executor as string | undefined
    if (executor === 'http_request') return 'REST API'
    if (executor === 'script') return 'Script'
  }

  if (nodeSubtypeId) {
    return label ?? nodeSubtypeId
  }

  return label ?? nodeTypeId
}
