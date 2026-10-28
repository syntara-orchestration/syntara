import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { FormFieldTypeEnum } from '../../../forms'
import { DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE } from '../../../forms/dateFieldValidationMessages'

import { formPromptFormSchema, formPromptStoredParametersSchema } from './formPromptNodeFormSchema'

describe('formPromptFormSchema', () => {
  it('accepts a minimal valid form prompt payload', () => {
    const result = formPromptFormSchema.safeParse({
      name: 'Survey',
      form_definition: createEmptyFormDefinition(),
    })
    expect(result.success).toBe(true)
  })

  it('rejects too many responder groups', () => {
    const groups = Array.from({ length: 51 }, (_, i) => `group-${i}`)
    const result = formPromptFormSchema.safeParse({
      name: 'Survey',
      form_definition: createEmptyFormDefinition(),
      responder_groups: groups,
    })
    expect(result.success).toBe(false)
  })

  it('rejects too many responder users', () => {
    const users = Array.from({ length: 101 }, (_, i) => `user-${i}`)
    const result = formPromptFormSchema.safeParse({
      name: 'Survey',
      form_definition: createEmptyFormDefinition(),
      responder_users: users,
    })
    expect(result.success).toBe(false)
  })

  it('rejects date and timezone without time in form_definition', () => {
    const result = formPromptFormSchema.safeParse({
      name: 'Survey',
      form_definition: {
        fields: [
          {
            type: FormFieldTypeEnum.DATE,
            value_name: 'due',
            label: 'Due',
            include_date: true,
            include_time: false,
            include_timezone: true,
          },
        ],
      },
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(
        result.error.issues.some((issue) => issue.message === DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE)
      ).toBe(true)
    }
  })

  it('parses stored parameters with fallback_behavior', () => {
    const result = formPromptStoredParametersSchema.safeParse({
      fallback_behavior: 'fail',
      fallback_decision: 'submit',
    })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.fallback_behavior).toBe('fail')
    }
  })
})
