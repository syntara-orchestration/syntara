import { generateUUID } from '../../../utils/generateUUID'

export type SimpleFieldType = 'string' | 'number' | 'integer' | 'boolean'

export type SimpleField = {
  id: string
  name: string
  type: SimpleFieldType
  required: boolean
}

export const SIMPLE_FIELD_TYPES: ReadonlyArray<{ value: SimpleFieldType; label: string }> = [
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'integer', label: 'Integer' },
  { value: 'boolean', label: 'Boolean' },
]

const SIMPLE_TYPE_SET = new Set<string>(SIMPLE_FIELD_TYPES.map((t) => t.value))

export type SimpleSchemaReason = 'ok' | 'invalid_json' | 'complex_schema'

export type ParsedSimpleSchema = {
  fields: SimpleField[]
  additionalProperties: boolean
  isSimpleSchema: boolean
  reason: SimpleSchemaReason
}

export function createEmptyField(): SimpleField {
  return { id: generateUUID(), name: '', type: 'string', required: false }
}

export function fieldsToJsonSchema(fields: readonly SimpleField[], additionalProperties: boolean): string {
  const properties: Record<string, { type: string }> = {}
  const required: string[] = []

  for (const field of fields) {
    if (!field.name.trim()) continue
    properties[field.name.trim()] = { type: field.type }
    if (field.required) {
      required.push(field.name.trim())
    }
  }

  const schema: Record<string, unknown> = {
    $schema: 'http://json-schema.org/draft-07/schema#',
    type: 'object',
    properties,
    additionalProperties,
  }

  if (required.length > 0) {
    schema.required = required
  }

  return JSON.stringify(schema, null, 2)
}

export function jsonSchemaToFields(jsonString: string | undefined): ParsedSimpleSchema {
  const empty: ParsedSimpleSchema = { fields: [], additionalProperties: true, isSimpleSchema: true, reason: 'ok' }
  const invalid: ParsedSimpleSchema = { ...empty, isSimpleSchema: false, reason: 'invalid_json' }
  const complex: ParsedSimpleSchema = { ...empty, isSimpleSchema: false, reason: 'complex_schema' }

  const trimmed = jsonString?.trim()
  if (!trimmed) return empty

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return invalid
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return invalid
  }

  const obj = parsed as Record<string, unknown>

  if (obj.type !== 'object') {
    return complex
  }

  if (hasComplexFeatures(obj)) {
    return complex
  }

  const properties = (obj.properties ?? {}) as Record<string, unknown>
  const requiredArr = Array.isArray(obj.required) ? (obj.required as string[]) : []
  const requiredSet = new Set(requiredArr)
  const additionalProperties = obj.additionalProperties !== false

  const fields: SimpleField[] = []

  for (const [name, prop] of Object.entries(properties)) {
    if (typeof prop !== 'object' || prop === null || Array.isArray(prop)) {
      return complex
    }

    const propObj = prop as Record<string, unknown>

    if (hasPropertyComplexFeatures(propObj)) {
      return complex
    }

    const rawType = propObj.type
    const propType = typeof rawType === 'string' ? rawType : 'string'
    if (!SIMPLE_TYPE_SET.has(propType)) {
      return complex
    }

    fields.push({
      id: generateUUID(),
      name,
      type: propType as SimpleFieldType,
      required: requiredSet.has(name),
    })
  }

  return { fields, additionalProperties, isSimpleSchema: true, reason: 'ok' }
}

const COMPLEX_KEYS = new Set(['oneOf', 'anyOf', 'allOf', 'not', 'if', 'then', 'else', 'patternProperties', '$ref'])

function hasComplexFeatures(obj: Record<string, unknown>): boolean {
  for (const key of Object.keys(obj)) {
    if (COMPLEX_KEYS.has(key)) return true
  }
  return false
}

const PROPERTY_COMPLEX_KEYS = new Set([
  'oneOf',
  'anyOf',
  'allOf',
  'not',
  'if',
  'then',
  'else',
  '$ref',
  'properties',
  'items',
  'enum',
  'pattern',
  'patternProperties',
  'minProperties',
  'maxProperties',
])

function hasPropertyComplexFeatures(propObj: Record<string, unknown>): boolean {
  for (const key of Object.keys(propObj)) {
    if (PROPERTY_COMPLEX_KEYS.has(key)) return true
  }
  if (propObj.type === 'object' || propObj.type === 'array') return true
  return false
}

const SAMPLE_VALUES: Record<string, unknown> = {
  string: 'example',
  number: 0,
  integer: 0,
  boolean: true,
  array: [],
  object: {},
}

export function generateSampleBody(jsonSchema: string | undefined): string {
  const trimmed = jsonSchema?.trim()
  if (!trimmed) return '{}'

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return '{}'
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return '{}'
  const obj = parsed as Record<string, unknown>
  if (obj.type !== 'object') return '{}'

  const properties = (obj.properties ?? {}) as Record<string, unknown>
  const sample: Record<string, unknown> = {}

  for (const [name, prop] of Object.entries(properties)) {
    if (typeof prop !== 'object' || prop === null) continue
    const propType = (prop as Record<string, unknown>).type
    if (typeof propType === 'string' && propType in SAMPLE_VALUES) {
      sample[name] = SAMPLE_VALUES[propType]
    } else {
      sample[name] = null
    }
  }

  if (Object.keys(sample).length === 0) return '{}'
  return JSON.stringify(sample, null, 2)
}
