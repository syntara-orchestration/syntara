import { ActivityTypeEnum, type Activity } from '@syntara/contracts'

import { generateUUID } from '../../../../../utils/generateUUID'
import type { EdgeConnection } from '../../../types/edge'
import { resolveFormPromptFallbackBehavior } from '../../formPromptFallbackBehavior'
import { formPromptHasFallbackEdge } from '../../formPromptSettingsNormalization'
import type { ValidationContext, ValidationError } from '../types'

export function validateFormPromptFallbackBehavior(
  activities: Activity[],
  edges: EdgeConnection[],
  context?: ValidationContext
): ValidationError[] {
  const systemContinueOnFailure = context?.systemContinueOnFailure ?? false
  const errors: ValidationError[] = []

  for (const activity of activities) {
    if (activity.type !== ActivityTypeEnum.FORM_PROMPT) continue
    if (!formPromptHasFallbackEdge(activity.id, edges)) continue

    const parameters = { ...(activity.parameters ?? {}) }
    const settings: Record<string, unknown> | undefined = activity.settings ? { ...activity.settings } : undefined
    const behavior = resolveFormPromptFallbackBehavior(parameters, settings, systemContinueOnFailure)
    if (behavior === 'fallback') continue

    const nodeName = activity.name ?? activity.id
    errors.push({
      id: `form-prompt-fallback-behavior-${activity.id}-${generateUUID()}`,
      severity: 'error',
      rule: 'form-prompt-fallback-behavior',
      message:
        `Form "${nodeName}" has a 'Fallback' branch connected, but On timeout is set to fail the workflow. ` +
        'The fallback branch will never execute. Remove the fallback connection or change On timeout to ' +
        "'Route to fallback'.",
      nodeId: activity.id,
    })
  }

  return errors
}
