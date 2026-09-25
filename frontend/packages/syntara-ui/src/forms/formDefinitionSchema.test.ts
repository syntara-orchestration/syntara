import { describe, expect, it } from 'vitest'

import { parseFormDefinition, safeParseFormDefinition } from './formDefinitionSchema'
import { FormFieldTypeEnum } from './formFieldTypeEnum'
import { FormDefinitionValidationError } from './formValidationErrors'

const staticOptions = {
  source: 'static' as const,
  values: [
    { display_label: 'A', value: 'a' },
    { display_label: 'B', value: 'b' },
  ],
}

describe('formDefinitionSchema', () => {
  it('parses a valid multi-field definition', () => {
    const data = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name' },
        { type: FormFieldTypeEnum.NUMBER, value_name: 'age', label: 'Age' },
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'env',
          label: 'Environment',
          options: staticOptions,
        },
      ],
    })

    expect(data.fields).toHaveLength(3)
  })

  it('rejects duplicate value_name entries', () => {
    const result = safeParseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.TEXT, value_name: 'dup', label: 'One' },
        { type: FormFieldTypeEnum.TEXT, value_name: 'dup', label: 'Two' },
      ],
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.errors[0]?.message).toContain('Duplicate field names')
    }
  })

  it('rejects dropdown default not in static options', () => {
    expect(() =>
      parseFormDefinition({
        fields: [
          {
            type: FormFieldTypeEnum.DROPDOWN,
            value_name: 'choice',
            label: 'Choice',
            options: staticOptions,
            default: 'missing',
          },
        ],
      })
    ).toThrow(FormDefinitionValidationError)
  })

  it('rejects multi-select default values not in static options', () => {
    const result = safeParseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.MULTI_SELECT,
          value_name: 'tags',
          label: 'Tags',
          options: staticOptions,
          default: ['a', 'z'],
        },
      ],
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.errors[0]?.message).toContain('default values')
    }
  })

  it('returns parsed data from safeParseFormDefinition on success', () => {
    const result = safeParseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name' }],
    })

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.fields[0]?.value_name).toBe('name')
    }
  })

  it('returns structured errors from safeParseFormDefinition when fields are invalid', () => {
    const result = safeParseFormDefinition({ fields: [] })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.errors.length).toBeGreaterThan(0)
      expect(result.errors[0]?.code).toBe('invalid_default')
    }
  })

  it('parses the form-prompt-full example form_definition shape', () => {
    const data = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'environment',
          label: 'Environment',
          required: true,
          options: {
            source: 'static',
            values: [
              { display_label: 'Development', value: 'dev' },
              { display_label: 'Staging', value: 'staging' },
              { display_label: 'Production', value: 'production' },
            ],
          },
        },
        {
          type: FormFieldTypeEnum.TEXT,
          value_name: 'version',
          label: 'Version',
          required: true,
          placeholder: 'v1.0.0',
        },
        {
          type: FormFieldTypeEnum.CHECKBOX,
          value_name: 'confirmation',
          label: 'I confirm this deployment',
          required: true,
        },
      ],
    })

    expect(data.fields.map((f) => f.value_name)).toEqual(['environment', 'version', 'confirmation'])
  })
})
