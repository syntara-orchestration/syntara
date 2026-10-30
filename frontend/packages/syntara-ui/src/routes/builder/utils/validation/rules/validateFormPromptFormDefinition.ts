import { ActivityTypeEnum, type Activity } from '@syntara/contracts'

import { humanizeFormDefinitionValidationError, safeParseFormDefinition } from '../../../../../forms'
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
    for (const [index, finding] of parsed.errors.entries()) {
      errors.push({
        id: `form-prompt-definition-${activity.id}-${index}`,
        severity: 'error',
        rule: 'form-prompt-form-definition',
        message: `Form "${nodeName}": ${humanizeFormDefinitionValidationError(finding)}`,
        nodeId: activity.id,
      })
    }
  }

  return errors
}
