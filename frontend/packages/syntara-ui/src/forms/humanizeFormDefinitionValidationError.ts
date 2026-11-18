import { formFieldLabelFromDefinition, humanizeFormDefinitionIssueMessage } from './formDefinitionValidationMessage'
import type { FormFieldValidationError } from './formValidationErrors'

export type HumanizeFormDefinitionValidationErrorOptions = Readonly<{
  /** Draft form definition used to resolve field labels instead of numeric row fallbacks. */
  formDefinition?: unknown
}>

/** Turn zod/form-definition validation errors into builder-friendly copy. */
export function humanizeFormDefinitionValidationError(
  error: FormFieldValidationError,
  options?: HumanizeFormDefinitionValidationErrorOptions
): string {
  const fieldLabel = formFieldLabelFromDefinition(options?.formDefinition, error.field)
  return humanizeFormDefinitionIssueMessage(error.message, error.field, { fieldLabel })
}

export function humanizeFormDefinitionValidationErrors(
  errors: ReadonlyArray<FormFieldValidationError>,
  options?: HumanizeFormDefinitionValidationErrorOptions
): string[] {
  return errors.map((error) => humanizeFormDefinitionValidationError(error, options))
}
