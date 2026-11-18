import { describe, expect, it } from 'vitest'

import { filterConfigurationError, filterEvaluationError } from './filterConfigurationError'

describe('safe CEL error messages', () => {
  it.each([
    ['filter_invalid_expression', 'Enter a valid CEL expression'],
    ['filter_invalid_syntax', 'Syntax error'],
    ['filter_unsupported_variable', 'Use input as the message variable'],
    ['filter_unsupported_function', 'This CEL function is not supported'],
    ['filter_unsupported_construct', 'This CEL construct is not supported'],
    ['filter_invalid_macro', 'Check the arguments'],
    ['filter_non_boolean', 'This expression must return true or false'],
  ])('humanizes %s and preserves its source location', (code, text) => {
    const message = filterConfigurationError({ code, line: 2, column: 5, detail: 'private source' })
    expect(message).toContain(text)
    expect(message).toContain('at line 2, column 5.')
    expect(message).not.toContain(code)
    expect(message).not.toContain('private source')
  })
  it.each([null, undefined, 'error', {}, { code: 'private-code' }, { code: 'toString' }])(
    'ignores unrecognized errors: %j',
    (error) => {
      expect(filterConfigurationError(error)).toBeUndefined()
    }
  )
  it('handles partial and absent locations', () => {
    expect(filterConfigurationError({ code: 'filter_invalid_syntax' })).toBe('Syntax error.')
    expect(filterConfigurationError({ code: 'filter_invalid_syntax', line: 1 })).toBe('Syntax error at line 1.')
    expect(filterConfigurationError({ code: 'filter_invalid_syntax', column: 7 })).toBe('Syntax error at column 7.')
  })
  it.each([
    ['filter_non_boolean', 'must return true or false'],
    ['filter_wrong_type', 'incompatible type'],
    ['filter_invalid_input', 'Check its values'],
    ['filter_evaluation_failed', 'could not be evaluated'],
    ['unknown-private-code', 'could not be evaluated'],
    [null, 'could not be evaluated'],
  ])('humanizes evaluation failures: %s', (code, expected) => {
    expect(filterEvaluationError(code)).toContain(expected)
    expect(filterEvaluationError(code)).not.toContain('filter_')
  })
})
