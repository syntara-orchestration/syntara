import type { TriggerFormData } from '../node-forms/triggerFormSchema'

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
  if (relative === 'css_override') return 'css_override'
  if (relative.startsWith('form_definition')) return 'form_definition'
  return null
}
