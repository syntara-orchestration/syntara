import type { Activity } from '@syntara/contracts'

import { generateUUID } from '../../../../utils/generateUUID'
import type { EdgeConnection } from '../../types/edge'

import { validateConditionConnections } from './rules/validateConditionConnections'
import { validateConvergeInputs } from './rules/validateConvergeInputs'
import { validateLoopNodes } from './rules/validateLoopNodes'
import { validateNoDanglingNodes } from './rules/validateNoDanglingNodes'
import { validateNoGenericNodes } from './rules/validateNoGenericNodes'
import { validateVariableReferences } from './rules/validateVariableReferences'
import type { ValidationContext, ValidationError, ValidationResult, ValidationRule } from './types'

/**
 * Validation rules that produce errors (block save)
 */
const ERROR_RULES: ValidationRule[] = [
  validateNoDanglingNodes,
  validateConditionConnections,
  validateConvergeInputs,
  validateLoopNodes,
  validateNoGenericNodes,
  validateVariableReferences,
]

/**
 * Validates a workflow before saving.
 *
 * This runs all validation rules and returns a comprehensive result
 * containing all errors and warnings found.
 *
 * Errors will block the save operation, while warnings are informational
 * and don't prevent saving.
 *
 * @param activities - Flat array of workflow activities
 * @param edges - Edge connections between activities
 * @returns Validation result with errors and warnings
 *
 * @example
 * ```typescript
 * const result = validateWorkflow(activities, edges)
 * if (!result.valid) {
 *   console.error('Validation failed:', result.errors)
 *   // Show errors to user, block save
 * } else if (result.warnings.length > 0) {
 *   console.warn('Validation warnings:', result.warnings)
 *   // Show warnings to user, allow save
 * } else {
 *   // Proceed with save
 * }
 * ```
 */
export function validateWorkflow(
  activities: Activity[],
  edges: EdgeConnection[],
  context?: ValidationContext
): ValidationResult {
  const errors: ValidationError[] = []
  const warnings: ValidationError[] = []

  // Run all error-level validation rules
  for (const rule of ERROR_RULES) {
    try {
      const ruleResults = rule(activities, edges, context)
      // Separate errors and warnings based on severity
      errors.push(...ruleResults.filter((e) => e.severity === 'error'))
      warnings.push(...ruleResults.filter((e) => e.severity === 'warning'))
    } catch (error) {
      // If a validation rule itself throws an error, catch it and report it
      // eslint-disable-next-line no-console
      console.error('Validation rule failed:', error)
      errors.push({
        id: `rule-error-${generateUUID()}`,
        severity: 'error',
        rule: 'internal',
        message: 'An internal validation error occurred. Please try again or contact support.',
      })
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  }
}
