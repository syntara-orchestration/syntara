/**
 * Serialization utilities for converting expression trees to template strings
 *
 * Converts internal expression tree representation to ${...} template strings
 * that are compatible with the workflow engine backend.
 */

import { isUnaryOperator } from './defaults'
import type { Expression, ExpressionNode, ExpressionCondition, ExpressionGroup } from './types'

/**
 * Serialize an expression tree to a template string
 *
 * Variable references are wrapped with ${...}, but the overall expression is not.
 *
 * @param expression - Expression tree to serialize
 * @param options - Serialization options
 * @param options.forBackend - If true, use 'not' for Python backend. If false (default), use '!' for UI display
 * @returns Template string with variables wrapped: ${var} == value, or empty string if no root
 *
 * @example
 * serializeExpression({
 *   root: {
 *     type: 'condition',
 *     variable: 'trigger.age',
 *     operator: '>=',
 *     value: '18'
 *   }
 * })
 * // Returns: "${trigger.age} >= 18" (NOT "${trigger.age >= 18}")
 *
 * @example
 * // With negation for UI display (default)
 * serializeExpression({ root: { ...condition, negate: true } })
 * // Returns: "!(${trigger.age} >= 18)"
 *
 * @example
 * // With negation for backend
 * serializeExpression({ root: { ...condition, negate: true } }, { forBackend: true })
 * // Returns: "not (${trigger.age} >= 18)"
 */
export function serializeExpression(expression: Expression, options?: { forBackend?: boolean }): string {
  if (!expression.root) {
    return ''
  }

  const result = serializeNode(expression.root, options?.forBackend ?? false)

  // Return empty string if serialization results in empty content
  if (!result?.trim()) {
    return ''
  }

  return result
}

/**
 * Recursively serialize an expression node to a string
 *
 * @param node - Node to serialize (condition or group)
 * @param forBackend - If true, use 'not' for Python backend. If false, use '!' for UI display
 * @returns String representation of the node
 */
function serializeNode(node: ExpressionNode, forBackend: boolean, isNested = false): string {
  if (node.type === 'condition') {
    return serializeCondition(node, forBackend)
  }

  return serializeGroup(node, forBackend, isNested)
}

/**
 * Auto-quote a value for Python compatibility if needed.
 * Only quotes if the value is not already quoted, not a number, not a boolean, and not a variable reference.
 *
 * @param value - Value to potentially quote
 * @returns Quoted value if needed, original otherwise
 */
function quoteValueIfNeeded(value: string): string {
  // Don't quote variable references - they should remain as template expressions
  const isVariable = value.startsWith('${') && value.endsWith('}')
  if (isVariable) return value

  const isQuoted = (value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))
  // Guard against empty string: Number('') returns 0, not NaN
  const isNumber = value.length > 0 && !Number.isNaN(Number(value))
  // Case-insensitive match for true/false (i flag handles True/False)
  const isBoolean = /^(true|false)$/i.test(value)

  if (!isQuoted && !isNumber && !isBoolean) {
    // Escape backslashes and double quotes before wrapping in Python string literal
    // Use replaceAll for reliability (replaces all occurrences, not just first)
    // NOSONAR: Runtime escaping of user input for Python strings, not source code literals
    const escaped = value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')
    return `"${escaped}"`
  }
  return value
}

/**
 * Serialize a condition node to a string
 *
 * Variable references are wrapped with ${...}, literals are not.
 *
 * @param condition - Condition to serialize
 * @param forBackend - If true, use 'not' for Python backend. If false, use '!' for UI display
 * @returns String like "${variable} operator value" or "!(${variable} operator value)"
 *
 * @example
 * serializeCondition({
 *   type: 'condition',
 *   variable: 'trigger.age',
 *   operator: '>=',
 *   value: '18',
 *   negate: false
 * })
 * // Returns: "${trigger.age} >= 18" (variable wrapped, value not wrapped)
 *
 * @example
 * serializeCondition({
 *   type: 'condition',
 *   variable: 'user.status',
 *   operator: '==',
 *   value: 'inactive',
 *   negate: true
 * }, false)
 * // Returns: "!(${user.status} == inactive)" (UI display - default)
 *
 * @example
 * serializeCondition({
 *   type: 'condition',
 *   variable: 'user.status',
 *   operator: '==',
 *   value: 'inactive',
 *   negate: true
 * }, true)
 * // Returns: "not (${user.status} == inactive)" (backend mode)
 *
 * @example
 * serializeCondition({
 *   type: 'condition',
 *   variable: 'data',
 *   operator: 'isEmpty',
 *   value: '',
 *   negate: false
 * })
 * // Returns: "${data} isEmpty"
 *
 * @example
 * serializeCondition({
 *   type: 'condition',
 *   variable: 'message.text',
 *   operator: 'contains',
 *   value: 'Hello',
 *   negate: false
 * }, true)
 * // Returns: "\"Hello\" in ${message.text}" (backend mode - reversed for Python 'in' operator)
 */
function serializeCondition(condition: ExpressionCondition, forBackend: boolean): string {
  // Skip if variable is missing
  if (!condition.variable.trim()) {
    return ''
  }

  // Check if this is a unary operator (using shared helper from defaults.ts)
  const isUnary = isUnaryOperator(condition.operator)

  // For binary operators, skip if value is missing
  if (!isUnary && !condition.value.trim()) {
    return ''
  }

  // Wrap variable reference with ${...} if not already wrapped
  const alreadyWrapped = condition.variable.startsWith('${') && condition.variable.endsWith('}')
  const wrappedVariable = alreadyWrapped ? condition.variable : `\${${condition.variable}}`

  // Auto-quote value if needed for Python compatibility
  const serializedValue = !isUnary && condition.value ? quoteValueIfNeeded(condition.value) : condition.value

  // Transform 'contains' to Python 'in' operator when serializing for backend
  // Note: Python's 'in' operator has reversed operand order (value in container)
  let base: string
  if (forBackend && condition.operator === 'contains') {
    // For backend: "value" in ${container}
    base = `${serializedValue} in ${wrappedVariable}`
  } else if (isUnary) {
    base = `${wrappedVariable} ${condition.operator}`
  } else {
    base = `${wrappedVariable} ${condition.operator} ${serializedValue}`
  }

  // Handle negation
  if (!condition.negate) {
    return base
  }

  // For backend with 'contains', use 'not in' instead of 'not (...in...)'
  if (forBackend && condition.operator === 'contains') {
    return `${serializedValue} not in ${wrappedVariable}`
  }

  // Use '!' for UI display, 'not' for backend mode
  const negatePrefix = forBackend ? 'not ' : '!'
  return `${negatePrefix}(${base})`
}

/**
 * Serialize a group node to a string
 *
 * @param group - Group to serialize
 * @param forBackend - If true, use 'not' for Python backend. If false, use '!' for UI display
 * @returns String with children joined by operator, wrapped in parentheses if needed
 *
 * @example
 * serializeGroup({
 *   type: 'group',
 *   operator: 'AND',
 *   children: [
 *     { type: 'condition', variable: 'trigger.age', operator: '>=', value: '18' },
 *     { type: 'condition', variable: 'trigger.score', operator: '>', value: '50' }
 *   ]
 * })
 * // Returns: "(trigger.age >= 18 && trigger.score > 50)"
 *
 * @example
 * serializeGroup({
 *   type: 'group',
 *   operator: 'AND',
 *   negate: true,
 *   children: [...]
 * }, false)
 * // Returns: "!((trigger.age >= 18 && trigger.score > 50))" (UI display - default)
 *
 * @example
 * serializeGroup({
 *   type: 'group',
 *   operator: 'AND',
 *   negate: true,
 *   children: [...]
 * }, true)
 * // Returns: "not ((trigger.age >= 18 && trigger.score > 50))" (backend mode)
 */
function serializeSingleChild(
  result: string,
  negatePrefix: string,
  isGroupNegated: boolean,
  isChildNegated: boolean,
  isNested: boolean
): string {
  if ((isGroupNegated && isChildNegated) || (isNested && isGroupNegated)) {
    return `${negatePrefix}((${result}))`
  }
  if (isNested) {
    return `(${result})`
  }
  return isGroupNegated ? `${negatePrefix}(${result})` : result
}

function serializeGroup(group: ExpressionGroup, forBackend: boolean, isNested = false): string {
  let operatorSymbol: string
  if (group.operator === 'AND') {
    operatorSymbol = forBackend ? 'and' : '&&'
  } else {
    operatorSymbol = forBackend ? 'or' : '||'
  }

  const childExpressions = group.children
    .map((node) => serializeNode(node, forBackend, true))
    .filter((expr) => expr.trim() !== '')

  if (childExpressions.length === 0) {
    return ''
  }

  const negatePrefix = forBackend ? 'not ' : '!'

  if (childExpressions.length === 1) {
    return serializeSingleChild(childExpressions[0], negatePrefix, !!group.negate, !!group.children[0].negate, isNested)
  }

  const separator = ` ${operatorSymbol} `
  const result = `(${childExpressions.join(separator)})`
  return group.negate ? `${negatePrefix}(${result})` : result
}
