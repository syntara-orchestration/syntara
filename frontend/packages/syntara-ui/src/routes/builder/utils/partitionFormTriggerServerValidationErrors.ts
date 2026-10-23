import type { FormDefinitionFieldServerError } from '../../../components/forms/formFieldBuilder/formDefinitionFieldServerError'
import type { TriggerFormData } from '../node-forms/triggerFormSchema'

import { mapFormTriggerValidationFieldPath } from './mapFormTriggerValidationFieldPath'
import { parseFormTriggerFormDefinitionFieldPath } from './parseFormTriggerFormDefinitionFieldPath'

export type FormTriggerServerValidationError = Readonly<{
  fieldPath?: string | null
  message: string
}>

export function partitionFormTriggerServerValidationErrors(errors?: ReadonlyArray<FormTriggerServerValidationError>): {
  triggerFieldErrors: Array<{ field: keyof TriggerFormData; message: string }>
  formFieldErrors: FormDefinitionFieldServerError[]
} {
  const triggerFieldErrors: Array<{ field: keyof TriggerFormData; message: string }> = []
  const formFieldErrors: FormDefinitionFieldServerError[] = []

  for (const err of errors ?? []) {
    const formField = parseFormTriggerFormDefinitionFieldPath(err.fieldPath, err.message)
    if (formField) {
      formFieldErrors.push(formField)
      continue
    }
    const field = mapFormTriggerValidationFieldPath(err.fieldPath)
    if (field) {
      triggerFieldErrors.push({ field, message: err.message })
    }
  }

  return { triggerFieldErrors, formFieldErrors }
}
