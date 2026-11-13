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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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
 * Build the public JSON Schema from visual rows, retaining advanced-schema metadata where possible.
 */
export function outputSchemaFromFields(
  fields: SubWorkflowOutputField[],
  baseSchema?: unknown
): Record<string, unknown> | undefined {
  const schema = isRecord(baseSchema) ? (JSON.parse(JSON.stringify(baseSchema)) as Record<string, unknown>) : {}
  schema.type = 'object'
  if (!isRecord(schema.properties)) schema.properties = {}
  const rootProperties = schema.properties as Record<string, unknown>

  const validRows = fields.flatMap((field) => {
    const rawSegments = field.path.split('.')
    if (rawSegments.some((segment) => !segment.trim())) return []
    return [{ field, segments: rawSegments.map((segment) => segment.trim()) }]
  })

  const includedPaths = new Set(validRows.map(({ segments }) => segments.join('.')))

  // Prune properties not in the field list
  const prune = (properties: Record<string, unknown>, prefix: string[]) => {
    for (const [name, rawProperty] of Object.entries(properties)) {
      const path = [...prefix, name]
      if (isRecord(rawProperty) && isRecord(rawProperty.properties) && Object.keys(rawProperty.properties).length > 0) {
        prune(rawProperty.properties, path)
        if (Object.keys(rawProperty.properties).length === 0 && !includedPaths.has(path.join('.')))
          delete properties[name]
      } else if (!includedPaths.has(path.join('.'))) {
        delete properties[name]
      }
    }
  }
  prune(rootProperties, [])

  // Clear all required arrays
  const clearRequired = (node: Record<string, unknown>) => {
    delete node.required
    if (!isRecord(node.properties)) return
    Object.values(node.properties).forEach((property) => {
      if (isRecord(property)) clearRequired(property)
    })
  }
  clearRequired(schema)

  // Track which fields are required at each level
  const requiredByParent = new Map<string, Set<string>>()

  // Build nested structure from flat rows
  for (const { field, segments } of validRows) {
    let properties = rootProperties
    let property: Record<string, unknown> | undefined

    for (const [index, segment] of segments.entries()) {
      const existingProperty = properties[segment]
      property = isRecord(existingProperty) ? existingProperty : {}
      properties[segment] = property
      const isLeaf = index === segments.length - 1

      if (!isLeaf) {
        property.type ??= 'object'
        if (!isRecord(property.properties)) property.properties = {}
        const nextProperties = property.properties
        if (isRecord(nextProperties)) {
          properties = nextProperties
        }
      } else {
        // Leaf node - set type and description
        if (field.type !== 'unknown' && !(field.type === 'number' && property.type === 'integer')) {
          property.type = field.type
        }
        if (field.description?.trim()) property.description = field.description.trim()
        else delete property.description
      }

      // Track required fields
      if (field.required) {
        const parentPath = segments.slice(0, index).join('.')
        const required = requiredByParent.get(parentPath) ?? new Set<string>()
        required.add(segment)
        requiredByParent.set(parentPath, required)
      }
    }
  }

  // Apply required arrays
  for (const [parentPath, required] of requiredByParent) {
    const parent = parentPath
      ? parentPath.split('.').reduce<Record<string, unknown> | undefined>((node, segment) => {
          if (!node || !isRecord(node.properties) || !isRecord(node.properties[segment])) return undefined
          return node.properties[segment]
        }, schema)
      : schema
    if (parent) parent.required = [...required]
  }

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
