import { describe, expect, it } from 'vitest'

import {
  WORKFLOW_START_DEFAULT_TITLE,
  WORKFLOW_START_NOT_PUBLISHED_DESCRIPTION,
  WORKFLOW_START_NOT_PUBLISHED_TITLE,
  WORKFLOW_START_SERVICE_UNAVAILABLE_DESCRIPTION,
  WORKFLOW_START_SERVICE_UNAVAILABLE_TITLE,
  getWorkflowStartErrorAlert,
} from './workflowStartErrors'

describe('getWorkflowStartErrorAlert', () => {
  it('maps WORKFLOW_NOT_PUBLISHED to the not-published alert', () => {
    expect(
      getWorkflowStartErrorAlert(
        {
          code: 'WORKFLOW_NOT_PUBLISHED',
          detail: 'The requested workflow has no published version',
          status: 400,
        },
        'Test Workflow'
      )
    ).toEqual({
      title: WORKFLOW_START_NOT_PUBLISHED_TITLE,
      description: WORKFLOW_START_NOT_PUBLISHED_DESCRIPTION,
    })
  })

  it('maps 503 to the service unavailable alert without Temporal jargon', () => {
    expect(getWorkflowStartErrorAlert({ status: 503, detail: 'Unavailable' }, 'Test Workflow')).toEqual({
      title: WORKFLOW_START_SERVICE_UNAVAILABLE_TITLE,
      description: WORKFLOW_START_SERVICE_UNAVAILABLE_DESCRIPTION,
    })
  })

  it('maps TEMPORAL_UNAVAILABLE to the service unavailable alert without Temporal jargon', () => {
    expect(
      getWorkflowStartErrorAlert({ code: 'TEMPORAL_UNAVAILABLE', detail: 'Worker down' }, 'Test Workflow')
    ).toEqual({
      title: WORKFLOW_START_SERVICE_UNAVAILABLE_TITLE,
      description: WORKFLOW_START_SERVICE_UNAVAILABLE_DESCRIPTION,
    })
  })

  it('uses the default alert for other errors without exposing raw detail', () => {
    expect(
      getWorkflowStartErrorAlert({ status: 500, detail: 'Internal server error with stack' }, 'My Workflow')
    ).toEqual({
      title: WORKFLOW_START_DEFAULT_TITLE,
      description:
        'Could not start workflow "My Workflow". Try again, or contact your administrator if this continues.',
    })
  })
})
