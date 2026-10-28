import { TriggerTypeEnum, type Activity } from '@syntara/contracts'

import { safeParseFormDefinition } from '../../../../../forms'
import type { EdgeConnection } from '../../../types/edge'
import type { ValidationContext, ValidationError } from '../types'

const FORM_TRIGGER_PARAMETER_KEYS = [
  'form_definition',
  'message',
  'submit_label',
  'success_message',
  'css_override',
] as const

function hasFormTriggerParameterKeys(parameters: Record<string, unknown> | undefined): boolean {
  if (!parameters) return false
  return FORM_TRIGGER_PARAMETER_KEYS.some((key) => key in parameters)
}

export function validateFormTriggerFormDefinition(
  activities: Activity[],
  edges: EdgeConnection[],
  context?: ValidationContext
): ValidationError[] {
  if (activities.length === 0 && edges.length === 0 && context === undefined) {
    return []
  }

  const triggers = context?.triggers ?? []
  const errors: ValidationError[] = []

  for (const trigger of triggers) {
    const nodeName = trigger.name ?? trigger.id
    const parameters = trigger.parameters as Record<string, unknown> | undefined

    if (trigger.type === TriggerTypeEnum.MANUAL_TRIGGER && hasFormTriggerParameterKeys(parameters)) {
      errors.push({
        id: `form-trigger-type-mismatch-${trigger.id}`,
        severity: 'error',
        rule: 'form-trigger-type-mismatch',
        message:
          `Trigger "${nodeName}" uses form trigger settings but its type is manual_trigger. ` +
          'Remove the trigger and add a Form trigger from the palette, or clear the form fields and use a manual trigger.',
        nodeId: trigger.id,
      })
      continue
    }

    if (trigger.type !== TriggerTypeEnum.FORM_TRIGGER) continue

    const raw = (trigger.parameters as { form_definition?: unknown } | undefined)?.form_definition
    const parsed = safeParseFormDefinition(raw)
    if (parsed.success && parsed.data.fields.length > 0) continue

    let detail: string
    if (parsed.success) {
      detail = 'Add at least one form field'
    } else {
      detail = parsed.errors[0]?.message ?? 'Form definition is invalid'
    }
    errors.push({
      id: `form-trigger-definition-${trigger.id}`,
      severity: 'error',
      rule: 'form-trigger-form-definition',
      message: `Form trigger "${nodeName}" has an invalid form definition: ${detail}`,
      nodeId: trigger.id,
    })
  }

  return errors
}
