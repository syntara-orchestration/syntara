import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { ValidationError as BuilderValidationError, ValidationSeverity } from '../../builderReducer'

import { FORM_DEFINITION_CANVAS_VALIDATION_RULES } from './formDefinitionValidationFindings'
import type { ValidationError as UtilsValidationError } from './types'

type LookupNodeNameOptions = Readonly<{
  activityIdFallback?: boolean
}>

/** Canvas rules that overlap backend workflow validate for form definitions. */
const FORM_DEFINITION_FRONTEND_RULES = FORM_DEFINITION_CANVAS_VALIDATION_RULES

/**
 * Backend validate returns the same form-definition issues with field paths.
 * Drop overlapping frontend canvas errors so verify/publish banners are not duplicated.
 */
export function filterFrontendFormDefinitionErrorsCoveredByBackend(
  frontendErrors: UtilsValidationError[],
  backendBannerErrors: ReadonlyArray<BuilderValidationError>
): UtilsValidationError[] {
  const nodesWithBackendFormFindings = new Set(
    backendBannerErrors
      .filter((error) => error.fieldPath?.includes('form_definition') && error.nodeId)
      .map((error) => error.nodeId as string)
  )

  if (nodesWithBackendFormFindings.size === 0) {
    return frontendErrors
  }

  return frontendErrors.filter((error) => {
    if (!error.nodeId || !FORM_DEFINITION_FRONTEND_RULES.has(error.rule)) {
      return true
    }
    return !nodesWithBackendFormFindings.has(error.nodeId)
  })
}

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
    rule: error.rule,
  }))
}

/** Publish/run gating uses error severity only; warnings stay visible on the banner. */
export function countBlockingValidationErrors(errors: ReadonlyArray<BuilderValidationError>): number {
  return errors.filter((error) => error.severity !== 'warning').length
}
