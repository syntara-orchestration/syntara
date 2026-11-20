import { describe, expect, it } from 'vitest'

import {
  getWorkflowRunTriggerDetailsErrorMessage,
  WorkflowRunTriggerDetailsLoadError,
} from './workflowRunTriggerDetailsError'

describe('getWorkflowRunTriggerDetailsErrorMessage', () => {
  it('maps 404 to a deleted-workflow message', () => {
    expect(getWorkflowRunTriggerDetailsErrorMessage({ status: 404 })).toBe(
      'This workflow may have been deleted. Refresh the page and try again.'
    )
  })

  it('maps 403 to a permission message', () => {
    expect(getWorkflowRunTriggerDetailsErrorMessage({ status: 403 })).toBe(
      'You do not have permission to run this workflow.'
    )
  })

  it('uses a friendly default for other failures', () => {
    expect(getWorkflowRunTriggerDetailsErrorMessage(new Error('Network down'))).toBe(
      'Could not load trigger details for this workflow. Try again.'
    )
    expect(getWorkflowRunTriggerDetailsErrorMessage({ status: 500 })).toBe(
      'Could not load trigger details for this workflow. Try again.'
    )
  })

  it('reads status from WorkflowRunTriggerDetailsLoadError', () => {
    const error = new WorkflowRunTriggerDetailsLoadError(403)
    expect(getWorkflowRunTriggerDetailsErrorMessage(error)).toBe('You do not have permission to run this workflow.')
  })
})
