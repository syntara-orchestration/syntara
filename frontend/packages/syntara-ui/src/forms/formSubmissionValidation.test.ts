import { describe, expect, it } from 'vitest'

import { parseFormDefinition } from './formDefinitionSchema'
import { FormFieldTypeEnum, type FormFieldType } from './formFieldTypeEnum'
import {
  assertValidFormDefinition,
  validateFormDefinitionDefaults,
  validateFormSubmission,
} from './formSubmissionValidation'
import { FormDataValidationError, FormDefinitionValidationError } from './formValidationErrors'

const staticOptions = {
  source: 'static' as const,
  values: [
    { display_label: 'A', value: 'a' },
    { display_label: 'B', value: 'b' },
  ],
}

function field(type: FormFieldType, value_name: string, overrides: Record<string, unknown> = {}) {
  return { type, value_name, label: value_name, ...overrides }
}

function form(...fields: ReturnType<typeof field>[]) {
  return parseFormDefinition({ fields })
}

function expectValidationErrors(
  definition: ReturnType<typeof form>,
  submitted: Record<string, unknown>,
  expected: Array<[string, string]>
) {
  try {
    validateFormSubmission(definition, submitted)
    throw new Error('Expected FormDataValidationError')
  } catch (error) {
    expect(error).toBeInstanceOf(FormDataValidationError)
    const validationError = error as FormDataValidationError
    expect(validationError.errors.map((e) => [e.field, e.code] as [string, string])).toEqual(
      expect.arrayContaining(expected)
    )
    expect(validationError.errors).toHaveLength(expected.length)
  }
}

describe('validateFormSubmission', () => {
  it('returns cleaned values for a valid submission', () => {
    const definition = form(
      field(FormFieldTypeEnum.TEXT, 'name'),
      field(FormFieldTypeEnum.NUMBER, 'age'),
      field(FormFieldTypeEnum.CHECKBOX, 'subscribe'),
      field(FormFieldTypeEnum.DATE, 'start')
    )

    const cleaned = validateFormSubmission(definition, {
      name: 'bob',
      age: 30,
      subscribe: true,
      start: '2026-01-05',
    })

    expect(cleaned).toEqual({
      name: 'bob',
      age: 30,
      subscribe: true,
      start: '2026-01-05',
    })
  })

  it('omits absent optional fields rather than setting null', () => {
    const cleaned = validateFormSubmission(form(field(FormFieldTypeEnum.TEXT, 'name')), {})
    expect(cleaned).toEqual({})
  })

  it.each(['', [], null] as const)('treats empty values as absent for non-checkbox fields', (empty) => {
    const cleaned = validateFormSubmission(form(field(FormFieldTypeEnum.TEXT, 'name')), { name: empty })
    expect(cleaned).toEqual({})
  })

  it('applies defaults when a field is absent', () => {
    const cleaned = validateFormSubmission(form(field(FormFieldTypeEnum.TEXT, 'name', { default: 'anon' })), {})
    expect(cleaned).toEqual({ name: 'anon' })
  })

  it('reports required, type, and unknown_field errors together', () => {
    const definition = form(
      field(FormFieldTypeEnum.TEXT, 'name', { required: true }),
      field(FormFieldTypeEnum.NUMBER, 'age', { required: true })
    )

    expectValidationErrors(definition, { age: 'not-a-number', extra: 1 }, [
      ['name', 'required'],
      ['age', 'type'],
      ['extra', 'unknown_field'],
    ])
  })

  it('requires a checked checkbox when required is true', () => {
    expectValidationErrors(form(field(FormFieldTypeEnum.CHECKBOX, 'agree', { required: true })), { agree: false }, [
      ['agree', 'must_be_checked'],
    ])
  })

  it('normalizes email domain to lowercase', () => {
    const cleaned = validateFormSubmission(form(field(FormFieldTypeEnum.EMAIL, 'contact')), {
      contact: 'Bob@Example.COM',
    })
    expect(cleaned).toEqual({ contact: 'Bob@example.com' })
  })

  it('validates static dropdown membership', () => {
    const definition = form(
      field(FormFieldTypeEnum.DROPDOWN, 'choice', {
        options: staticOptions,
      })
    )

    expect(validateFormSubmission(definition, { choice: 'a' })).toEqual({ choice: 'a' })
    expectValidationErrors(definition, { choice: 'z' }, [['choice', 'not_in_options']])
  })

  it('does not mutate the submitted object', () => {
    const submitted = { name: 'bob' }
    validateFormSubmission(
      form(field(FormFieldTypeEnum.TEXT, 'name'), field(FormFieldTypeEnum.TEXT, 'other', { default: 'd' })),
      submitted
    )
    expect(submitted).toEqual({ name: 'bob' })
  })

  it('wraps a single scalar into a one-element multi-select list', () => {
    const definition = form(
      field(FormFieldTypeEnum.MULTI_SELECT, 'tags', {
        options: staticOptions,
      })
    )

    const cleaned = validateFormSubmission(definition, { tags: 'a' })
    expect(cleaned).toEqual({ tags: ['a'] })
  })

  it('coerces textarea, masked text, and numeric string inputs', () => {
    const definition = form(
      field(FormFieldTypeEnum.TEXTAREA, 'notes'),
      field(FormFieldTypeEnum.MASKED_TEXT, 'secret'),
      field(FormFieldTypeEnum.NUMBER, 'count')
    )

    expect(
      validateFormSubmission(definition, {
        notes: 'hello',
        secret: '***',
        count: '42',
      })
    ).toEqual({ notes: 'hello', secret: '***', count: 42 })
  })

  it('reports invalid_format when email fails pattern validation', () => {
    expectValidationErrors(form(field(FormFieldTypeEnum.EMAIL, 'contact')), { contact: 'a@b' }, [
      ['contact', 'invalid_format'],
    ])
  })

  it('reports type errors for invalid number, checkbox, and date values', () => {
    const definition = form(
      field(FormFieldTypeEnum.NUMBER, 'n'),
      field(FormFieldTypeEnum.CHECKBOX, 'c'),
      field(FormFieldTypeEnum.DATE, 'd')
    )

    expectValidationErrors(definition, { n: true, c: 'maybe', d: '2026-02-30' }, [
      ['n', 'type'],
      ['c', 'type'],
      ['d', 'type'],
    ])
  })

  it('rejects non-ISO date strings', () => {
    expectValidationErrors(form(field(FormFieldTypeEnum.DATE, 'start')), { start: '01/02/2026' }, [['start', 'type']])
  })

  it('rejects non-finite numbers and non-boolean checkbox payloads', () => {
    const definition = form(field(FormFieldTypeEnum.NUMBER, 'n'), field(FormFieldTypeEnum.CHECKBOX, 'c'))

    expectValidationErrors(definition, { n: Number.NaN, c: null }, [
      ['n', 'type'],
      ['c', 'type'],
    ])
    expectValidationErrors(form(field(FormFieldTypeEnum.NUMBER, 'count')), { count: {} }, [['count', 'type']])
  })

  it('reports type errors for non-string text fields and invalid numbers', () => {
    const definition = form(
      field(FormFieldTypeEnum.TEXT, 'name'),
      field(FormFieldTypeEnum.NUMBER, 'n'),
      field(FormFieldTypeEnum.DATE, 'd')
    )

    expectValidationErrors(definition, { name: 1, n: 'not-a-number', d: 20260101 }, [
      ['name', 'type'],
      ['n', 'type'],
      ['d', 'type'],
    ])
  })

  it('reports type errors when multi-select lists contain invalid elements', () => {
    const definition = form(field(FormFieldTypeEnum.MULTI_SELECT, 'tags', { options: staticOptions }))
    expectValidationErrors(definition, { tags: ['a', {}] }, [['tags', 'type']])
  })

  it('accepts checkbox string and numeric encodings', () => {
    const definition = form(field(FormFieldTypeEnum.CHECKBOX, 'c'))
    expect(validateFormSubmission(definition, { c: 'yes' })).toEqual({ c: true })
    expect(validateFormSubmission(definition, { c: 'off' })).toEqual({ c: false })
    expect(validateFormSubmission(definition, { c: 1 })).toEqual({ c: true })
  })

  it('rejects dropdown arrays and object payloads', () => {
    const definition = form(field(FormFieldTypeEnum.DROPDOWN, 'choice', { options: staticOptions }))
    expectValidationErrors(definition, { choice: ['a'] }, [['choice', 'type']])
    expectValidationErrors(definition, { choice: { value: 'a' } }, [['choice', 'type']])
  })

  it('rejects multi-select dict payloads and invalid option members', () => {
    const definition = form(field(FormFieldTypeEnum.MULTI_SELECT, 'tags', { options: staticOptions }))
    expectValidationErrors(definition, { tags: { value: 'a' } }, [['tags', 'type']])
    expectValidationErrors(definition, { tags: ['a', 'z'] }, [['tags', 'not_in_options']])
  })

  it('rejects invalid static dropdown scalar types before membership checks', () => {
    const definition = form(field(FormFieldTypeEnum.DROPDOWN, 'choice', { options: staticOptions }))
    expectValidationErrors(definition, { choice: { toString: () => 'a' } }, [['choice', 'type']])
  })

  it('allows dynamic-option fields without static membership validation', () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'env',
          label: 'Env',
          options: { source: 'dynamic', expression: 'options' },
        },
      ],
    })

    expect(validateFormSubmission(definition, { env: 'anything' })).toEqual({ env: 'anything' })
  })
})

describe('validateFormDefinitionDefaults', () => {
  it('throws when a default value fails coercion', () => {
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.EMAIL, value_name: 'contact', label: 'Contact', default: 'not-an-email' }],
    })

    expect(() => validateFormDefinitionDefaults(definition)).toThrow(FormDefinitionValidationError)
  })

  it('skips checkbox defaults', () => {
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.CHECKBOX, value_name: 'agree', label: 'Agree', default: false }],
    })

    expect(() => validateFormDefinitionDefaults(definition)).not.toThrow()
  })
})

describe('assertValidFormDefinition', () => {
  it('returns the definition when defaults are valid', () => {
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name', default: 'anon' }],
    })

    expect(assertValidFormDefinition(definition)).toBe(definition)
  })
})
