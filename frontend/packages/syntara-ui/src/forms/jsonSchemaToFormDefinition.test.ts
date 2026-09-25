import { describe, expect, it } from 'vitest'

import { parseFormDefinition } from './formDefinitionSchema'
import { formDefinitionToJsonSchema } from './formDefinitionToJsonSchema'
import { FormFieldTypeEnum } from './formFieldTypeEnum'
import { jsonSchemaStringToFormDefinition, jsonSchemaToFormDefinition } from './jsonSchemaToFormDefinition'

describe('jsonSchemaToFormDefinition', () => {
  it('round-trips field defaults and numeric dropdown enums', () => {
    const original = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.TEXT, value_name: 'title', label: 'Title', default: 'preset' },
        { type: FormFieldTypeEnum.NUMBER, value_name: 'qty', label: 'Qty', default: 3 },
        { type: FormFieldTypeEnum.CHECKBOX, value_name: 'agree', label: 'Agree', default: true },
        { type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due', default: '2026-01-02' },
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'tier',
          label: 'Tier',
          default: 2,
          options: {
            source: 'static',
            values: [
              { display_label: 'One', value: 1 },
              { display_label: 'Two', value: 2 },
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
    const fields = imported.data.fields
    expect(fields[0]?.type).toBe(FormFieldTypeEnum.TEXT)
    expect(fields[0]?.default).toBe('preset')
    expect(fields[1]?.default).toBe(3)
    expect(fields[2]?.default).toBe(true)
    expect(fields[3]?.default).toBe('2026-01-02')
    const tier = fields[4]
    expect(tier?.type).toBe(FormFieldTypeEnum.DROPDOWN)
    if (tier?.type === FormFieldTypeEnum.DROPDOWN) {
      expect(tier.default).toBe(2)
      if (tier.options.source === 'static') {
        expect(tier.options.values.map((option) => option.value)).toEqual([1, 2])
      }
    }
  })

  it('round-trips dynamic dropdown and multi-select options via extension', () => {
    const original = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'env',
          label: 'Env',
          options: { source: 'dynamic', expression: '${nodes.upstream.envs}', label_key: 'name', value_key: 'id' },
        },
        {
          type: FormFieldTypeEnum.MULTI_SELECT,
          value_name: 'tags',
          label: 'Tags',
          options: { source: 'dynamic', expression: 'options.tags', label_key: null, value_key: null },
        },
      ],
    })

    const imported = jsonSchemaToFormDefinition(formDefinitionToJsonSchema(original))
    expect(imported.success).toBe(true)
    if (!imported.success) {
      return
    }
    const env = imported.data.fields[0]
    const tags = imported.data.fields[1]
    expect(env?.type).toBe(FormFieldTypeEnum.DROPDOWN)
    if (env?.type === FormFieldTypeEnum.DROPDOWN && env.options.source === 'dynamic') {
      expect(env.options.expression).toBe('${nodes.upstream.envs}')
      expect(env.options.label_key).toBe('name')
      expect(env.options.value_key).toBe('id')
    }
    expect(tags?.type).toBe(FormFieldTypeEnum.MULTI_SELECT)
    if (tags?.type === FormFieldTypeEnum.MULTI_SELECT && tags.options.source === 'dynamic') {
      expect(tags.options.expression).toBe('options.tags')
    }
  })

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
      FormFieldTypeEnum.EMAIL,
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
