import type { TriggerFormData } from '../step-forms/triggerFormSchema'

const PARAMETER_PREFIX = 'parameters.'

/** Map backend validation `field_path` values to trigger form field names. */
export function mapFormTriggerValidationFieldPath(fieldPath: string | null | undefined): keyof TriggerFormData | null {
  if (!fieldPath?.startsWith(PARAMETER_PREFIX)) {
    return null
  }
  const relative = fieldPath.slice(PARAMETER_PREFIX.length)
  if (relative === 'message') return 'message'
  if (relative === 'submit_label') return 'submit_label'
  if (relative === 'success_message') return 'success_message'
  if (relative.startsWith('form_definition')) return 'form_definition'
  return null
}
