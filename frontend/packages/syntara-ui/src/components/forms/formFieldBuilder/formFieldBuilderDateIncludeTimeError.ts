import type { FormDefinition } from '@syntara/contracts'
import type { FieldError, FieldErrors } from 'react-hook-form'

/** Subset of {@link FieldErrors} for a date field row (`include_time` server/zod errors). */
export type DateIncludeTimeFieldErrors = Readonly<{
  include_time?: FieldError
}>

function dateFormFieldErrorsAtIndex(
  errors: FieldErrors<FormDefinition>,
  fieldIndex: number
): DateIncludeTimeFieldErrors | undefined {
  const fields = errors.fields
  if (!fields || !Array.isArray(fields)) {
    return undefined
  }
  return fields[fieldIndex] as DateIncludeTimeFieldErrors | undefined
}

/** RHF error message for `fields.{index}.include_time` (server + zod paths on the builder form). */
export function dateFieldIncludeTimeErrorMessage(
  errors: FieldErrors<FormDefinition>,
  fieldIndex: number
): string | undefined {
  const message = dateFormFieldErrorsAtIndex(errors, fieldIndex)?.include_time?.message
  return typeof message === 'string' && message.length > 0 ? message : undefined
}
