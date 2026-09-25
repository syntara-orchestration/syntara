import { ActivityTypeEnum, type Activity } from '@syntara/contracts'

import { safeParseFormDefinition } from '../../../../../forms'
import type { EdgeConnection } from '../../../types/edge'
import type { ValidationContext, ValidationError } from '../types'

export function validateFormPromptFormDefinition(
  activities: Activity[],
  edges: EdgeConnection[],
  context?: ValidationContext
): ValidationError[] {
  if (activities.length === 0 && edges.length === 0 && context === undefined) {
    return []
  }
  const errors: ValidationError[] = []

  for (const activity of activities) {
    if (activity.type !== ActivityTypeEnum.FORM_PROMPT) continue

    const raw = (activity.parameters as { form_definition?: unknown } | undefined)?.form_definition
    const parsed = safeParseFormDefinition(raw)
    if (parsed.success) continue

    const nodeName = activity.name ?? activity.id
    const detail = parsed.errors[0]?.message ?? 'Form definition is invalid'
    errors.push({
      id: `form-prompt-definition-${activity.id}`,
      severity: 'error',
      rule: 'form-prompt-form-definition',
      message: `Form "${nodeName}" has an invalid form definition: ${detail}`,
      nodeId: activity.id,
    })
  }

  return errors
}
