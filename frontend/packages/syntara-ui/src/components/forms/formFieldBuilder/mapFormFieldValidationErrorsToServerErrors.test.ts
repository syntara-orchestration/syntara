import { describe, expect, it } from 'vitest'

import { DATE_FIELD_RFC3339_COMBINATION_MESSAGE, FormFieldTypeEnum } from '../../../forms'
import { safeParseFormDefinition } from '../../../forms/formDefinitionSchema'

import { mapFormFieldValidationErrorsToServerErrors } from './mapFormFieldValidationErrorsToServerErrors'

describe('mapFormFieldValidationErrorsToServerErrors', () => {
  it('maps date and timezone without time to include_date server errors', () => {
    const parsed = safeParseFormDefinition({
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
    })

    expect(parsed.success).toBe(false)
    if (parsed.success) {
      return
    }

    expect(mapFormFieldValidationErrorsToServerErrors(parsed.errors)).toEqual([
      {
        fieldIndex: 0,
        subPath: 'include_date',
        message: DATE_FIELD_RFC3339_COMBINATION_MESSAGE,
      },
    ])
  })

  it('maps include_date zod findings for unsupported RFC 3339 combinations', () => {
    const parsed = safeParseFormDefinition({
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
    })

    expect(parsed.success).toBe(false)
    if (parsed.success) {
      return
    }

    expect(mapFormFieldValidationErrorsToServerErrors(parsed.errors)).toEqual([
      {
        fieldIndex: 0,
        subPath: 'include_date',
        message: DATE_FIELD_RFC3339_COMBINATION_MESSAGE,
      },
    ])
  })
})
