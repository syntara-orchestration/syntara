import { describe, expect, it } from 'vitest'

import { mapFormTriggerValidationFieldPath } from './mapFormTriggerValidationFieldPath'
import { parseFormTriggerFormDefinitionFieldPath } from './parseFormTriggerFormDefinitionFieldPath'
import { partitionFormTriggerServerValidationErrors } from './partitionFormTriggerServerValidationErrors'

describe('parseFormTriggerFormDefinitionFieldPath', () => {
  it('parses dotted field paths', () => {
    expect(parseFormTriggerFormDefinitionFieldPath('parameters.form_definition.fields.0.label', 'Required')).toEqual({
      fieldIndex: 0,
      subPath: 'label',
      message: 'Required',
    })
  })

  it('parses bracket field paths', () => {
    expect(parseFormTriggerFormDefinitionFieldPath('parameters.form_definition.fields[1].options', 'Invalid')).toEqual({
      fieldIndex: 1,
      subPath: 'options',
      message: 'Invalid',
    })
  })

  it('parses whole-field paths', () => {
    expect(parseFormTriggerFormDefinitionFieldPath('parameters.form_definition.fields.2', 'Invalid field')).toEqual({
      fieldIndex: 2,
      subPath: '',
      message: 'Invalid field',
    })
  })

  it('returns null for top-level form_definition', () => {
    expect(parseFormTriggerFormDefinitionFieldPath('parameters.form_definition', 'Bad')).toBeNull()
  })
})

describe('partitionFormTriggerServerValidationErrors', () => {
  it('routes nested form paths to form field errors and top-level paths to trigger fields', () => {
    const result = partitionFormTriggerServerValidationErrors([
      { fieldPath: 'parameters.form_definition.fields.0.label', message: 'Label error' },
      { fieldPath: 'parameters.message', message: 'Message error' },
      { fieldPath: 'parameters.form_definition', message: 'Definition error' },
    ])

    expect(result.formFieldErrors).toEqual([{ fieldIndex: 0, subPath: 'label', message: 'Label error' }])
    expect(result.triggerFieldErrors).toEqual([
      { field: 'message', message: 'Message error' },
      { field: 'form_definition', message: 'Definition error' },
    ])
    expect(mapFormTriggerValidationFieldPath('parameters.form_definition.fields.0.label')).toBe('form_definition')
  })
})
