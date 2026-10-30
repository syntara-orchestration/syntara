import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { ValidationError as BuilderValidationError, ValidationSeverity } from '../../builderReducer'

import type { ValidationError as UtilsValidationError } from './types'

type LookupNodeNameOptions = Readonly<{
  activityIdFallback?: boolean
}>

export function lookupValidationNodeName(
  nodeId: string | null | undefined,
  options?: LookupNodeNameOptions
): string | undefined {
  if (!nodeId) return undefined
  const currentWorkflow = useWorkflowStore.getState().currentWorkflow
  const activity = currentWorkflow?.workflow?.activities?.find((item) => item.id === nodeId)
  if (activity) {
    return activity.name ?? (options?.activityIdFallback ? nodeId : undefined)
  }
  const trigger = currentWorkflow?.triggers?.find((item) => item.id === nodeId)
  if (trigger) {
    return trigger.name ?? nodeId
  }
  return undefined
}

function utilsSeverityToBannerSeverity(severity: UtilsValidationError['severity'] | undefined): ValidationSeverity {
  return severity === 'warning' ? 'warning' : 'error'
}

/** Maps canvas `validateWorkflow` / `validateMinimumWorkflow` errors to builder banner shape. */
export function mapUtilsValidationErrorsToBanner(
  errors: UtilsValidationError[],
  options?: LookupNodeNameOptions
): BuilderValidationError[] {
  return errors.map((error) => ({
    message: error.message,
    nodeId: error.nodeId ?? null,
    nodeName: lookupValidationNodeName(error.nodeId, options),
    severity: utilsSeverityToBannerSeverity(error.severity),
  }))
}

/** Publish/run gating uses error severity only; warnings stay visible on the banner. */
export function countBlockingValidationErrors(errors: ReadonlyArray<BuilderValidationError>): number {
  return errors.filter((error) => error.severity !== 'warning').length
}
