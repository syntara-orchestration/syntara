import { describe, expect, it } from 'vitest'

import { parseFormDefinition } from './formDefinitionSchema'
import { formDefinitionToJsonSchema } from './formDefinitionToJsonSchema'
import { FormFieldTypeEnum } from './formFieldTypeEnum'
import { jsonSchemaStringToFormDefinition, jsonSchemaToFormDefinition } from './jsonSchemaToFormDefinition'

describe('jsonSchemaToFormDefinition', () => {
  it('round-trips definitions produced by formDefinitionToJsonSchema', () => {
    const original = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.TEXT, value_name: 'title', label: 'Title', required: true },
        { type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' },
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'tier',
          label: 'Tier',
          options: {
            source: 'static',
            values: [
              { display_label: 'A', value: 'a' },
              { display_label: 'B', value: 'b' },
            ],
          },
        },
      ],
    })

    const schema = formDefinitionToJsonSchema(original)
    const imported = jsonSchemaToFormDefinition(schema)
    expect(imported.success).toBe(true)
    if (!imported.success) {
      return
    }

    expect(imported.data.fields.map((f) => f.value_name)).toEqual(['title', 'due', 'tier'])
    expect(imported.data.fields[0]?.required).toBe(true)
    expect(imported.data.fields[1]?.type).toBe(FormFieldTypeEnum.DATE)
    const tier = imported.data.fields[2]
    expect(tier?.type).toBe(FormFieldTypeEnum.DROPDOWN)
    if (tier?.type === FormFieldTypeEnum.DROPDOWN && tier.options.source === 'static') {
      expect(tier.options.values.map((v) => v.value)).toEqual(['a', 'b'])
    }
  })

  it('rejects invalid JSON strings', () => {
    expect(jsonSchemaStringToFormDefinition('{').success).toBe(false)
  })

  it('rejects schemas without properties', () => {
    const result = jsonSchemaToFormDefinition({ type: 'object' })
    expect(result.success).toBe(false)
  })

  it('imports string field variants without enum', () => {
    const schema = {
      type: 'object',
      properties: {
        notes: { type: 'string', title: 'Notes' },
        secret: { type: 'string', title: 'Secret' },
        email: { type: 'string', format: 'email', title: 'Email' },
      },
    }
    const imported = jsonSchemaToFormDefinition(schema)
    expect(imported.success).toBe(true)
    if (!imported.success) {
      return
    }
    expect(imported.data.fields.map((f) => f.type)).toEqual([
      FormFieldTypeEnum.TEXT,
      FormFieldTypeEnum.TEXT,
      FormFieldTypeEnum.TEXT,
    ])
  })

  it('rejects invalid property keys and empty property lists', () => {
    expect(
      jsonSchemaToFormDefinition({
        type: 'object',
        properties: { 'not valid': { type: 'string', title: 'Bad' } },
      }).success
    ).toBe(false)
    expect(
      jsonSchemaToFormDefinition({
        type: 'object',
        properties: {},
      }).success
    ).toBe(false)
  })

  it('rejects non-object root and invalid property entries', () => {
    expect(jsonSchemaToFormDefinition(null).success).toBe(false)
    expect(jsonSchemaToFormDefinition({ type: 'array' }).success).toBe(false)
    expect(
      jsonSchemaToFormDefinition({
        type: 'object',
        properties: { name: 'string' },
      }).success
    ).toBe(false)
  })

  it('rejects unsupported property types', () => {
    const result = jsonSchemaToFormDefinition({
      type: 'object',
      properties: {
        blob: { type: 'object', title: 'Blob' },
      },
    })
    expect(result.success).toBe(false)
  })

  it('imports checkbox, number, and multi-select static enums', () => {
    const original = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.CHECKBOX, value_name: 'agree', label: 'Agree' },
        { type: FormFieldTypeEnum.NUMBER, value_name: 'qty', label: 'Qty' },
        {
          type: FormFieldTypeEnum.MULTI_SELECT,
          value_name: 'tags',
          label: 'Tags',
          options: {
            source: 'static',
            values: [
              { display_label: 'One', value: 'one' },
              { display_label: 'Two', value: 'two' },
            ],
          },
        },
      ],
    })

    const imported = jsonSchemaToFormDefinition(formDefinitionToJsonSchema(original))
    expect(imported.success).toBe(true)
    if (!imported.success) {
      return
    }
    expect(imported.data.fields.map((f) => f.type)).toEqual([
      FormFieldTypeEnum.CHECKBOX,
      FormFieldTypeEnum.NUMBER,
      FormFieldTypeEnum.MULTI_SELECT,
    ])
  })
})
