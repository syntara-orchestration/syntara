import type { WorkflowAPI } from '@syntara/contracts'

import { workflowFetchClient } from '../../client'

export type InvocationSchema = WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead']
export type InvocationTrigger = WorkflowAPI.components['schemas']['WorkflowInvocationTriggerSchema']
export type ChildWorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

export class ChildWorkflowSchemaFetchError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(`${message} (${status})`)
    this.name = 'ChildWorkflowSchemaFetchError'
    this.status = status
  }
}

export const invocationSchemaQueryKey = (workflowId: string) => ['workflow-invocation-schema', workflowId] as const

export const childWorkflowVersionQueryKey = (
  workflowId: string,
  publishedVersionId: string,
  publishedVersion: number
) => ['child-workflow-version', workflowId, publishedVersionId, publishedVersion] as const

export async function fetchInvocationSchema(workflowId: string): Promise<InvocationSchema> {
  const { data, error, response } = await workflowFetchClient.GET('/workflows/{workflow_id}/invocation_schema', {
    params: { path: { workflow_id: workflowId } },
  })

  if (error || !data) {
    throw new ChildWorkflowSchemaFetchError('Failed to load child workflow invocation schema', response.status)
  }

  return data
}

export async function fetchChildWorkflowVersion(
  workflowId: string,
  publishedVersion: number
): Promise<ChildWorkflowVersion> {
  const { data, error, response } = await workflowFetchClient.GET('/workflows/{workflow_id}/versions/{version}', {
    params: { path: { workflow_id: workflowId, version: publishedVersion } },
  })

  if (error || !data) {
    throw new ChildWorkflowSchemaFetchError('Failed to load the published child workflow definition', response.status)
  }

  return data
}

export function isChildWorkflowAccessDenied(error: unknown): error is ChildWorkflowSchemaFetchError {
  return error instanceof ChildWorkflowSchemaFetchError && error.status === 403
}

export function isChildWorkflowNotFound(error: unknown): error is ChildWorkflowSchemaFetchError {
  return error instanceof ChildWorkflowSchemaFetchError && error.status === 404
}
