import { describe, expect, it } from 'vitest'

import { DATE_FIELD_RFC3339_COMBINATION_MESSAGE } from '../../../forms'

import { partitionFormTriggerServerValidationErrors } from './partitionFormTriggerServerValidationErrors'

describe('partitionFormTriggerServerValidationErrors', () => {
  it('maps canvas banner copy to short inline form field messages', () => {
    const { formFieldErrors } = partitionFormTriggerServerValidationErrors([
      {
        fieldPath: 'parameters.form_definition.fields.0.include_date',
        message: `Form "Survey": Due — ${DATE_FIELD_RFC3339_COMBINATION_MESSAGE}`,
      },
    ])

    expect(formFieldErrors).toEqual([
      {
        fieldIndex: 0,
        subPath: 'include_date',
        message: DATE_FIELD_RFC3339_COMBINATION_MESSAGE,
      },
    ])
  })
})
