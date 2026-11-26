const CONFIGURATION_MESSAGES: Readonly<Record<string, string>> = {
  filter_invalid_expression: 'Enter a valid CEL expression that returns true or false',
  filter_invalid_syntax: 'Syntax error',
  filter_unsupported_variable: 'Use input as the message variable',
  filter_unsupported_function: 'This CEL function is not supported',
  filter_unsupported_construct: 'This CEL construct is not supported',
  filter_invalid_macro: 'Check the arguments to this CEL macro',
  filter_non_boolean: 'This expression must return true or false',
}

/** Only expose the backend's safe compiler categories and optional one-based location. */
export function filterConfigurationError(error: unknown): string | undefined {
  if (!error || typeof error !== 'object' || !('code' in error) || typeof error.code !== 'string') return
  if (!Object.hasOwn(CONFIGURATION_MESSAGES, error.code)) return
  const message = CONFIGURATION_MESSAGES[error.code]
  const line = 'line' in error && typeof error.line === 'number' && error.line > 0 ? error.line : undefined
  const column = 'column' in error && typeof error.column === 'number' && error.column > 0 ? error.column : undefined
  let location = ''
  if (line) location = ` at line ${line}${column ? `, column ${column}` : ''}`
  else if (column) location = ` at column ${column}`
  return `${message}${location}.`
}

export function filterEvaluationError(code?: string | null): string {
  switch (code ?? 'filter_evaluation_failed') {
    case 'filter_non_boolean':
      return 'This expression must return true or false. Update the expression and test again.'
    case 'filter_wrong_type':
      return 'A sample value has an incompatible type. Check the fields and operators used by the expression.'
    case 'filter_invalid_input':
      return 'This sample cannot be evaluated as input. Check its values and try again.'
    default:
      return 'The expression could not be evaluated for this sample. Check the expression and sample values, then try again.'
  }
}
