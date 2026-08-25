/**
 * Parsing utilities for converting template strings to expression trees
 *
 * Parses ${...} template strings into internal expression tree representation.
 * Uses a simplified recursive descent parser for common cases.
 *
 * Limitations:
 * - No support for complex nested property access in values
 * - No support for function calls
 * - Falls back to returning null for unparseable expressions (raw mode)
 * - **CRITICAL: Variable names cannot contain operator keywords** (startsWith, endsWith, contains, etc.)
 *   The regex-based parser will incorrectly treat operator keywords inside variable names as the actual operator.
 *
 *   Example failure mode:
 *   ```
 *   parseExpression('${user.startsWith startsWith "admin"}')
 *   // Incorrectly parses as: variable="user.", operator="startsWith", value="startsWith \"admin\""
 *   // Expected: variable="user.startsWith", operator="startsWith", value="\"admin\""
 *   ```
 *
 *   Workarounds:
 *   - Avoid using operator keywords (startsWith, endsWith, contains, matches, exists, isEmpty, etc.) in variable names
 *   - Use alternative property names (e.g., `user.startsWithValue` instead of `user.startsWith`)
 *   - For complex cases, use raw mode (manual expression input) instead of the visual builder
 */

import { generateUUID, isUnaryOperator, SYMBOL_OPERATORS, WORD_OPERATORS } from './defaults'
import { normalizeBackendExpression } from './normalizer'
import type { Expression, ExpressionNode, ExpressionCondition, ComparisonOperator } from './types'

// Python operator detection regexes (hoisted to avoid recompilation on every parse)
const PYTHON_KEYWORDS_RE = /\b(and|or|not)\b/
// Matches both "value" in ${var} and ${needle} in ${haystack} patterns
const PYTHON_IN_OP_RE = /(?:['"][^'"]+['"]|\$\{[^}]+\})\s+(not\s+)?in\s+\$\{/

// Condition parsing regex (hoisted to avoid recompilation on recursive parseCondition calls)
const CONDITION_REGEX = new RegExp(String.raw`^(.+?)\s*(${[...SYMBOL_OPERATORS, ...WORD_OPERATORS].join('|')})\s*(.*)$`)

/**
 * Parse a template string to an expression tree
 *
 * Variable references are wrapped with ${...}, but the overall expression is not.
 *
 * @param templateString - Template string with wrapped variables: ${var} == value
 * @returns Expression tree or { root: null } if empty/unparseable
 *
 * @example
 * parseExpression('${trigger.age} >= 18')
 * // Returns: { root: { type: 'condition', variable: 'trigger.age', operator: '>=', value: '18' } }
 *
 * @example
 * parseExpression('${trigger.age} >= 18 && ${trigger.score} > 50')
 * // Returns: { root: { type: 'group', operator: 'AND', children: [...] } }
 *
 * @example
 * parseExpression('${trigger.enabled}')
 * // Returns: { root: null } - simple template reference, not parseable as condition
 */
export function parseExpression(templateString: string): Expression {
  // Handle empty input
  if (!templateString?.trim()) {
    return { root: null }
  }

  let trimmed = templateString.trim()

  if (!trimmed) {
    return { root: null }
  }

  // Check if expression uses Python operators (backend format)
  // If so, normalize to JavaScript operators before parsing
  // IMPORTANT: This normalization must happen BEFORE any parsing to ensure
  // all nested expressions are also normalized (parseNode doesn't normalize)
  // Note: Detects 'not' broadly (not just 'not (') to catch standalone usage like 'not ${x}'
  // Strip quoted strings before checking to avoid false positives on keywords in string values
  const withoutStrings = trimmed.replaceAll(/["'][^"']*["']/g, '')
  const hasPythonKeywords = PYTHON_KEYWORDS_RE.test(withoutStrings)
  const hasPythonInOperator = PYTHON_IN_OP_RE.test(trimmed)
  const hasPythonOps = hasPythonKeywords || hasPythonInOperator

  if (hasPythonOps) {
    try {
      trimmed = normalizeBackendExpression(trimmed)
    } catch (error) {
      // If normalization fails, return error instead of trying to parse
      return {
        root: null,
        error: `Failed to normalize Python-style expression: ${error instanceof Error ? error.message : String(error)}`,
      }
    }
  }

  // Try to parse as nested structure (no longer requires outer ${...} wrapper)
  // parseNode expects expressions with JavaScript operators (&&, ||, !)
  try {
    const root = parseNode(trimmed)
    return { root }
  } catch {
    // Fallback: return null and let raw editor handle it
    return { root: null }
  }
}

/**
 * Track string state while iterating through expression characters.
 * Handles quote boundaries and escape sequences.
 *
 * @returns Updated index (may skip escaped char) and whether we're still in a string
 */
function handleStringChar(
  char: string,
  nextChar: string | undefined,
  inString: string | null
): { skipNext: boolean; inString: string | null } {
  if (inString) {
    // Inside a string: check for escape or closing quote
    if (char === '\\' && nextChar) {
      return { skipNext: true, inString } // Skip escaped character
    }
    if (char === inString) {
      return { skipNext: false, inString: null } // Exit string
    }
    return { skipNext: false, inString } // Still in string
  }

  // Not in string: check if starting one
  if (char === '"' || char === "'") {
    return { skipNext: false, inString: char }
  }

  return { skipNext: false, inString: null }
}

/**
 * Check if removing outer parentheses would leave balanced parens.
 * Skips parentheses inside quoted strings to avoid false negatives.
 *
 * @param inner - String after removing outer parens
 * @returns true if parens are balanced (safe to strip outer parens)
 */
function areParensBalanced(inner: string): boolean {
  let depth = 0
  let inString: string | null = null

  for (let i = 0; i < inner.length; i++) {
    const char = inner[i]
    const nextChar = i + 1 < inner.length ? inner[i + 1] : undefined

    // Handle string boundaries and escapes
    const stringState = handleStringChar(char, nextChar, inString)
    inString = stringState.inString
    if (stringState.skipNext) {
      i++ // Skip the escaped character
      continue
    }
    if (inString) continue // Skip chars inside strings

    // Count parentheses (only outside strings)
    if (char === '(') {
      depth++
    } else if (char === ')') {
      depth--
      if (depth < 0) return false // Unmatched closing paren
    }
  }

  return depth === 0 // All parens matched
}

/**
 * Recursively parse an expression node
 *
 * @param expr - Expression string to parse
 * @returns ExpressionNode (group or condition)
 * @throws Error if expression is invalid
 */
export function parseNode(expr: string): ExpressionNode {
  expr = expr.trim()

  if (!expr) {
    throw new Error('Empty expression')
  }

  // Remove outer parentheses first if present AND they are matching pairs
  const parenMatch = /^\((.+)\)$/.exec(expr)
  if (parenMatch && areParensBalanced(parenMatch[1])) {
    return parseNode(parenMatch[1])
  }

  // Try to split by logical operators (outside parentheses)
  // Priority: OR has lower precedence than AND, so check OR first
  const orParts = splitByOperator(expr, '||')
  if (orParts.length > 1) {
    return {
      type: 'group',
      id: generateUUID(),
      operator: 'OR',
      children: orParts.map(parseNode),
    }
  }

  const andParts = splitByOperator(expr, '&&')
  if (andParts.length > 1) {
    return {
      type: 'group',
      id: generateUUID(),
      operator: 'AND',
      children: andParts.map(parseNode),
    }
  }

  // Handle NOT operator - applies to both conditions and groups
  // Supports both ! and not for backward compatibility
  // Examples: not (trigger.age >= 18) or !(trigger.age >= 18) for conditions
  //           not ((A && B)) or !((A && B)) for groups
  const negateMatch = /^(?:!|not)\s*\((.+)\)$/.exec(expr)
  if (negateMatch) {
    const inner = negateMatch[1]
    // Special case: !((...)) indicates a negated group with single child
    // This preserves structure for cases like !((!(c == d)))
    if (inner.startsWith('(') && inner.endsWith(')')) {
      // Parse the inner content as a potential group
      const innerNode = parseNode(inner)
      // If it's a single negated condition, wrap it in a group to preserve structure
      if (innerNode.type === 'condition' && innerNode.negate) {
        return {
          type: 'group',
          id: generateUUID(),
          operator: 'AND',
          children: [innerNode],
          negate: true,
        }
      }
    }
    const innerNode = parseNode(inner)
    // Apply negation to both conditions and groups
    return { ...innerNode, negate: true }
  }

  // Parse as condition: variable operator value
  return parseCondition(expr)
}

/**
 * Parse a condition expression
 *
 * Variables should be wrapped with ${...}, values should not be.
 *
 * @param expr - Condition string like "${trigger.age} >= 18" or "${name} contains admin"
 * @returns ExpressionCondition
 * @throws Error if not a valid condition
 */
function parseCondition(expr: string): ExpressionCondition {
  const conditionMatch = CONDITION_REGEX.exec(expr)

  if (!conditionMatch) {
    throw new Error(`Invalid condition: ${expr}`)
  }

  let variable = conditionMatch[1].trim()
  let operator = conditionMatch[2] as ComparisonOperator
  const value = conditionMatch[3].trim()

  // Unwrap variable from ${...} if present
  const varMatch = /^\$\{(.+)\}$/.exec(variable)
  if (varMatch) {
    variable = varMatch[1].trim()
  }

  // Convert negated operators to their positive form + negate flag
  // This provides backward compatibility while standardizing the UI representation
  // Old workflows with ${x} != y will parse and display as: x == y with NOT checkbox checked
  let negate = false
  if (operator === '!=') {
    operator = '=='
    negate = true
  }

  // Validate that unary operators don't have extra tokens
  if (isUnaryOperator(operator) && value.length > 0) {
    throw new Error(`Invalid condition: ${expr}`)
  }

  return {
    type: 'condition',
    id: generateUUID(),
    variable,
    operator,
    value,
    negate,
  }
}

/**
 * Split expression by operator, respecting parentheses
 *
 * @param expr - Expression to split
 * @param operator - Operator to split by ('&&' or '||')
 * @returns Array of parts (returns single-element array if no split occurred)
 *
 * @example
 * splitByOperator('a && b && c', '&&')
 * // Returns: ['a', 'b', 'c']
 *
 * @example
 * splitByOperator('a && (b || c)', '||')
 * // Returns: ['a && (b || c)'] - doesn't split because || is inside parentheses
 */
function pushTrimmedPart(parts: string[], fragment: string): void {
  const trimmed = fragment.trim()
  if (trimmed) {
    parts.push(trimmed)
  }
}

function indexAfterAsciiSpaces(expr: string, from: number): number {
  let j = from
  while (j < expr.length && expr[j] === ' ') {
    j++
  }
  return j
}

export function splitByOperator(expr: string, operator: string): string[] {
  if (!operator || operator.trim().length === 0) {
    throw new Error('splitByOperator: operator must be a non-empty string')
  }

  const parts: string[] = []
  let current = ''
  let depth = 0
  let i = 0

  while (i < expr.length) {
    const char = expr[i]

    if (char === '(') {
      depth++
      current += char
      i++
      continue
    }

    if (char === ')') {
      depth--
      current += char
      i++
      continue
    }

    if (depth === 0 && i + operator.length <= expr.length && expr.substring(i, i + operator.length) === operator) {
      pushTrimmedPart(parts, current)
      current = ''
      i += operator.length
      i = indexAfterAsciiSpaces(expr, i)
      continue
    }

    current += char
    i++
  }

  pushTrimmedPart(parts, current)

  return parts.length > 1 ? parts : [expr]
}
