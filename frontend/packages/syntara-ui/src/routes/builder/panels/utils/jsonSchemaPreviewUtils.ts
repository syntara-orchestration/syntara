import type { OutputFieldDef } from '@syntara/contracts'

type JsonSchemaProperty = Record<string, unknown>

const JSON_SCHEMA_TYPE_MAP: Record<string, OutputFieldDef['type']> = {
  string: 'string',
  number: 'number',
  integer: 'number',
  boolean: 'boolean',
  object: 'object',
  array: 'array',
}

function outputTypeFromSchemaType(schemaType: string): OutputFieldDef['type'] {
  return JSON_SCHEMA_TYPE_MAP[schemaType] ?? 'unknown'
}

/** Map a JSON Schema `type` keyword (single string) to builder preview types. */
export function mapJsonSchemaType(type?: string): OutputFieldDef['type'] {
  return type ? (JSON_SCHEMA_TYPE_MAP[type] ?? 'unknown') : 'unknown'
}

function isJsonSchemaTypeArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === 'string')
}

/** Map a JSON Schema property object to a builder preview type (form response_schema, trigger input_schema, etc.). */
export function mapJsonSchemaPropertyType(property: JsonSchemaProperty): OutputFieldDef['type'] {
  if (property.const === true || property.const === false) {
    return 'boolean'
  }

  const rawType = property.type
  if (isJsonSchemaTypeArray(rawType)) {
    const primary = rawType.find((entry) => entry !== 'null')
    return primary ? outputTypeFromSchemaType(primary) : 'unknown'
  }

  if (typeof rawType === 'string') {
    return outputTypeFromSchemaType(rawType)
  }

  return 'unknown'
}
