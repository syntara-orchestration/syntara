const CONFIGURATION_CODES = new Set([
  'filter_invalid_expression',
  'filter_invalid_syntax',
  'filter_unsupported_variable',
  'filter_unsupported_function',
  'filter_unsupported_construct',
  'filter_invalid_macro',
  'filter_non_boolean',
])

/** Only expose the backend's safe compiler categories and optional one-based location. */
export function filterConfigurationError(error: unknown): string | undefined {
  if (!error || typeof error !== 'object' || !('code' in error) || typeof error.code !== 'string') return
  if (!CONFIGURATION_CODES.has(error.code)) return
  const line = 'line' in error && typeof error.line === 'number' ? ` · Line ${error.line}` : ''
  const column = 'column' in error && typeof error.column === 'number' ? `, column ${error.column}` : ''
  return `${error.code}${line}${column}`
}
