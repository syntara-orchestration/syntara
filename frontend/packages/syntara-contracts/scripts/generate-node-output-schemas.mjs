/**
 * Reads backend JSON Schema files and generates a TypeScript file
 * containing node output schemas.
 *
 * Usage:
 *   node generate-node-output-schemas.mjs
 *   node generate-node-output-schemas.mjs --schemas-dir ../../../backend/src/syntara/schemas/workflows/v2
 */

import { readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------

/** Parse --schemas-dir from process.argv, falling back to the cloned repo path. */
function parseSchemasDir() {
  const idx = process.argv.indexOf('--schemas-dir')
  if (idx !== -1 && process.argv[idx + 1]) {
    return resolve(process.argv[idx + 1])
  }
  // Default: monorepo backend path (three levels up from syntara-contracts)
  return resolve('../../../backend/src/syntara/schemas/workflows/v2')
}

const schemasDir = parseSchemasDir()
const catalogPath = join(schemasDir, 'catalog', 'node_type_catalog.json')

// ---------------------------------------------------------------------------
// JSON Schema type -> simplified TypeScript type
// ---------------------------------------------------------------------------

const TYPE_MAP = {
  string: 'string',
  integer: 'number',
  number: 'number',
  boolean: 'boolean',
  object: 'object',
  array: 'array',
}

function mapType(schema) {
  const schemaType = Array.isArray(schema.type) ? schema.type.find((type) => type !== 'null') : schema.type
  if (schemaType === undefined || schemaType === null) {
    if (schema.properties || schema.additionalProperties) return 'object'
    return 'unknown'
  }
  return TYPE_MAP[schemaType] ?? 'unknown'
}

// ---------------------------------------------------------------------------
// Resolve local schema references and extract output fields recursively
// ---------------------------------------------------------------------------

function mergeSchemas(base, override) {
  const merged = { ...base, ...override }
  if (base.properties || override.properties) {
    merged.properties = { ...(base.properties ?? {}), ...(override.properties ?? {}) }
  }
  if (base.required || override.required) {
    merged.required = [...new Set([...(base.required ?? []), ...(override.required ?? [])])]
  }
  return merged
}

function resolveSchema(schema, root, resolving = new Set()) {
  if (typeof schema !== 'object' || schema === null || Array.isArray(schema)) return {}

  let resolved = {}
  const reference = schema.$ref
  if (typeof reference === 'string' && reference.startsWith('#/$defs/')) {
    if (resolving.has(reference)) return {}
    const definitionName = reference.slice('#/$defs/'.length).replace(/~1/g, '/').replace(/~0/g, '~')
    const definition = root.$defs?.[definitionName]
    if (definition) {
      const nextResolving = new Set(resolving)
      nextResolving.add(reference)
      resolved = resolveSchema(definition, root, nextResolving)
    }
  }

  if (Array.isArray(schema.allOf)) {
    for (const item of schema.allOf) {
      resolved = mergeSchemas(resolved, resolveSchema(item, root, resolving))
    }
  }

  const local = { ...schema }
  delete local.$ref
  delete local.allOf
  return mergeSchemas(resolved, local)
}

function extractFields(schema, root, resolving = new Set()) {
  const resolved = resolveSchema(schema, root, resolving)
  const properties = resolved.properties ?? {}
  const required = resolved.required ?? []

  // Build the ordered field list: required fields first (in order), then
  // remaining optional fields in their natural iteration order.
  const requiredSet = new Set(required)
  const optionalKeys = Object.keys(properties).filter((k) => !requiredSet.has(k))
  const orderedKeys = [...required, ...optionalKeys]

  return orderedKeys.map((name) => {
    const prop = resolveSchema(properties[name] ?? {}, root, resolving)
    const field = {
      name,
      type: mapType(prop),
      description: prop.description ?? '',
    }

    if (prop.properties) field.children = extractFields(prop, root, resolving)
    if (prop.additionalProperties && typeof prop.additionalProperties === 'object') {
      field.additionalProperties = extractFields(prop.additionalProperties, root, resolving)
    }
    return field
  })
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

console.log(`Reading catalog: ${catalogPath}`)

const catalog = JSON.parse(readFileSync(catalogPath, 'utf-8'))
const catalogDir = dirname(catalogPath)

/** @type {Record<string, Array<{name: string, type: string, description: string, children?: object[], additionalProperties?: object[]}>>} */
const schemas = {}

const realSchemasDir = realpathSync(schemasDir)
const normalizedSchemasDir = realSchemasDir.endsWith('/') ? realSchemasDir : realSchemasDir + '/'

for (const nodeType of catalog.node_types) {
  const schemaPath = realpathSync(resolve(catalogDir, nodeType.schema_ref))
  if (!schemaPath.startsWith(normalizedSchemasDir)) {
    console.warn(`  WARN: schema_ref for "${nodeType.type}" escapes schemas directory, skipping.`)
    continue
  }
  let schema
  try {
    schema = JSON.parse(readFileSync(schemaPath, 'utf-8'))
  } catch {
    console.warn(`  WARN: Could not read schema for "${nodeType.type}" at ${schemaPath}, skipping.`)
    continue
  }

  const resultSchema = resolveSchema(schema.resultSchema, schema)
  if (!resultSchema) {
    console.warn(`  WARN: No resultSchema in "${nodeType.type}", skipping.`)
    continue
  }

  // The standard structure uses oneOf[0] as the "Completed Result" variant.
  // Some schemas (e.g. scheduled_trigger) have a flat resultSchema with
  // properties directly on the object — fall back to that when oneOf is absent.
  const completedResult = resultSchema.oneOf?.[0] ?? (resultSchema.properties ? resultSchema : null)
  if (!completedResult || !completedResult.properties) {
    console.warn(`  WARN: No completed result variant for "${nodeType.type}", skipping.`)
    continue
  }

  const fields = extractFields(completedResult, schema)
  schemas[nodeType.type] = fields
  console.log(`  ${nodeType.type}: ${fields.length} fields`)
}

// ---------------------------------------------------------------------------
// Code generation
// ---------------------------------------------------------------------------

function quote(s) {
  // Escape backslashes, single quotes, and control characters
  return `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\0/g, '\\0')}'`
}

function fieldToLiteral(f) {
  const children = f.children ? `, children: [${f.children.map(fieldToLiteral).join(', ')}]` : ''
  const additionalProperties = f.additionalProperties
    ? `, additionalProperties: [${f.additionalProperties.map(fieldToLiteral).join(', ')}]`
    : ''
  return `{ name: ${quote(f.name)}, type: ${quote(f.type)}, description: ${quote(f.description)}${children}${additionalProperties} }`
}

const entries = Object.entries(schemas)

let output = `/**
 * Auto-generated from backend JSON Schema files.
 * DO NOT EDIT — run \`npm run gen\` to regenerate.
 *
 * Source: backend/src/syntara/schemas/workflows/v2/
 */

export interface OutputFieldDef {
  name: string
  type: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'unknown'
  description: string
  children?: OutputFieldDef[]
  additionalProperties?: OutputFieldDef[]
}

export const NODE_OUTPUT_SCHEMAS: Record<string, OutputFieldDef[]> = {\n`

for (const [nodeType, fields] of entries) {
  output += `  ${nodeType}: [\n`
  for (const f of fields) {
    output += `    ${fieldToLiteral(f)},\n`
  }
  output += `  ],\n`
}

output += `}

export function getNodeOutputSchema(nodeType: string): OutputFieldDef[] | null {
  return NODE_OUTPUT_SCHEMAS[nodeType] ?? null
}
`

// ---------------------------------------------------------------------------
// Write
// ---------------------------------------------------------------------------

// Write to a fixed location relative to this script.
const contractsSrc = resolve(import.meta.dirname, '..', 'src')
const outFile = join(contractsSrc, 'node-output-schemas.ts')

writeFileSync(outFile, output, 'utf-8')
console.log(`\nGenerated: ${outFile}`)
console.log(`Total node types: ${entries.length}`)
