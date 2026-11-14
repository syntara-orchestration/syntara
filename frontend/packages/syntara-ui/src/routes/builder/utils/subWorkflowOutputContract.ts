import type { OutputFieldDef } from '@syntara/contracts'

export type SubWorkflowOutputField = {
  path: string
  type: OutputFieldDef['type']
  required: boolean
  description?: string
  expression?: string
}

type SchemaProperty = {
  type?: string
  description?: string
  properties?: Record<string, SchemaProperty>
  required?: string[]
}

const FIELD_TYPES: Record<string, OutputFieldDef['type']> = {
  string: 'string',
  integer: 'number',
  number: 'number',
  boolean: 'boolean',
  object: 'object',
  array: 'array',
}

const UNSUPPORTED_SIMPLE_SCHEMA_KEYS = [
  '$ref',
  'allOf',
  'anyOf',
  'oneOf',
  'not',
  'if',
  'then',
  'else',
  'patternProperties',
  'unevaluatedProperties',
  'dependentSchemas',
  'dependentRequired',
] as const

const SIMPLE_PATH_SEGMENT = /^[a-zA-Z0-9_ -]+$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasUnsupportedSimpleSchemaFeatures(schema: Record<string, unknown>): boolean {
  if (UNSUPPORTED_SIMPLE_SCHEMA_KEYS.some((key) => Object.hasOwn(schema, key))) return true

  if (isRecord(schema.properties) && schema.type !== 'object') return true
  const schemaType = schema.type
  if (Array.isArray(schemaType)) return true

  const additionalProperties = schema.additionalProperties
  if (additionalProperties !== undefined && additionalProperties !== false) return true

  if (isRecord(schema.items) && isRecord(schema.items.properties)) return true

  const properties = schema.properties
  if (!isRecord(properties)) return false
  const required = Array.isArray(schema.required)
    ? schema.required.filter((value): value is string => typeof value === 'string')
    : []
  if (required.some((name) => !Object.hasOwn(properties, name))) return true

  return Object.entries(properties).some(([name, property]) => {
    if (!name || name.includes('.') || !SIMPLE_PATH_SEGMENT.test(name) || !isRecord(property)) return true
    if (isRecord(property.properties) && property.type !== 'object') return true
    return hasUnsupportedSimpleSchemaFeatures(property)
  })
}

/**
 * Convert the persisted JSON Schema and mappings into rows for the trigger's visual field builder.
 */
export function outputFieldsFromSchema(
  schema: unknown,
  mapping: Record<string, string> = {}
): SubWorkflowOutputField[] {
  if (!isRecord(schema) || !isRecord(schema.properties)) return []

  const visit = (
    properties: Record<string, unknown>,
    prefix: string[],
    parentRequired: boolean,
    required: string[]
  ): SubWorkflowOutputField[] =>
    Object.entries(properties).flatMap(([name, rawProperty]): SubWorkflowOutputField[] => {
      if (!isRecord(rawProperty)) return []
      const property = rawProperty as SchemaProperty
      const path = [...prefix, name]
      const pathString = path.join('.')
      const isRequired = parentRequired && required.includes(name)

      // If this property has nested properties, recurse
      if (isRecord(property.properties) && Object.keys(property.properties).length > 0) {
        if (Object.hasOwn(mapping, pathString)) {
          return [
            {
              path: pathString,
              type: FIELD_TYPES[property.type ?? 'object'] ?? 'object',
              required: isRequired,
              description: property.description ?? '',
              expression: mapping[pathString],
            },
          ]
        }
        return visit(
          property.properties,
          path,
          isRequired,
          Array.isArray(property.required)
            ? property.required.filter((value): value is string => typeof value === 'string')
            : []
        )
      }

      // Leaf field
      return [
        {
          path: pathString,
          type: FIELD_TYPES[property.type ?? ''] ?? 'unknown',
          required: isRequired,
          description: property.description ?? '',
          expression: mapping[pathString] ?? '',
        },
      ]
    })

  return visit(
    schema.properties,
    [],
    true,
    Array.isArray(schema.required) ? schema.required.filter((value): value is string => typeof value === 'string') : []
  )
}

/**
 * Return whether the Simple editor can represent a schema and mapping without dropping information.
 * Advanced-only JSON Schema constructs and mappings to nested object values have no Simple row equivalent.
 */
export function isSimpleOutputSchemaRepresentable(schema: unknown, mapping: Record<string, string> = {}): boolean {
  if (!isRecord(schema) || schema.type !== 'object' || !isRecord(schema.properties)) return false
  if (hasUnsupportedSimpleSchemaFeatures(schema)) return false

  const simplePaths = new Set(outputFieldsFromSchema(schema).map((field) => field.path))
  return Object.keys(mapping).every((path) => simplePaths.has(path))
}

type ValidOutputRow = { field: SubWorkflowOutputField; segments: string[] }

function getValidOutputRows(fields: SubWorkflowOutputField[]): ValidOutputRow[] {
  return fields.flatMap((field) => {
    const segments = field.path.split('.').map((segment) => segment.trim())
    return segments.some((segment) => !segment) ? [] : [{ field, segments }]
  })
}

function pruneUnusedProperties(
  properties: Record<string, unknown>,
  includedPaths: Set<string>,
  prefix: string[] = []
): void {
  for (const [name, rawProperty] of Object.entries(properties)) {
    const path = [...prefix, name]
    if (!isRecord(rawProperty) || !isRecord(rawProperty.properties)) {
      if (!includedPaths.has(path.join('.'))) delete properties[name]
      continue
    }
    pruneUnusedProperties(rawProperty.properties, includedPaths, path)
    if (Object.keys(rawProperty.properties).length === 0 && !includedPaths.has(path.join('.'))) delete properties[name]
  }
}

function clearRequiredProperties(schema: Record<string, unknown>): void {
  delete schema.required
  if (!isRecord(schema.properties)) return
  for (const property of Object.values(schema.properties)) {
    if (isRecord(property)) clearRequiredProperties(property)
  }
}

function collectRequiredObjectPaths(schema: Record<string, unknown>): string[] {
  const paths: string[] = []
  const visit = (current: Record<string, unknown>, prefix: string[] = [], requiredAncestors = true) => {
    if (!isRecord(current.properties)) return
    const requiredNames = new Set(
      Array.isArray(current.required) ? current.required.filter((name): name is string => typeof name === 'string') : []
    )
    for (const [name, property] of Object.entries(current.properties)) {
      if (!isRecord(property)) continue
      const path = [...prefix, name]
      const isRequired = requiredAncestors && requiredNames.has(name)
      if (isRequired && (property.type === 'object' || isRecord(property.properties))) paths.push(path.join('.'))
      visit(property, path, isRequired)
    }
  }
  visit(schema)
  return paths
}

function setOutputLeaf(property: Record<string, unknown>, field: SubWorkflowOutputField): void {
  const preservesInteger = field.type === 'number' && property.type === 'integer'
  if (field.type !== 'unknown' && !preservesInteger) property.type = field.type
  if (field.description?.trim()) property.description = field.description.trim()
  else delete property.description
}

function nestedPropertiesFor(property: Record<string, unknown>): Record<string, unknown> {
  property.type ??= 'object'
  if (isRecord(property.properties)) return property.properties
  const properties: Record<string, unknown> = {}
  property.properties = properties
  return properties
}

function addRequiredField(
  requiredByParent: Map<string, Set<string>>,
  segments: string[],
  index: number,
  segment: string
): void {
  const parentPath = segments.slice(0, index).join('.')
  const required = requiredByParent.get(parentPath) ?? new Set<string>()
  required.add(segment)
  requiredByParent.set(parentPath, required)
}

function addOutputRows(rootProperties: Record<string, unknown>, validRows: ValidOutputRow[]): Map<string, Set<string>> {
  const requiredByParent = new Map<string, Set<string>>()
  for (const { field, segments } of validRows) {
    let properties = rootProperties
    for (const [index, segment] of segments.entries()) {
      const existingProperty = properties[segment]
      const property = isRecord(existingProperty) ? existingProperty : {}
      properties[segment] = property
      const isLeaf = index === segments.length - 1
      if (isLeaf) setOutputLeaf(property, field)
      else properties = nestedPropertiesFor(property)
      if (field.required) addRequiredField(requiredByParent, segments, index, segment)
    }
  }
  return requiredByParent
}

function findSchemaAtPath(schema: Record<string, unknown>, path: string): Record<string, unknown> | undefined {
  if (!path) return schema
  return path.split('.').reduce<Record<string, unknown> | undefined>((node, segment) => {
    if (!node || !isRecord(node.properties) || !isRecord(node.properties[segment])) return undefined
    return node.properties[segment]
  }, schema)
}

function applyRequiredProperties(schema: Record<string, unknown>, requiredByParent: Map<string, Set<string>>): void {
  for (const [path, required] of requiredByParent) {
    const parent = findSchemaAtPath(schema, path)
    if (parent) parent.required = [...required]
  }
}

/** Build the public JSON Schema from visual rows, retaining advanced-schema metadata where possible. */
export function outputSchemaFromFields(
  fields: SubWorkflowOutputField[],
  baseSchema?: unknown
): Record<string, unknown> | undefined {
  const schema = isRecord(baseSchema) ? (JSON.parse(JSON.stringify(baseSchema)) as Record<string, unknown>) : {}
  schema.type = 'object'
  if (!isRecord(schema.properties)) schema.properties = {}
  const rootProperties = isRecord(schema.properties) ? schema.properties : {}
  schema.properties = rootProperties
  const requiredObjectPaths = collectRequiredObjectPaths(schema)
  const validRows = getValidOutputRows(fields)
  const includedPaths = new Set(validRows.map(({ segments }) => segments.join('.')))
  pruneUnusedProperties(rootProperties, includedPaths)
  clearRequiredProperties(schema)
  const requiredByParent = addOutputRows(rootProperties, validRows)
  for (const path of requiredObjectPaths) {
    if (!findSchemaAtPath(schema, path)) continue
    const segments = path.split('.')
    segments.forEach((segment, index) => addRequiredField(requiredByParent, segments, index, segment))
  }
  applyRequiredProperties(schema, requiredByParent)
  return Object.keys(rootProperties).length > 0 ? schema : undefined
}

/**
 * Extract template expression mappings from visual rows.
 */
export function outputMappingFromFields(fields: SubWorkflowOutputField[]): Record<string, string> {
  return Object.fromEntries(
    fields
      .map(
        (field) =>
          [
            field.path
              .split('.')
              .map((segment) => segment.trim())
              .join('.'),
            field.expression?.trim() ?? '',
          ] as const
      )
      .filter(([path, expression]) => path.length > 0 && expression.length > 0)
  )
}
