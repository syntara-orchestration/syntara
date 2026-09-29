import { describe, expect, it } from 'vitest'

import {
  formatWorkflowLaunchRejection,
  getErrorCode,
  getErrorMessage,
  getErrorStatus,
  getErrorTitle,
  getValidationFieldErrors,
  isAdminConfigurationError,
  isConflictError,
  isRetryableError,
  isServiceUnavailableError,
  isValidationError,
  isWorkflowVersionConflictError,
  sanitizeUserFacingErrorText,
} from './apiErrors'

describe('apiErrors', () => {
  describe('workflow launch rejections', () => {
    it('lists every denied step in a launch error', () => {
      expect(
        formatWorkflowLaunchRejection({
          code: 'WORKFLOW_LAUNCH_REJECTED',
          reason: 'step_type_denied',
          denied_steps: [
            { kind: 'script', node_id: 'step-a', denied_by: 'deny-script' },
            { kind: 'http_request', node_id: 'step-b', denied_by: 'deny-http' },
          ],
        })
      ).toBe(
        'This workflow contains denied step types: script (step-a, deny-script); http_request (step-b, deny-http).'
      )
    })

    it('formats other rejection reasons inside API wrappers', () => {
      expect(getErrorMessage({ data: { code: 'WORKFLOW_LAUNCH_REJECTED', reason: 'execution_run_denied' } })).toBe(
        'You are not allowed to run this workflow.'
      )
      expect(formatWorkflowLaunchRejection('not json')).toBeNull()
    })
  })

  describe('sanitizeUserFacingErrorText', () => {
    it('strips angle-bracket segments resembling HTML tags', () => {
      expect(sanitizeUserFacingErrorText('<script></script>Safe text')).toBe('Safe text')
      expect(sanitizeUserFacingErrorText('before<img src=x>after')).toBe('beforeafter')
    })

    it('matches prior tag stripping for nested angle brackets (linear scan)', () => {
      expect(sanitizeUserFacingErrorText('<a<b>c>')).toBe('c>')
      expect(sanitizeUserFacingErrorText('x<a')).toBe('x<a')
    })

    it('removes NUL characters', () => {
      expect(sanitizeUserFacingErrorText('a\u0000b')).toBe('ab')
    })

    it('truncates to display max with ellipsis', () => {
      const long = 'z'.repeat(3000)
      const out = sanitizeUserFacingErrorText(long)
      expect(out.length).toBe(2000)
      expect(out.endsWith('…')).toBe(true)
    })

    it('returns empty string unchanged', () => {
      expect(sanitizeUserFacingErrorText('')).toBe('')
    })
  })

  describe('getErrorStatus', () => {
    it('extracts status from direct status field', () => {
      expect(getErrorStatus({ status: 404 })).toBe(404)
    })

    it('extracts status from statusCode field', () => {
      expect(getErrorStatus({ statusCode: 422 })).toBe(422)
    })

    it('extracts status from response.status (openapi-fetch)', () => {
      expect(getErrorStatus({ response: { status: 503 } })).toBe(503)
    })

    it('extracts status from cause wrapper', () => {
      expect(getErrorStatus({ cause: { status: 500 } })).toBe(500)
      expect(getErrorStatus({ cause: { statusCode: 502 } })).toBe(502)
    })

    it('extracts status from data wrapper', () => {
      expect(getErrorStatus({ data: { status: 401 } })).toBe(401)
      expect(getErrorStatus({ data: { statusCode: 403 } })).toBe(403)
    })

    it('returns undefined for non-objects', () => {
      expect(getErrorStatus(null)).toBeUndefined()
      expect(getErrorStatus(undefined)).toBeUndefined()
      expect(getErrorStatus('string')).toBeUndefined()
      expect(getErrorStatus(123)).toBeUndefined()
    })

    it('returns undefined when no status found', () => {
      expect(getErrorStatus({ detail: 'no status here' })).toBeUndefined()
    })
  })

  describe('isServiceUnavailableError', () => {
    it('returns true for status 503', () => {
      expect(isServiceUnavailableError({ status: 503 })).toBe(true)
      expect(isServiceUnavailableError({ statusCode: 503 })).toBe(true)
    })

    it('returns true for RFC 9457 service unavailable error codes', () => {
      expect(isServiceUnavailableError({ code: 'LLM_CONFIGURATION_ERROR' })).toBe(true)
      expect(isServiceUnavailableError({ code: 'TEMPORAL_UNAVAILABLE' })).toBe(true)
    })

    it('returns false for other errors', () => {
      expect(isServiceUnavailableError({ status: 404 })).toBe(false)
      expect(isServiceUnavailableError({ code: 'WORKFLOW_NOT_FOUND' })).toBe(false)
      expect(isServiceUnavailableError(null)).toBe(false)
      expect(isServiceUnavailableError(undefined)).toBe(false)
      expect(isServiceUnavailableError('error string')).toBe(false)
    })
  })

  describe('getErrorMessage', () => {
    it('extracts message from RFC 9457 detail field', () => {
      expect(getErrorMessage({ detail: 'Field "name" is required' })).toBe('Field "name" is required')
    })

    it('extracts message from RFC 9457 title as fallback', () => {
      expect(getErrorMessage({ title: 'Validation Error' })).toBe('Validation Error')
    })

    it('extracts message from cause (openapi-fetch format)', () => {
      expect(getErrorMessage({ cause: { detail: 'Cause message' } })).toBe('Cause message')
    })

    it('extracts message from FastAPI validation error detail arrays', () => {
      const validationError = {
        detail: [
          { loc: ['body', 'name'], msg: 'field required', type: 'value_error.missing' },
          { loc: ['body', 'age'], msg: 'value is not a valid integer', type: 'type_error.integer' },
        ],
      }
      expect(getErrorMessage(validationError)).toBe('name: field required; age: value is not a valid integer')
    })

    it('includes nested validation loc path when available', () => {
      const validationError = {
        detail: [{ loc: ['body', 'configuration', 'api_key'], msg: 'Field required', type: 'missing' }],
      }
      expect(getErrorMessage(validationError)).toBe('configuration.api_key: Field required')
    })

    it('returns string errors directly', () => {
      expect(getErrorMessage('String error')).toBe('String error')
    })

    it('returns fallback for null/undefined', () => {
      expect(getErrorMessage(null)).toBe('An unexpected error occurred')
      expect(getErrorMessage(undefined)).toBe('An unexpected error occurred')
    })

    it('returns fallback for non-object/non-string types', () => {
      expect(getErrorMessage(123)).toBe('An unexpected error occurred')
      expect(getErrorMessage(true)).toBe('An unexpected error occurred')
    })

    it('returns fallback for empty objects', () => {
      expect(getErrorMessage({})).toBe('An unexpected error occurred')
    })

    it('handles RFC 9457 503 error format from backend', () => {
      const rfc9457Error = {
        type: 'https://api.example.com/errors/configuration-error',
        title: 'Configuration Error',
        detail: 'OPENROUTER_API_KEY environment variable is required. Get your API key from https://openrouter.ai/keys',
        code: 'LLM_CONFIGURATION_ERROR',
        status: 503,
        retryable: true,
      }
      expect(getErrorMessage(rfc9457Error)).toBe(
        'OPENROUTER_API_KEY environment variable is required. Get your API key from https://openrouter.ai/keys'
      )
    })

    it('handles circular references without infinite recursion', () => {
      const circular: Record<string, unknown> = { detail: 'Top level error' }
      circular.cause = circular // Create circular reference

      // Should return the message from the top level before hitting the cycle
      expect(getErrorMessage(circular)).toBe('Top level error')
    })

    it('handles deeply nested circular references', () => {
      const error1: Record<string, unknown> = { detail: 'Error 1' }
      const error2: Record<string, unknown> = { cause: error1 }
      const error3: Record<string, unknown> = { data: error2 }
      error1.cause = error3 // Create cycle: error1 -> error3 -> error2 -> error1

      // Should traverse and find the detail message before hitting the cycle
      expect(getErrorMessage(error3)).toBe('Error 1')
    })

    it('handles circular reference with no extractable message', () => {
      const circular: Record<string, unknown> = { someField: 'not a message' }
      circular.cause = circular // Circular reference with no message

      // Should return fallback without infinite loop
      expect(getErrorMessage(circular)).toBe('An unexpected error occurred')
    })

    it('extracts message from native Error instances', () => {
      expect(getErrorMessage(new Error('Native error message'))).toBe('Native error message')
    })

    it('extracts message from data wrapper (WebSocket format)', () => {
      expect(getErrorMessage({ data: { detail: 'WS error detail' } })).toBe('WS error detail')
    })

    it('extracts message from validation items with message field', () => {
      expect(getErrorMessage({ detail: [{ message: 'field is invalid' }] })).toBe('field is invalid')
    })

    it('extracts message from validation items with detail field', () => {
      expect(getErrorMessage({ detail: [{ detail: 'item detail' }] })).toBe('item detail')
    })

    it('truncates many validation errors with count', () => {
      const manyErrors = {
        detail: [{ msg: 'Error 1' }, { msg: 'Error 2' }, { msg: 'Error 3' }, { msg: 'Error 4' }, { msg: 'Error 5' }],
      }
      expect(getErrorMessage(manyErrors)).toBe('Error 1; Error 2; Error 3 (+2 more)')
    })

    it('skips non-object and null items in validation detail array', () => {
      expect(getErrorMessage({ detail: [null, 42, 'text', { msg: 'valid' }] })).toBe('text; valid')
    })

    it('drops non-string/number loc parts', () => {
      const error = { detail: [{ loc: ['body', null, 'field'], msg: 'required' }] }
      expect(getErrorMessage(error)).toBe('field: required')
    })

    it('returns fallback for empty validation detail array', () => {
      expect(getErrorMessage({ detail: [] })).toBe('An unexpected error occurred')
    })

    it('returns fallback for validation items without extractable message', () => {
      expect(getErrorMessage({ detail: [{ loc: ['body', 'name'] }] })).toBe('An unexpected error occurred')
    })

    it('sanitizes reflected server text in detail (defense in depth)', () => {
      expect(getErrorMessage({ detail: '<b>oops</b>Please try again' })).toBe('oopsPlease try again')
    })

    it('truncates overlong detail strings for display', () => {
      const long = 'a'.repeat(3000)
      const result = getErrorMessage({ detail: long })
      expect(result.length).toBe(2000)
      expect(result.endsWith('…')).toBe(true)
    })
  })

  describe('getValidationFieldErrors', () => {
    it('extracts field errors from FastAPI detail arrays', () => {
      const validationError = {
        detail: [{ loc: ['body', 'configuration', 'api_key'], msg: 'Field required', type: 'missing' }],
      }
      expect(getValidationFieldErrors(validationError)).toEqual([
        { field: 'configuration.api_key', message: 'Field required' },
      ])
    })

    it('returns empty list when no detail array present', () => {
      expect(getValidationFieldErrors({ detail: 'nope' })).toEqual([])
      expect(getValidationFieldErrors(null)).toEqual([])
    })

    it('sanitizes field error messages from server', () => {
      const validationError = {
        detail: [{ loc: ['body', 'name'], msg: '<img>x</img>Invalid', type: 'value_error' }],
      }
      expect(getValidationFieldErrors(validationError)).toEqual([{ field: 'name', message: 'xInvalid' }])
    })
  })

  describe('getErrorCode', () => {
    it('extracts error code from RFC 9457 code field', () => {
      expect(getErrorCode({ code: 'VALIDATION_ERROR' })).toBe('VALIDATION_ERROR')
      expect(getErrorCode({ code: 'WORKFLOW_NOT_FOUND' })).toBe('WORKFLOW_NOT_FOUND')
    })

    it('extracts error code from openapi-fetch wrapper', () => {
      expect(getErrorCode({ cause: { code: 'INTERNAL_ERROR' } })).toBe('INTERNAL_ERROR')
    })

    it('extracts error code from data wrapper', () => {
      expect(getErrorCode({ data: { code: 'FILE_TOO_LARGE' } })).toBe('FILE_TOO_LARGE')
    })

    it('returns undefined for missing error code', () => {
      expect(getErrorCode({ detail: 'No code' })).toBeUndefined()
      expect(getErrorCode(null)).toBeUndefined()
      expect(getErrorCode(undefined)).toBeUndefined()
      expect(getErrorCode('string')).toBeUndefined()
    })
  })

  describe('getErrorTitle', () => {
    it('returns RFC 9457 explicit title when present', () => {
      expect(getErrorTitle({ title: 'Workflow Not Found' })).toBe('Workflow Not Found')
      expect(getErrorTitle({ title: 'Validation Error' })).toBe('Validation Error')
    })

    it('derives title from RFC 9457 error codes', () => {
      expect(getErrorTitle({ code: 'WORKFLOW_NAME_CONFLICT' })).toBe('Workflow Name Conflict')
      expect(getErrorTitle({ code: 'VALIDATION_ERROR' })).toBe('Validation Error')
      expect(getErrorTitle({ code: 'LLM_CONFIGURATION_ERROR' })).toBe('Configuration Error')
      expect(getErrorTitle({ code: 'FILE_TOO_LARGE' })).toBe('File Too Large')
    })

    it('prioritizes explicit title over derived title', () => {
      expect(getErrorTitle({ title: 'Custom Title', code: 'VALIDATION_ERROR' })).toBe('Custom Title')
    })

    it('extracts title from data wrapper', () => {
      expect(getErrorTitle({ data: { title: 'Data Title' } })).toBe('Data Title')
    })

    it('extracts title from cause wrapper', () => {
      expect(getErrorTitle({ cause: { title: 'Cause Title' } })).toBe('Cause Title')
    })

    it('sanitizes server-provided titles', () => {
      expect(getErrorTitle({ title: '<em>Bad</em>Title' })).toBe('BadTitle')
    })

    it('returns "Error" for unknown error codes', () => {
      expect(getErrorTitle({ code: 'UNKNOWN_CODE' })).toBe('Error')
      expect(getErrorTitle({ detail: 'No code' })).toBe('Error')
      expect(getErrorTitle(null)).toBe('Error')
    })
  })

  describe('isAdminConfigurationError', () => {
    it('returns true for 503 errors', () => {
      expect(isAdminConfigurationError({ status: 503 })).toBe(true)
      expect(isAdminConfigurationError({ code: 'LLM_CONFIGURATION_ERROR' })).toBe(true)
    })

    it('returns true for API key related messages', () => {
      expect(isAdminConfigurationError({ detail: 'OPENROUTER_API_KEY is required' })).toBe(true)
      expect(isAdminConfigurationError({ detail: 'Missing API key' })).toBe(true)
    })

    it('returns true for configuration related messages', () => {
      expect(isAdminConfigurationError({ detail: 'Service not configured properly' })).toBe(true)
      expect(isAdminConfigurationError({ detail: 'Environment variable missing' })).toBe(true)
    })

    it('returns false for regular errors', () => {
      expect(isAdminConfigurationError({ code: 'WORKFLOW_NOT_FOUND', detail: 'Resource not found' })).toBe(false)
      expect(isAdminConfigurationError({ detail: 'Validation failed' })).toBe(false)
    })
  })

  describe('isRetryableError', () => {
    it('returns true when retryable flag is true', () => {
      expect(isRetryableError({ retryable: true })).toBe(true)
    })

    it('returns false when retryable flag is false', () => {
      expect(isRetryableError({ retryable: false })).toBe(false)
    })

    it('returns true for 5xx errors by default', () => {
      expect(isRetryableError({ status: 500 })).toBe(true)
      expect(isRetryableError({ status: 503 })).toBe(true)
      expect(isRetryableError({ statusCode: 502 })).toBe(true)
    })

    it('returns false for 4xx errors by default', () => {
      expect(isRetryableError({ status: 400 })).toBe(false)
      expect(isRetryableError({ status: 404 })).toBe(false)
      expect(isRetryableError({ status: 422 })).toBe(false)
    })

    it('checks retryable in nested wrappers', () => {
      expect(isRetryableError({ data: { retryable: true } })).toBe(true)
      expect(isRetryableError({ cause: { retryable: false } })).toBe(false)
    })

    it('returns false for null/undefined/non-objects', () => {
      expect(isRetryableError(null)).toBe(false)
      expect(isRetryableError(undefined)).toBe(false)
      expect(isRetryableError('string')).toBe(false)
    })
  })

  describe('isConflictError', () => {
    it('returns true for 409 status code', () => {
      expect(isConflictError({ status: 409 })).toBe(true)
    })

    it('returns true for conflict error codes', () => {
      expect(isConflictError({ code: 'WORKFLOW_NAME_CONFLICT' })).toBe(true)
      expect(isConflictError({ code: 'PROVIDER_NAME_CONFLICT' })).toBe(true)
    })

    it('returns false for other errors', () => {
      expect(isConflictError({ status: 400 })).toBe(false)
      expect(isConflictError({ code: 'VALIDATION_ERROR' })).toBe(false)
      expect(isConflictError(null)).toBe(false)
    })
  })

  describe('isValidationError', () => {
    it('returns true for 422 status code', () => {
      expect(isValidationError({ status: 422 })).toBe(true)
    })

    it('returns true for validation error codes', () => {
      expect(isValidationError({ code: 'VALIDATION_ERROR' })).toBe(true)
      expect(isValidationError({ code: 'FILE_VALIDATION_ERROR' })).toBe(true)
      expect(isValidationError({ code: 'TOOL_VALIDATION_ERROR' })).toBe(true)
    })

    it('returns true for FastAPI detail arrays', () => {
      expect(isValidationError({ detail: [{ loc: ['body', 'name'], msg: 'required' }] })).toBe(true)
    })

    it('returns false for other errors', () => {
      expect(isValidationError({ status: 404 })).toBe(false)
      expect(isValidationError({ code: 'WORKFLOW_NOT_FOUND' })).toBe(false)
      expect(isValidationError(null)).toBe(false)
    })
  })

  describe('isWorkflowVersionConflictError', () => {
    it('returns true for WORKFLOW_VERSION_CONFLICT code', () => {
      expect(
        isWorkflowVersionConflictError({
          code: 'WORKFLOW_VERSION_CONFLICT',
          current_version: 5,
          expected_version: 3,
        })
      ).toBe(true)
    })

    it('returns false for other conflict codes', () => {
      expect(isWorkflowVersionConflictError({ code: 'WORKFLOW_NAME_CONFLICT' })).toBe(false)
    })

    it('returns false for non-object values', () => {
      expect(isWorkflowVersionConflictError(null)).toBe(false)
      expect(isWorkflowVersionConflictError(undefined)).toBe(false)
      expect(isWorkflowVersionConflictError('string')).toBe(false)
    })

    it('narrows the type to Record<string, unknown>', () => {
      const error: unknown = {
        code: 'WORKFLOW_VERSION_CONFLICT',
        current_version: 5,
        expected_version: 3,
        created_by_username: 'alice',
      }
      if (isWorkflowVersionConflictError(error)) {
        expect(error.current_version).toBe(5)
        expect(error.created_by_username).toBe('alice')
      }
    })
  })
})
