import type { Activity } from '@syntara/contracts'

import type { EdgeConnection } from '../../types/edge'

/**
 * Severity levels for validation issues
 */
export type ValidationSeverity = 'error' | 'warning' | 'info'

/**
 * A validation error or warning
 */
export type ValidationError = {
  /** Unique identifier for this error */
  id: string
  /** Severity level */
  severity: ValidationSeverity
  /** Human-readable error message */
  message: string
  /** ID of affected node (for highlighting) */
  nodeId?: string
  /** IDs of multiple affected nodes */
  nodeIds?: string[]
  /** ID of affected edge */
  edgeId?: string
  /** Name of the validation rule that triggered this error */
  rule: string
  /** Optional suggestion for how to fix the issue */
  suggestion?: string
}

/**
 * Result of workflow validation
 */
export type ValidationResult = {
  /** True if workflow is valid (no errors) */
  valid: boolean
  /** All errors found (block save) */
  errors: ValidationError[]
  /** All warnings found (don't block save) */
  warnings: ValidationError[]
}

/**
 * Additional context passed to validation rules that need workflow-level data.
 */
export type ValidationContext = {
  /** Trigger nodes — their parameters.input_schema defines valid ${trigger.*} references */
  triggers?: Activity[]
}

/**
 * A validation rule function
 */
export type ValidationRule = (
  activities: Activity[],
  edges: EdgeConnection[],
  context?: ValidationContext
) => ValidationError[]
