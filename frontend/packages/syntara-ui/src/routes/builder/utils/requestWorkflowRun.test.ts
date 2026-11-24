import { describe, expect, it, vi } from 'vitest'

import { requestWorkflowRun } from './requestWorkflowRun'

describe('requestWorkflowRun', () => {
  it('runs immediately when confirmation is skipped and no input is required', () => {
    const dispatch = vi.fn()
    const handleRunWorkflow = vi.fn()

    requestWorkflowRun({
      triggerIndex: 1,
      triggerNodeId: 'trigger-2',
      requiresInput: false,
      skipConfirmation: true,
      dispatch,
      handleRunWorkflow,
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_SELECTED_TRIGGER', payload: 1 })
    expect(handleRunWorkflow).toHaveBeenCalledWith(undefined, 'trigger-2')
    expect(dispatch).not.toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: true })
  })

  it('opens input confirmation when confirmation is skipped but input is required', () => {
    const dispatch = vi.fn()
    const handleRunWorkflow = vi.fn()

    requestWorkflowRun({
      triggerNodeId: 'trigger-1',
      requiresInput: true,
      skipConfirmation: true,
      dispatch,
      handleRunWorkflow,
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: true })
    expect(handleRunWorkflow).not.toHaveBeenCalled()
  })

  it('opens the confirmation dialog when the preference is not dismissed', () => {
    const dispatch = vi.fn()
    const handleRunWorkflow = vi.fn()

    requestWorkflowRun({
      triggerNodeId: 'trigger-1',
      requiresInput: false,
      skipConfirmation: false,
      dispatch,
      handleRunWorkflow,
    })

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: true })
    expect(handleRunWorkflow).not.toHaveBeenCalled()
  })
})
