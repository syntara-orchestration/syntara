import type { FormDefinition, FormField } from '@syntara/contracts'

import { isValidFormFieldValueName } from './formConstants'
import { safeParseFormDefinition } from './formDefinitionSchema'
import { FormFieldTypeEnum } from './formFieldTypeEnum'

type OptionScalar = string | number | boolean

type JsonSchemaProperty = {
  type?: unknown
  format?: unknown
  title?: unknown
  enum?: unknown
  items?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isOptionScalar(value: unknown): value is OptionScalar {
  const kind = typeof value
  return kind === 'string' || kind === 'number' || kind === 'boolean'
}

function parseEnumValues(raw: unknown): OptionScalar[] | null {
  if (!Array.isArray(raw) || raw.length === 0) {
    return null
  }
  if (!raw.every(isOptionScalar)) {
    return null
  }
  return raw
}

function staticOptionsFromEnum(enumValues: readonly OptionScalar[]) {
  return {
    source: 'static' as const,
    values: enumValues.map((value) => ({
      display_label: String(value),
      value,
    })),
  }
}

function inferFieldType(property: JsonSchemaProperty): FormField['type'] | null {
  if (property.type === 'boolean') {
    return FormFieldTypeEnum.CHECKBOX
  }
  if (property.type === 'number' || property.type === 'integer') {
    return FormFieldTypeEnum.NUMBER
  }
  if (property.type === 'array') {
    return FormFieldTypeEnum.MULTI_SELECT
  }
  if (property.type === 'string') {
    if (property.format === 'date') {
      return FormFieldTypeEnum.DATE
    }
    if (parseEnumValues(property.enum)) {
      return FormFieldTypeEnum.DROPDOWN
    }
    return FormFieldTypeEnum.TEXT
  }
  return null
}

function fieldFromProperty(valueName: string, property: JsonSchemaProperty, required: boolean): FormField | null {
  const fieldType = inferFieldType(property)
  if (fieldType === null || !isValidFormFieldValueName(valueName)) {
    return null
  }

  const label = typeof property.title === 'string' && property.title.trim() !== '' ? property.title : valueName
  const base = {
    value_name: valueName,
    label,
    placeholder: null as string | null,
    help_text: null as string | null,
    required,
  }

  switch (fieldType) {
    case FormFieldTypeEnum.CHECKBOX:
      return { ...base, type: FormFieldTypeEnum.CHECKBOX, default: false }
    case FormFieldTypeEnum.NUMBER:
      return { ...base, type: FormFieldTypeEnum.NUMBER, default: null }
    case FormFieldTypeEnum.DATE:
      return { ...base, type: FormFieldTypeEnum.DATE, default: null }
    case FormFieldTypeEnum.DROPDOWN: {
      const enumValues = parseEnumValues(property.enum)
      if (!enumValues) {
        return {
          ...base,
          type: FormFieldTypeEnum.DROPDOWN,
          options: { source: 'dynamic', expression: '', label_key: null, value_key: null },
          default: null,
        }
      }
      return {
        ...base,
        type: FormFieldTypeEnum.DROPDOWN,
        options: staticOptionsFromEnum(enumValues),
        default: null,
      }
    }
    case FormFieldTypeEnum.MULTI_SELECT: {
      const items = isRecord(property.items) ? property.items : null
      const enumValues = items ? parseEnumValues(items.enum) : null
      if (!enumValues) {
        return {
          ...base,
          type: FormFieldTypeEnum.MULTI_SELECT,
          options: { source: 'dynamic', expression: '', label_key: null, value_key: null },
          default: null,
        }
      }
      return {
        ...base,
        type: FormFieldTypeEnum.MULTI_SELECT,
        options: staticOptionsFromEnum(enumValues),
        default: null,
      }
    }
    case FormFieldTypeEnum.TEXT:
      return { ...base, type: FormFieldTypeEnum.TEXT }
    case FormFieldTypeEnum.TEXTAREA:
      return { ...base, type: FormFieldTypeEnum.TEXTAREA }
    case FormFieldTypeEnum.MASKED_TEXT:
      return { ...base, type: FormFieldTypeEnum.MASKED_TEXT }
    case FormFieldTypeEnum.EMAIL:
      return { ...base, type: FormFieldTypeEnum.EMAIL }
  }
}

export type JsonSchemaToFormDefinitionResult =
  | { success: true; data: FormDefinition }
  | { success: false; error: string }

/**
 * Best-effort import of JSON Schema produced by {@link formDefinitionToJsonSchema}.
 * Loses placeholders, help text, and non-static option sources.
 */
export function jsonSchemaToFormDefinition(input: unknown): JsonSchemaToFormDefinitionResult {
  if (!isRecord(input)) {
    return { success: false, error: 'JSON Schema must be an object' }
  }
  if (input.type !== 'object') {
    return { success: false, error: 'JSON Schema root type must be "object"' }
  }
  if (!isRecord(input.properties)) {
    return { success: false, error: 'JSON Schema must include a properties object' }
  }

  const requiredNames = new Set(
    Array.isArray(input.required) ? input.required.filter((name): name is string => typeof name === 'string') : []
  )

  const fields: FormField[] = []
  for (const [valueName, rawProperty] of Object.entries(input.properties)) {
    if (!isRecord(rawProperty)) {
      return { success: false, error: `Invalid property schema for "${valueName}"` }
    }
    const field = fieldFromProperty(valueName, rawProperty as JsonSchemaProperty, requiredNames.has(valueName))
    if (!field) {
      return { success: false, error: `Unsupported or invalid property "${valueName}"` }
    }
    fields.push(field)
  }

  if (fields.length === 0) {
    return { success: false, error: 'JSON Schema must define at least one property' }
  }

  const parsed = safeParseFormDefinition({ fields })
  if (!parsed.success) {
    return { success: false, error: parsed.errors[0]?.message ?? 'Imported schema is not a valid form definition' }
  }

  return { success: true, data: parsed.data }
}

export function jsonSchemaStringToFormDefinition(json: string): JsonSchemaToFormDefinitionResult {
  try {
    const parsed: unknown = JSON.parse(json)
    return jsonSchemaToFormDefinition(parsed)
  } catch {
    return { success: false, error: 'Invalid JSON' }
  }
}
