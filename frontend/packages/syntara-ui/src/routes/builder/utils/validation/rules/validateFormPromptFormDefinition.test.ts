import { ActivityTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../../../../../components/forms/formFieldBuilder/createDefaultField'
import { DATE_FIELD_RFC3339_COMBINATION_MESSAGE, FormFieldTypeEnum } from '../../../../../forms'

import { validateFormPromptFormDefinition } from './validateFormPromptFormDefinition'

describe('validateFormPromptFormDefinition', () => {
  it('returns no errors when activities and edges are empty', () => {
    expect(validateFormPromptFormDefinition([], [], undefined)).toEqual([])
  })

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
    expect(errors[0].id).toBe('form-prompt-definition-form-1-0')
    expect(errors[0].message).toContain('Survey')
  })

  it('returns an error for unsupported RFC 3339 date include combinations', () => {
    const activities = [
      {
        id: 'form-1',
        type: ActivityTypeEnum.FORM_PROMPT,
        name: 'Survey',
        parameters: {
          form_definition: {
            fields: [
              {
                type: FormFieldTypeEnum.DATE,
                value_name: 'due',
                label: 'Due',
                include_date: true,
                include_time: true,
                include_timezone: false,
              },
            ],
          },
        },
      },
    ]

    const errors = validateFormPromptFormDefinition(activities, [])
    expect(errors).toHaveLength(1)
    expect(errors[0].rule).toBe('form-prompt-form-definition')
    expect(errors[0].message).toBe(`Form "Survey": Due — ${DATE_FIELD_RFC3339_COMBINATION_MESSAGE}`)
    expect(errors[0].message).not.toContain('Field 1')
    expect(errors[0].fieldPath).toBe('parameters.form_definition.fields[0].include_date')
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
