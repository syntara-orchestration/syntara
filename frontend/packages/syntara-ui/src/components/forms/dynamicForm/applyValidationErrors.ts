import type { UseFormSetError } from 'react-hook-form'

import type { FormFieldValidationError, FormSubmissionInput } from '../../../forms'

export function applyValidationErrors(
  setError: UseFormSetError<FormSubmissionInput>,
  errors: readonly FormFieldValidationError[]
): void {
  for (const err of errors) {
    setError(err.field, { type: err.code, message: err.message })
  }
}
