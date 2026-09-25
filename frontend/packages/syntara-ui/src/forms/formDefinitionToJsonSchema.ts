import type { FormDefinition, FormField } from '@syntara/contracts'

import { FormFieldTypeEnum } from './formFieldTypeEnum'
import { SYNTARA_FORM_OPTIONS_EXTENSION, type SyntaraFormOptionsExtension } from './jsonSchemaFormExtensions'

type JsonSchemaObject = {
  $schema: string
  type: 'object'
  properties: Record<string, Record<string, unknown>>
  required?: string[]
  additionalProperties: boolean
}

type OptionScalar = string | number | boolean

function enumValuesFromStaticOptions(values: ReadonlyArray<{ value: string | number | boolean }>): OptionScalar[] {
  return values.map((option) => option.value)
}

function jsonSchemaTypeForScalarValues(values: readonly OptionScalar[]): string {
  if (values.length === 0) {
    return 'string'
  }
  const first = values[0]
  if (values.every((value) => typeof value === typeof first)) {
    return typeof first
  }
  return 'string'
}

function defaultForJsonSchema(field: FormField): unknown {
  if (!Object.hasOwn(field, 'default')) {
    return undefined
  }
  return field.default
}

function syntaraOptionsExtension(field: FormField): SyntaraFormOptionsExtension | undefined {
  if (field.type !== FormFieldTypeEnum.DROPDOWN && field.type !== FormFieldTypeEnum.MULTI_SELECT) {
    return undefined
  }
  if (field.options.source !== 'dynamic') {
    return undefined
  }
  return {
    source: 'dynamic',
    expression: field.options.expression,
    label_key: field.options.label_key ?? null,
    value_key: field.options.value_key ?? null,
  }
}

function propertySchemaForField(field: FormField): Record<string, unknown> {
  switch (field.type) {
    case FormFieldTypeEnum.TEXT:
    case FormFieldTypeEnum.TEXTAREA:
    case FormFieldTypeEnum.MASKED_TEXT:
    case FormFieldTypeEnum.EMAIL:
      return { type: 'string' }
    case FormFieldTypeEnum.NUMBER:
      return { type: 'number' }
    case FormFieldTypeEnum.CHECKBOX:
      return { type: 'boolean' }
    case FormFieldTypeEnum.DATE:
      return { type: 'string', format: 'date' }
    case FormFieldTypeEnum.DROPDOWN:
      if (field.options.source === 'static') {
        const enumValues = enumValuesFromStaticOptions(field.options.values)
        const schema: Record<string, unknown> = { type: jsonSchemaTypeForScalarValues(enumValues) }
        if (enumValues.length > 0) {
          schema.enum = enumValues
        }
        return schema
      }
      return { type: 'string' }
    case FormFieldTypeEnum.MULTI_SELECT:
      if (field.options.source === 'static') {
        const enumValues = enumValuesFromStaticOptions(field.options.values)
        const itemType = jsonSchemaTypeForScalarValues(enumValues)
        const itemSchema: Record<string, unknown> = { type: itemType }
        if (enumValues.length > 0) {
          itemSchema.enum = enumValues
        }
        return { type: 'array', items: itemSchema }
      }
      return { type: 'array', items: { type: 'string' } }
    default:
      return { type: 'string' }
  }
}

/**
 * Builds a JSON Schema (draft-07) describing submitted values for a {@link FormDefinition}.
 * For export and preview only — workflow storage uses the typed FormDefinition model.
 */
export function formDefinitionToJsonSchema(definition: FormDefinition): JsonSchemaObject {
  const properties: Record<string, Record<string, unknown>> = {}
  const required: string[] = []

  for (const field of definition.fields) {
    const property: Record<string, unknown> = {
      ...propertySchemaForField(field),
      title: field.label,
    }
    const defaultValue = defaultForJsonSchema(field)
    if (defaultValue !== undefined) {
      property.default = defaultValue
    }
    const optionsExtension = syntaraOptionsExtension(field)
    if (optionsExtension) {
      property[SYNTARA_FORM_OPTIONS_EXTENSION] = optionsExtension
    }
    properties[field.value_name] = property
    if (field.required) {
      required.push(field.value_name)
    }
  }

  const schema: JsonSchemaObject = {
    $schema: 'http://json-schema.org/draft-07/schema#',
    type: 'object',
    properties,
    additionalProperties: false,
  }

  if (required.length > 0) {
    schema.required = required
  }

  return schema
}

export function formDefinitionToJsonSchemaString(definition: FormDefinition, indent = 2): string {
  return JSON.stringify(formDefinitionToJsonSchema(definition), null, indent)
}
