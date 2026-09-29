/** Validates inline `${...}` expression syntax in a plain-text field value. */
export function validateExpressionSyntax(value: string): string | null {
  if (!value.includes('${')) return null
  if (value.includes('${}')) return 'Invalid syntax'

  const expressionPattern = /\$\{([^}]*)\}/g
  let match: RegExpExecArray | null = expressionPattern.exec(value)
  while (match !== null) {
    const body = match[1]
    const openBrackets = (body.match(/\[/g) ?? []).length
    const closeBrackets = (body.match(/\]/g) ?? []).length
    if (openBrackets !== closeBrackets) return 'Invalid syntax'
    match = expressionPattern.exec(value)
  }

  const withoutMatched = value.replace(/\$\{[^}]*\}/g, '')
  if (withoutMatched.includes('${')) return 'Invalid syntax'

  return null
}
