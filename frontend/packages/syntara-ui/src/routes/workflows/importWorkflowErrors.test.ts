import { describe, expect, it } from 'vitest'

import {
  IMPORT_DEFAULT_ERROR_MESSAGE,
  IMPORT_INVALID_FORMAT_MESSAGE,
  IMPORT_NAME_CONFLICT_MESSAGE,
  getImportWorkflowApiErrorMessage,
  getImportWorkflowFileErrorMessage,
} from './importWorkflowErrors'

describe('getImportWorkflowApiErrorMessage', () => {
  it('maps workflow name conflict to a friendly message', () => {
    expect(
      getImportWorkflowApiErrorMessage({
        code: 'WORKFLOW_NAME_CONFLICT',
        detail: 'Workflow with name "test" already exists in this project',
      })
    ).toBe(IMPORT_NAME_CONFLICT_MESSAGE)
  })

  it('maps workflow definition validation errors to invalid format message', () => {
    expect(
      getImportWorkflowApiErrorMessage({
        code: 'WORKFLOW_DEFINITION_INVALID',
        detail: 'The workflow definition failed validation',
      })
    ).toBe(IMPORT_INVALID_FORMAT_MESSAGE)
  })

  it('maps generic validation errors to invalid format message', () => {
    expect(
      getImportWorkflowApiErrorMessage({
        code: 'VALIDATION_ERROR',
        detail: 'The provided data failed validation requirements',
      })
    ).toBe(IMPORT_INVALID_FORMAT_MESSAGE)
  })

  it('maps file validation errors to invalid format message', () => {
    expect(
      getImportWorkflowApiErrorMessage({
        code: 'FILE_VALIDATION_ERROR',
        detail: 'Uploaded file failed validation',
      })
    ).toBe(IMPORT_INVALID_FORMAT_MESSAGE)
  })

  it('maps FastAPI validation detail arrays to invalid format message', () => {
    expect(
      getImportWorkflowApiErrorMessage({
        detail: [{ loc: ['body', 'workflow_definition'], msg: 'field required', type: 'missing' }],
      })
    ).toBe(IMPORT_INVALID_FORMAT_MESSAGE)
  })

  it('uses default message for unknown API errors without exposing raw detail', () => {
    expect(getImportWorkflowApiErrorMessage({ detail: 'Duplicate name' })).toBe(IMPORT_DEFAULT_ERROR_MESSAGE)
    expect(getImportWorkflowApiErrorMessage({ code: 'WORKFLOW_DEFINITION_WARNINGS', detail: 'has warnings' })).toBe(
      IMPORT_DEFAULT_ERROR_MESSAGE
    )
    expect(getImportWorkflowApiErrorMessage({ detail: 'Internal server error' })).toBe(IMPORT_DEFAULT_ERROR_MESSAGE)
  })
})

describe('getImportWorkflowFileErrorMessage', () => {
  it('preserves actionable parse error messages', () => {
    expect(getImportWorkflowFileErrorMessage(new SyntaxError('Unexpected token'))).toBe('Unexpected token')
    expect(getImportWorkflowFileErrorMessage(new Error('Unsupported schema version: "1.0.0". Expected 2.0.0'))).toBe(
      'Unsupported schema version: "1.0.0". Expected 2.0.0'
    )
  })

  it('falls back to invalid format message for non-error values', () => {
    expect(getImportWorkflowFileErrorMessage('not an error')).toBe(IMPORT_INVALID_FORMAT_MESSAGE)
    expect(getImportWorkflowFileErrorMessage(null)).toBe(IMPORT_INVALID_FORMAT_MESSAGE)
  })
})
