import { safeJSONReviver } from '../../../utils/jsonSafeParse'

export type InvocationInputField = {
  name: string
  type: string
  required: boolean
  description?: string
  defaultValue?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function getFieldType(schema: Record<string, unknown>): string {
  const schemaType = schema.type
  if (typeof schemaType === 'string') return schemaType
  if (Array.isArray(schemaType)) {
    const firstType = schemaType.find((value): value is string => typeof value === 'string' && value !== 'null')
    if (firstType) return firstType
  }
  return 'string'
}

/** Convert the JSON Schema object returned by the invocation-schema API into form fields. */
export function getInvocationInputFields(inputSchema: unknown): InvocationInputField[] {
  if (!isRecord(inputSchema) || !isRecord(inputSchema.properties)) return []

  const required = new Set(
    Array.isArray(inputSchema.required) ? inputSchema.required.filter((name) => typeof name === 'string') : []
  )

  return Object.entries(inputSchema.properties).flatMap(([name, rawField]) => {
    if (!isRecord(rawField)) return []

    return [
      {
        name,
        type: getFieldType(rawField),
        required: required.has(name),
        description: typeof rawField.description === 'string' ? rawField.description : undefined,
        ...(Object.hasOwn(rawField, 'default') && { defaultValue: rawField.default }),
      },
    ]
  })
}

function isTemplateExpression(value: unknown): value is string {
  return typeof value === 'string' && value.includes('${')
}

function isMissing(value: unknown): boolean {
  return value === undefined || value === null || value === ''
}

function parseJsonValue(value: unknown): unknown {
  if (typeof value !== 'string') return value
  return JSON.parse(value, safeJSONReviver) as unknown
}

function normalizeNumber(value: unknown, field: InvocationInputField): unknown {
  if (typeof value === 'number') return value
  if (typeof value !== 'string' || value.trim() === '') return value

  const parsed = Number(value)
  const invalidNumber = !Number.isFinite(parsed)
  const invalidInteger = field.type === 'integer' && !Number.isInteger(parsed)
  if (invalidNumber || invalidInteger) throw new Error(`Enter a valid ${field.type} for "${field.name}".`)
  return parsed
}

function normalizeBoolean(value: unknown, field: InvocationInputField): unknown {
  if (typeof value === 'boolean') return value
  if (value === 'true') return true
  if (value === 'false') return false
  throw new Error(`Enter true or false for "${field.name}".`)
}

function normalizeObject(value: unknown, field: InvocationInputField): unknown {
  const parsed = parseJsonValue(value)
  if (!isRecord(parsed)) throw new Error(`Enter a JSON object for "${field.name}".`)
  return parsed
}

function normalizeArray(value: unknown, field: InvocationInputField): unknown {
  const parsed = parseJsonValue(value)
  if (!Array.isArray(parsed)) throw new Error(`Enter a JSON array for "${field.name}".`)
  return parsed
}

function normalizeFieldValue(value: unknown, field: InvocationInputField): unknown {
  if (isTemplateExpression(value)) return value

  const normalizers: Record<string, (value: unknown, field: InvocationInputField) => unknown> = {
    integer: normalizeNumber,
    number: normalizeNumber,
    boolean: normalizeBoolean,
    object: normalizeObject,
    array: normalizeArray,
  }
  return normalizers[field.type]?.(value, field) ?? value
}

/** Apply defaults and coerce present values, leaving missing required inputs for workflow validation. */
export function serializeInvocationInputMapping(
  values: Record<string, unknown>,
  fields: InvocationInputField[]
): Record<string, unknown> {
  return Object.fromEntries(
    fields.flatMap((field) => {
      const rawValue = values[field.name]
      if (isMissing(rawValue)) return []
      return [[field.name, normalizeFieldValue(rawValue, field)]]
    })
  )
}

/** Parse the free-form fallback used when a child trigger has no declared input schema. */
export function parseFreeformInputMapping(value: string): Record<string, unknown> {
  if (!value.trim()) return {}

  const parsed = JSON.parse(value, safeJSONReviver) as unknown
  if (!isRecord(parsed)) throw new Error('Input mapping must be a JSON object.')
  return parsed
}

export function formatInputMappingJson(value: Record<string, unknown> | undefined): string {
  return JSON.stringify(value ?? {}, null, 2)
}
