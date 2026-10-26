import { TriggerTypeEnum, type Activity } from '@syntara/contracts'

import { safeParseFormDefinition } from '../../../../../forms'
import type { EdgeConnection } from '../../../types/edge'
import type { ValidationContext, ValidationError } from '../types'

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
    if (trigger.type !== TriggerTypeEnum.FORM_TRIGGER) continue

    const raw = (trigger.parameters as { form_definition?: unknown } | undefined)?.form_definition
    const parsed = safeParseFormDefinition(raw)
    if (parsed.success && parsed.data.fields.length > 0) continue

    const nodeName = trigger.name ?? trigger.id
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
