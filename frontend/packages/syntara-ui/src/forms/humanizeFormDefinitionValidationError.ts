import { humanizeFormDefinitionIssueMessage } from './formDefinitionValidationMessage'
import type { FormFieldValidationError } from './formValidationErrors'

/** Turn zod/form-definition validation errors into builder-friendly copy. */
export function humanizeFormDefinitionValidationError(error: FormFieldValidationError): string {
  return humanizeFormDefinitionIssueMessage(error.message, error.field)
}

export function humanizeFormDefinitionValidationErrors(errors: ReadonlyArray<FormFieldValidationError>): string[] {
  return errors.map((error) => humanizeFormDefinitionValidationError(error))
}
