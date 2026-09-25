import type { FormDefinition, FormField } from '@syntara/contracts'

import { isValidFormFieldValueName } from './formConstants'
import { safeParseFormDefinition } from './formDefinitionSchema'
import { FormFieldTypeEnum } from './formFieldTypeEnum'
import { SYNTARA_FORM_OPTIONS_EXTENSION, type SyntaraFormOptionsExtension } from './jsonSchemaFormExtensions'

type OptionScalar = string | number | boolean

type JsonSchemaProperty = {
  type?: unknown
  format?: unknown
  title?: unknown
  enum?: unknown
  items?: unknown
  default?: unknown
  [SYNTARA_FORM_OPTIONS_EXTENSION]?: unknown
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

function parseSyntaraOptionsExtension(property: JsonSchemaProperty): SyntaraFormOptionsExtension | null {
  const raw = property[SYNTARA_FORM_OPTIONS_EXTENSION]
  if (!isRecord(raw) || raw.source !== 'dynamic') {
    return null
  }
  if (typeof raw.expression !== 'string' || raw.expression.trim() === '') {
    return null
  }
  return {
    source: 'dynamic',
    expression: raw.expression,
    label_key: typeof raw.label_key === 'string' ? raw.label_key : null,
    value_key: typeof raw.value_key === 'string' ? raw.value_key : null,
  }
}

function inferFieldType(property: JsonSchemaProperty): FormField['type'] | null {
  if (parseSyntaraOptionsExtension(property)) {
    return property.type === 'array' ? FormFieldTypeEnum.MULTI_SELECT : FormFieldTypeEnum.DROPDOWN
  }
  if (property.type === 'array') {
    const items = isRecord(property.items) ? property.items : null
    if (items && parseEnumValues(items.enum)) {
      return FormFieldTypeEnum.MULTI_SELECT
    }
    return FormFieldTypeEnum.MULTI_SELECT
  }
  if (parseEnumValues(property.enum)) {
    return FormFieldTypeEnum.DROPDOWN
  }
  if (property.type === 'boolean') {
    return FormFieldTypeEnum.CHECKBOX
  }
  if (property.type === 'number' || property.type === 'integer') {
    return FormFieldTypeEnum.NUMBER
  }
  if (property.type === 'string') {
    if (property.format === 'date') {
      return FormFieldTypeEnum.DATE
    }
    if (property.format === 'email') {
      return FormFieldTypeEnum.EMAIL
    }
    return FormFieldTypeEnum.TEXT
  }
  return null
}

function defaultFromProperty(property: JsonSchemaProperty): unknown {
  return Object.hasOwn(property, 'default') ? property.default : undefined
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

  const importedDefault = defaultFromProperty(property)

  switch (fieldType) {
    case FormFieldTypeEnum.CHECKBOX:
      return {
        ...base,
        type: FormFieldTypeEnum.CHECKBOX,
        default: typeof importedDefault === 'boolean' ? importedDefault : false,
      }
    case FormFieldTypeEnum.NUMBER:
      return {
        ...base,
        type: FormFieldTypeEnum.NUMBER,
        default: typeof importedDefault === 'number' ? importedDefault : null,
      }
    case FormFieldTypeEnum.DATE:
      return {
        ...base,
        type: FormFieldTypeEnum.DATE,
        default: typeof importedDefault === 'string' ? importedDefault : null,
      }
    case FormFieldTypeEnum.DROPDOWN: {
      const dynamicOptions = parseSyntaraOptionsExtension(property)
      if (dynamicOptions) {
        return {
          ...base,
          type: FormFieldTypeEnum.DROPDOWN,
          options: dynamicOptions,
          default:
            importedDefault === null ||
            typeof importedDefault === 'string' ||
            typeof importedDefault === 'number' ||
            typeof importedDefault === 'boolean'
              ? importedDefault
              : null,
        }
      }
      const enumValues = parseEnumValues(property.enum)
      if (!enumValues) {
        return null
      }
      return {
        ...base,
        type: FormFieldTypeEnum.DROPDOWN,
        options: staticOptionsFromEnum(enumValues),
        default:
          importedDefault === null ||
          typeof importedDefault === 'string' ||
          typeof importedDefault === 'number' ||
          typeof importedDefault === 'boolean'
            ? importedDefault
            : null,
      }
    }
    case FormFieldTypeEnum.MULTI_SELECT: {
      const dynamicOptions = parseSyntaraOptionsExtension(property)
      if (dynamicOptions) {
        return {
          ...base,
          type: FormFieldTypeEnum.MULTI_SELECT,
          options: dynamicOptions,
          default: Array.isArray(importedDefault) ? importedDefault : null,
        }
      }
      const items = isRecord(property.items) ? property.items : null
      const enumValues = items ? parseEnumValues(items.enum) : null
      if (!enumValues) {
        return null
      }
      return {
        ...base,
        type: FormFieldTypeEnum.MULTI_SELECT,
        options: staticOptionsFromEnum(enumValues),
        default: Array.isArray(importedDefault) ? importedDefault : null,
      }
    }
    case FormFieldTypeEnum.TEXT:
      return {
        ...base,
        type: FormFieldTypeEnum.TEXT,
        ...(typeof importedDefault === 'string' ? { default: importedDefault } : {}),
      }
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
 * Loses placeholders and help text. Dynamic option sources round-trip via {@link SYNTARA_FORM_OPTIONS_EXTENSION}.
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
