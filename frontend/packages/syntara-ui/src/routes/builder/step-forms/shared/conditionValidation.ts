import { ALL_OPERATORS } from '../../../../utils/expressions/defaults'
import { parseExpression } from '../../../../utils/expressions/parser'
import { hasValidationErrors } from '../../../../utils/expressions/validation'

const UNARY_WORD_OPERATORS = new Set(['exists', 'isEmpty'])

// Literal validation regexes (hoisted to avoid recompilation)
const SINGLE_TEMPLATE_RE = /^\$\{[^\s}]+\}$/
const QUOTED_STRING_RE = /^["'][^"']*["']$/
const BOOLEAN_RE = /^(true|false)$/i
const NUMBER_RE = /^-?\d+(\.\d+)?$/

// Operator pattern regexes (hoisted to avoid recompilation on each validation)
const allOpsPattern = [...ALL_OPERATORS, '===', '!=='].join('|')
const TRAILING_OP_RE = new RegExp(String.raw`(${allOpsPattern})\s*$`)
const LEADING_OP_RE = new RegExp(String.raw`^\s*(${allOpsPattern})`)

/**
 * True when `exists` / `isEmpty` appears with both a left-hand token and a
 * trailing token (invalid unary-with-value). Implemented without nested
 * quantifier regexes to avoid ReDoS (Sonar S5852).
 */
function hasUnaryOperatorWithDisallowedValue(content: string): boolean {
  const tokens = content.split(/\s+/).filter((t) => t.length > 0)
  for (let i = 0; i < tokens.length; i++) {
    if (!UNARY_WORD_OPERATORS.has(tokens[i])) continue
    if (i > 0 && i < tokens.length - 1) return true
  }
  return false
}

/**
 * Check if content is a valid single-token literal form
 * (template, quoted string, boolean, or number).
 * Uses early return to avoid running remaining regex tests once a match is found.
 */
function isValidSingleTokenLiteral(content: string): boolean {
  return (
    SINGLE_TEMPLATE_RE.test(content) ||
    QUOTED_STRING_RE.test(content) ||
    BOOLEAN_RE.test(content) ||
    NUMBER_RE.test(content)
  )
}

/**
 * Validate fallback (unparsed) expression content
 * Returns error message or true if valid
 */
function validateFallbackContent(content: string): string | true {
  if (!content.length) {
    return 'Please fill in all required fields (Field and Value for each condition)'
  }

  // Check for invalid unary operator usage
  if (hasUnaryOperatorWithDisallowedValue(content)) {
    return 'Operators "exists" and "isEmpty" do not take a value. Remove the value after the operator.'
  }

  // Reject incomplete logical operators or parentheses
  if (/[&|!()]/.test(content)) {
    return 'Please fill in all required fields (Field and Value for each condition)'
  }

  // Reject trailing comparison operators
  if (TRAILING_OP_RE.test(content)) {
    return 'Please fill in all required fields (Field and Value for each condition)'
  }

  // Reject leading comparison operators
  if (LEADING_OP_RE.test(content)) {
    return 'Please fill in all required fields (Field and Value for each condition)'
  }

  // Reject empty template ${} or malformed templates
  if (/^\$\{\s*\}$/.test(content)) {
    return 'Please fill in all required fields (Field and Value for each condition)'
  }

  // Reject Python logical operators
  if (/\b(and|or)\b/.test(content) || /\bnot\s+/.test(content)) {
    return 'Please fill in all required fields (Field and Value for each condition)'
  }

  // Reject multi-token expressions with unquoted spaces
  const hasMultipleTokens = /\s+/.test(content) && !/^["'][^"']*["']$/.test(content)
  if (hasMultipleTokens && !isValidSingleTokenLiteral(content)) {
    return 'Please fill in all required fields (Field and Value for each condition)'
  }

  return true
}

/**
 * Shared validation rules for conditional expression fields.
 *
 * Used in:
 * - Condition nodes (main condition field)
 * - While loops (loop condition field)
 *
 * Ensures expression:
 * 1. Is not empty
 * 2. Parses correctly with valid expression tree (variables are wrapped with ${...}, but entire expression is not)
 */
export const conditionValidationRules = {
  required: 'Condition is required',
  validate: (value: string | undefined) => {
    if (!value?.trim()) return 'Condition cannot be empty'

    // Parse and validate the expression tree
    // Note: Individual variable references should be wrapped with ${...}, but the entire expression should not
    // Examples: "${trigger.status} == 'success'", "${count} > 5 && ${enabled}"
    const parsed = parseExpression(value)

    // If parsing failed (root is null), check if it's an allowed literal form
    if (!parsed.root) {
      const content = value.trim()
      const validationResult = validateFallbackContent(content)

      if (validationResult !== true) {
        return validationResult
      }

      // If we get here, it's likely a simple template reference or literal that didn't parse
      // This is allowed for cases like: ${running}, ${user.isActive}, ${true}
    }

    // If parsing succeeded, check for incomplete fields
    if (parsed.root && hasValidationErrors(parsed.root)) {
      return 'Please fill in all required fields (Field and Value for each condition)'
    }

    return true
  },
}
