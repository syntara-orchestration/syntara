import { getErrorCode, isServiceUnavailableError } from '../../utils/apiErrors'

export const WORKFLOW_START_NOT_PUBLISHED_TITLE = 'Workflow not published'
export const WORKFLOW_START_NOT_PUBLISHED_DESCRIPTION = 'Publish this workflow before running it.'

export const WORKFLOW_START_SERVICE_UNAVAILABLE_TITLE = 'Service unavailable'
export const WORKFLOW_START_SERVICE_UNAVAILABLE_DESCRIPTION =
  'The workflow service is temporarily unavailable. Try again in a few minutes.'

export const WORKFLOW_START_DEFAULT_TITLE = 'Failed to run workflow'

/** User-facing alert when creating an execution (Run) fails. */
export function getWorkflowStartErrorAlert(
  error: unknown,
  workflowName: string
): { title: string; description: string } {
  if (getErrorCode(error) === 'WORKFLOW_NOT_PUBLISHED') {
    return {
      title: WORKFLOW_START_NOT_PUBLISHED_TITLE,
      description: WORKFLOW_START_NOT_PUBLISHED_DESCRIPTION,
    }
  }

  if (isServiceUnavailableError(error)) {
    return {
      title: WORKFLOW_START_SERVICE_UNAVAILABLE_TITLE,
      description: WORKFLOW_START_SERVICE_UNAVAILABLE_DESCRIPTION,
    }
  }

  return {
    title: WORKFLOW_START_DEFAULT_TITLE,
    description: `Could not start workflow "${workflowName}". Try again, or contact your administrator if this continues.`,
  }
}
