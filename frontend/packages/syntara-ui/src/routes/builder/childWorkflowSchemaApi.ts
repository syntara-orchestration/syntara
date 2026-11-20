import type { WorkflowAPI } from '@syntara/contracts'

import { workflowFetchClient } from '../../client'

export type InvocationSchema = WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead']
export type InvocationTrigger = WorkflowAPI.components['schemas']['WorkflowInvocationTriggerSchema']

export class ChildWorkflowSchemaFetchError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(`${message} (${status})`)
    this.name = 'ChildWorkflowSchemaFetchError'
    this.status = status
  }
}

export const invocationSchemaQueryKey = (workflowId: string) => ['workflow-invocation-schema', workflowId] as const

export async function fetchInvocationSchema(workflowId: string): Promise<InvocationSchema> {
  const { data, error, response } = await workflowFetchClient.GET('/workflows/{workflow_id}/invocation_schema', {
    params: { path: { workflow_id: workflowId } },
  })

  if (error || !data) {
    throw new ChildWorkflowSchemaFetchError('Failed to load child workflow invocation schema', response.status)
  }

  return data
}

export function isChildWorkflowAccessDenied(error: unknown): error is ChildWorkflowSchemaFetchError {
  return error instanceof ChildWorkflowSchemaFetchError && error.status === 403
}

export function isChildWorkflowNotFound(error: unknown): error is ChildWorkflowSchemaFetchError {
  return error instanceof ChildWorkflowSchemaFetchError && error.status === 404
}
