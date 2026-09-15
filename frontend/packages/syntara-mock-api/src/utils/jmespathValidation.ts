import jmespath from 'jmespath'

/**
 * Validate a JMESPath expression the same way the Syntara API does at configuration time.
 * Returns null when valid, or an error message when invalid.
 */
export function validateGroupJmespathExpression(expression: string | null | undefined): string | null {
  if (!expression) return null
  try {
    jmespath.compile(expression)
    return null
  } catch {
    return `Invalid group extraction expression: '${expression}' is not a valid JMESPath expression`
  }
}
