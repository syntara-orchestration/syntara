import { describe, expect, it } from 'vitest'

import { DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE, FormFieldTypeEnum } from '../../../forms'
import { safeParseFormDefinition } from '../../../forms/formDefinitionSchema'

import { mapFormFieldValidationErrorsToServerErrors } from './mapFormFieldValidationErrorsToServerErrors'

describe('mapFormFieldValidationErrorsToServerErrors', () => {
  it('maps include_time zod findings to builder server errors', () => {
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
        subPath: 'include_time',
        message: DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE,
      },
    ])
  })
})
