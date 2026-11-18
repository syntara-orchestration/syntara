import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { ValidationError } from '../../builderReducer'

import { FORM_DEFINITION_CANVAS_VALIDATION_RULES } from './formDefinitionValidationFindings'
import { mapUtilsValidationErrorsToBanner } from './mapFrontendValidationErrorsToBanner'
import { validateWorkflow } from './validateWorkflow'

type CollectStoredWorkflowCanvasValidationOptions = Readonly<{
  systemContinueOnFailure?: boolean
}>

/** Canvas-level findings for the workflow currently in the builder store (matches verify/run rules). */
function collectStoredWorkflowCanvasValidationFindings(
  options?: CollectStoredWorkflowCanvasValidationOptions
): ValidationError[] {
  const { edges, currentWorkflow } = useWorkflowStore.getState()
  const activities = currentWorkflow?.workflow.activities ?? []
  const triggers = currentWorkflow?.triggers ?? []

  const result = validateWorkflow(activities, edges, {
    triggers,
    systemContinueOnFailure: options?.systemContinueOnFailure ?? false,
  })

  return mapUtilsValidationErrorsToBanner(result.errors, { activityIdFallback: true })
}

/**
 * Form-definition rules for when the save API accepts the draft but canvas validation still
 * fails (stale worker, mock API, etc.). Mirrors verify/run copy.
 */
export function collectStoredWorkflowFormDefinitionCanvasFindings(
  options?: CollectStoredWorkflowCanvasValidationOptions
): ValidationError[] {
  return collectStoredWorkflowCanvasValidationFindings(options).filter(
    (finding) => finding.rule != null && FORM_DEFINITION_CANVAS_VALIDATION_RULES.has(finding.rule)
  )
}
