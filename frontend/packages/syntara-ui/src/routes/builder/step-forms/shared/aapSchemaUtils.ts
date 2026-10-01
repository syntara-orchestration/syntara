import type { z } from 'zod'

/**
 * Shared validation logic for AAP schemas (job template and workflow template).
 */

/**
 * Validates extra_vars field is valid JSON object format.
 * Used in superRefine for both job template and workflow template schemas.
 */
export function validateExtraVars(
  extraVars: string | undefined,
  ctx: z.RefinementCtx,
  fieldPath: string[] = ['extra_vars']
): void {
  const v = extraVars?.trim()
  if (!v) return

  try {
    const parsed: unknown = JSON.parse(v)
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object') {
      ctx.addIssue({
        code: 'custom',
        path: fieldPath,
        message: 'Extra variables must be a JSON object',
      })
    }
  } catch {
    ctx.addIssue({
      code: 'custom',
      path: fieldPath,
      message: 'Invalid JSON format',
    })
  }
}

/**
 * Validates that a template ID is valid (positive integer).
 * Returns true if valid or undefined, false if invalid.
 */
export function isValidTemplateId(templateId: number | undefined): boolean {
  if (templateId === undefined) return true
  return Number.isInteger(templateId) && templateId > 0
}

/**
 * Checks if any of the provided field values contain AAP expression syntax.
 * Expression syntax: ${...} or {{...}}
 */
export function hasAnyExpressionValue(...values: (string | undefined)[]): boolean {
  return values.some((v) => {
    if (!v) return false
    const trimmed = v.trim()
    return trimmed.includes('${') || trimmed.includes('{{')
  })
}
