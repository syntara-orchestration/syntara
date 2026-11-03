import type { ValidationError as BuilderValidationError } from '../../builderReducer'
export const FORM_DEFINITION_CANVAS_VALIDATION_RULES = new Set([
  'form-prompt-form-definition',
  'form-trigger-form-definition',
  'form-trigger-dynamic-options',
  'form-trigger-type-mismatch',
])

function isFormDefinitionValidationFinding(error: Pick<BuilderValidationError, 'fieldPath' | 'rule'>): boolean {
  if (error.fieldPath?.includes('form_definition')) {
    return true
  }
  if (error.rule && FORM_DEFINITION_CANVAS_VALIDATION_RULES.has(error.rule)) {
    return true
  }
  return false
}

export function isFormDefinitionValidationFindingForNode(error: BuilderValidationError, nodeId: string): boolean {
  return error.nodeId === nodeId && isFormDefinitionValidationFinding(error)
}
