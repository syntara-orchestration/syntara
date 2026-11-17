import { describe, expect, it, vi, beforeEach } from 'vitest'

import { FormDataValidationError, parseFormDefinition } from '../../../forms'

import { submitFormTriggerExecution } from './submitFormTriggerExecution'

const mockPost = vi.hoisted(() => vi.fn())

vi.mock('../../../client', () => ({
  executionsFetchClient: {
    POST: mockPost,
  },
}))

describe('submitFormTriggerExecution', () => {
  const definition = parseFormDefinition({
    fields: [{ type: 'text', value_name: 'reason', label: 'Reason', required: true }],
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns execution id on success', async () => {
    mockPost.mockResolvedValue({ data: { id: 'exec-99' }, error: undefined })
    await expect(
      submitFormTriggerExecution({
        workflowId: 'wf-1',
        triggerNodeId: 'form-1',
        inputData: { reason: 'ok' },
        formDefinition: definition,
        usePublished: true,
      })
    ).resolves.toBe('exec-99')
  })

  it('throws FormDataValidationError for FORM_VALIDATION_ERROR responses', async () => {
    mockPost.mockResolvedValue({
      data: undefined,
      error: {
        code: 'FORM_VALIDATION_ERROR',
        detail: 'Form validation failed: reason: This field is required',
      },
    })

    await expect(
      submitFormTriggerExecution({
        workflowId: 'wf-1',
        triggerNodeId: 'form-1',
        inputData: {},
        formDefinition: definition,
      })
    ).rejects.toBeInstanceOf(FormDataValidationError)
  })
})
