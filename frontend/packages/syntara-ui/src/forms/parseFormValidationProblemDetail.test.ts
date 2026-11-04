import { describe, expect, it } from 'vitest'

import { parseFormDefinition } from './formDefinitionSchema'
import { isFormValidationProblemDetail, parseFormValidationProblemDetail } from './parseFormValidationProblemDetail'

describe('parseFormValidationProblemDetail', () => {
  const definition = parseFormDefinition({
    fields: [{ type: 'text', value_name: 'required_text', label: 'Required text', required: true }],
  })

  it('returns empty array when detail does not match the form validation prefix', () => {
    expect(parseFormValidationProblemDetail('Something else')).toEqual([])
  })

  it('parses a single field error', () => {
    const errors = parseFormValidationProblemDetail(
      'Form validation failed: required_text: This field is required',
      definition
    )
    expect(errors).toEqual([
      {
        field: 'required_text',
        label: 'Required text',
        code: 'required',
        message: 'This field is required',
      },
    ])
  })

  it('parses multiple errors in order', () => {
    const detail =
      'Form validation failed: required_text: This field is required; count: Must be a valid number string; unknown: Unknown field'
    const errors = parseFormValidationProblemDetail(detail, definition)
    expect(errors.map((e) => e.field)).toEqual(['required_text', 'count', 'unknown'])
    expect(errors[2]?.code).toBe('unknown_field')
  })

  it('isFormValidationProblemDetail detects the prefix', () => {
    expect(isFormValidationProblemDetail('Form validation failed: a: b')).toBe(true)
    expect(isFormValidationProblemDetail('Validation failed')).toBe(false)
  })
})
