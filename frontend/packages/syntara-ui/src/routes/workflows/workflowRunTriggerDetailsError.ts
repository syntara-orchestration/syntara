import { getErrorStatus } from '../../utils/apiErrors'

export function getWorkflowRunTriggerDetailsErrorMessage(error: unknown): string {
  const status = getErrorStatus(error)
  if (status === 404) {
    return 'This workflow may have been deleted. Refresh the page and try again.'
  }
  if (status === 403) {
    return 'You do not have permission to run this workflow.'
  }
  return 'Could not load trigger details for this workflow. Try again.'
}

export class WorkflowRunTriggerDetailsLoadError extends Error {
  readonly status: number

  constructor(status: number) {
    super(getWorkflowRunTriggerDetailsErrorMessage({ status }))
    this.name = 'WorkflowRunTriggerDetailsLoadError'
    this.status = status
  }
}

type WorkflowFetchResult = {
  data?: unknown
  error?: unknown
  response: Response
}

export function assertWorkflowRunTriggerDetailsLoaded(result: WorkflowFetchResult): void {
  if (!result.error && result.data) {
    return
  }

  const status = (!result.response.ok ? result.response.status : undefined) ?? getErrorStatus(result.error) ?? 500

  throw new WorkflowRunTriggerDetailsLoadError(status)
}
