import { ActivityTypeEnum } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import { createEmptyFormDefinition } from '../../../../../components/forms/formFieldBuilder/createDefaultField'

import { validateFormPromptFormDefinition } from './validateFormPromptFormDefinition'

vi.mock('../../../../../utils/generateUUID', () => ({
  generateUUID: () => 'uuid',
}))

describe('validateFormPromptFormDefinition', () => {
  it('returns no errors for a valid form definition', () => {
    const activities = [
      {
        id: 'form-1',
        type: ActivityTypeEnum.FORM_PROMPT,
        name: 'Survey',
        parameters: { form_definition: createEmptyFormDefinition() },
      },
    ]

    expect(validateFormPromptFormDefinition(activities, [])).toEqual([])
  })

  it('returns an error when form_definition is invalid', () => {
    const activities = [
      {
        id: 'form-1',
        type: ActivityTypeEnum.FORM_PROMPT,
        name: 'Survey',
        parameters: { form_definition: { fields: [] } },
      },
    ]

    const errors = validateFormPromptFormDefinition(activities, [])
    expect(errors).toHaveLength(1)
    expect(errors[0].rule).toBe('form-prompt-form-definition')
    expect(errors[0].nodeId).toBe('form-1')
    expect(errors[0].message).toContain('Survey')
  })

  it('ignores non form_prompt activities', () => {
    const activities = [
      {
        id: 'script-1',
        type: ActivityTypeEnum.SCRIPT,
        parameters: { form_definition: { fields: [] } },
      },
    ]

    expect(validateFormPromptFormDefinition(activities, [])).toEqual([])
  })
})
