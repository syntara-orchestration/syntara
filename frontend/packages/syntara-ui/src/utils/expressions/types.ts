/**
 * Type definitions for the nested logical expressions builder
 *
 * Expressions are represented as a tree structure that can be serialized
 * to template strings in the format: ${expression}
 */

/**
 * Logical operators for combining conditions
 */
export type LogicalOperator = 'AND' | 'OR'

/**
 * Data type categories for operator selection
 */
export type OperatorCategory = 'number' | 'string' | 'array' | 'object' | 'boolean' | 'dateTime'

/**
 * Comparison operators for individual conditions
 * Note: != is supported for backward compatibility with existing workflows,
 * but the UI should use the negate property (NOT checkbox) instead.
 */
export type ComparisonOperator =
  // Number operators
  | '=='
  | '!=' // Kept for backward compatibility with existing workflows
  | '>'
  | '<'
  | '>='
  | '<='
  // String operators
  | 'contains'
  | 'startsWith'
  | 'endsWith'
  | 'matches'
  // Common operators (all types)
  | 'exists'
  | 'isEmpty'
  // Array operators
  | 'lengthEqualTo'
  | 'lengthGreaterThan'
  | 'lengthLessThan'

/**
 * A node in the expression tree - either a group or a condition
 */
export type ExpressionNode = ExpressionGroup | ExpressionCondition

/**
 * A group of expressions combined with a logical operator (AND/OR)
 *
 * Example: (trigger.age >= 18 AND trigger.score > 50)
 * Example with negation: !((trigger.age >= 18 AND trigger.score > 50))
 */
export type ExpressionGroup = {
  type: 'group'
  /** Unique identifier for React keys and path-based updates */
  id: string
  /** How to combine child expressions */
  operator: LogicalOperator
  /** Child expressions (conditions or nested groups) */
  children: ExpressionNode[]
  /** Whether to negate this group with NOT operator */
  negate?: boolean
}

/**
 * A single condition comparing a variable to a value
 *
 * Example: trigger.age >= 18
 * Example with negation: !(user.status == 'inactive')
 */
export type ExpressionCondition = {
  type: 'condition'
  /** Unique identifier for React keys and path-based updates */
  id: string
  /** Variable path (e.g., "trigger.age", "fetch_order.output.riskScore") */
  variable: string
  /** Comparison operator */
  operator: ComparisonOperator
  /** Value to compare against (stored as string, e.g., "18", "true", "'active'") */
  value: string
  /** Whether to negate this condition with NOT operator */
  negate?: boolean
}

/**
 * Root expression structure
 *
 * null indicates an empty expression (no conditions defined)
 */
export type Expression = {
  /** Root node of the expression tree, or null if empty */
  root: ExpressionNode | null
  /** Error message if parsing or normalization failed */
  error?: string
}
