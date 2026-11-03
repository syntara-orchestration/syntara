import { getNodeOutputSchema } from '@syntara/contracts'

import type { PreviewFieldDef } from './effectiveOutputSchema'

/**
 * Build a JSON skeleton string from a node's output schema.
 * Used by both InputPanel and OutputPanel for mock data editor initial values.
 */
export function buildMockJsonSkeleton(nodeType: string | null, schemaFields: PreviewFieldDef[] | null): string {
  // Prefer a supplied effective schema so configuration-derived form fields survive.
  const schema = nodeType ? getNodeOutputSchema(nodeType) : null
  const effectiveSchema = schemaFields ?? schema
  if (!effectiveSchema) return '{}'

  const skeleton = buildSkeletonFields(effectiveSchema)
  return JSON.stringify(skeleton, null, 2)
}

function buildSkeletonFields(fields: PreviewFieldDef[]): Record<string, unknown> {
  const skeleton: Record<string, unknown> = {}
  for (const field of fields) {
    skeleton[field.name] = field.children?.length ? buildSkeletonFields(field.children) : ''
  }
  return skeleton
}

type ParseJsonObjectResult = { success: true; data: Record<string, unknown> } | { success: false; error: string }

/**
 * Parse a JSON string and validate that it is a plain object (not an array or null).
 * Returns a discriminated union so callers can handle success/failure without try/catch.
 */
export function parseJsonObject(jsonText: string): ParseJsonObjectResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText)
  } catch (error) {
    return { success: false, error: (error as Error).message }
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { success: false, error: 'Mock data must be a JSON object' }
  }

  return { success: true, data: parsed as Record<string, unknown> }
}
