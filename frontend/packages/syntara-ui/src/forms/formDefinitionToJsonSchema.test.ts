import { describe, expect, it } from 'vitest'

import { parseFormDefinition } from './formDefinitionSchema'
import { formDefinitionToJsonSchema, formDefinitionToJsonSchemaString } from './formDefinitionToJsonSchema'
import { FormFieldTypeEnum } from './formFieldTypeEnum'

describe('formDefinitionToJsonSchema', () => {
  it('maps field types and required keys', () => {
    const definition = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name', required: true },
        { type: FormFieldTypeEnum.CHECKBOX, value_name: 'agree', label: 'Agree' },
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

    const schema = formDefinitionToJsonSchema(definition)
    expect(schema.required).toEqual(['name'])
    expect(schema.properties.name).toMatchObject({ type: 'string', title: 'Name' })
    expect(schema.properties.agree).toMatchObject({ type: 'boolean' })
    expect(schema.properties.tier).toMatchObject({ type: 'string', enum: ['a', 'b'] })
  })

  it('maps date, number, and multi-select static arrays', () => {
    const definition = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' },
        { type: FormFieldTypeEnum.NUMBER, value_name: 'qty', label: 'Qty' },
        {
          type: FormFieldTypeEnum.MULTI_SELECT,
          value_name: 'tags',
          label: 'Tags',
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

    const schema = formDefinitionToJsonSchema(definition)
    expect(schema.properties.due).toMatchObject({ type: 'string', format: 'date' })
    expect(schema.properties.qty).toMatchObject({ type: 'number' })
    expect(schema.properties.tags).toMatchObject({
      type: 'array',
      items: { type: 'number', enum: [1, 2] },
    })
  })

  it('uses generic string schema for dynamic option sources', () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'remote',
          label: 'Remote',
          options: {
            source: 'dynamic',
            expression: 'steps.fetch.options',
            label_key: 'name',
            value_key: 'id',
          },
        },
      ],
    })

    expect(formDefinitionToJsonSchema(definition).properties.remote).toMatchObject({ type: 'string' })
  })

  it('serializes to formatted JSON', () => {
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'x', label: 'X' }],
    })
    const json = formDefinitionToJsonSchemaString(definition)
    expect(json).toContain('"type": "object"')
    expect(json).toContain('"x"')
  })
})
