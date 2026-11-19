import type { OutputFieldDef, WorkflowAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'

import { detachPromise } from '../../../../utils/detachPromise'
import {
  fetchInvocationSchema,
  invocationSchemaQueryKey,
  isChildWorkflowAccessDenied,
  isChildWorkflowNotFound,
} from '../../childWorkflowSchemaApi'
import { getDeclaredOutputFields } from '../utils/subWorkflowOutputSchema'

export type ChildWorkflowStepSchema = {
  id: string
  name: string
  type: string
  outputSchema: Record<string, unknown> | null
  outputFields: OutputFieldDef[] | null
}

function getSelectedTriggerNodeId(
  triggers: WorkflowAPI.components['schemas']['WorkflowInvocationTriggerSchema'][],
  requestedTriggerNodeId: string | null
): string | null {
  if (requestedTriggerNodeId)
    return triggers.some((trigger) => trigger.trigger_node_id === requestedTriggerNodeId)
      ? requestedTriggerNodeId
      : null
  return triggers.length === 1 ? (triggers[0]?.trigger_node_id ?? null) : null
}

function requiresTriggerSelection(
  triggers: WorkflowAPI.components['schemas']['WorkflowInvocationTriggerSchema'][],
  selectedTriggerNodeId: string | null
): boolean {
  return triggers.length > 1 && selectedTriggerNodeId === null
}

function buildChildStepSchemas(
  invocationSchema: WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead'] | undefined,
  selectedTriggerNodeId: string | null
): ChildWorkflowStepSchema[] {
  if (!invocationSchema || !selectedTriggerNodeId) return []

  const selectedTrigger = invocationSchema.triggers.find((trigger) => trigger.trigger_node_id === selectedTriggerNodeId)
  if (!selectedTrigger?.output_schema) return []

  return [
    {
      id: '__declared_outputs__',
      name: 'Declared Outputs',
      type: 'subworkflow_declared_outputs',
      outputSchema: selectedTrigger.output_schema,
      outputFields: getDeclaredOutputFields(selectedTrigger.output_schema),
    },
  ]
}

function useInvocationSchemaQuery(workflowId: string | null) {
  return useQuery({
    queryKey: invocationSchemaQueryKey(workflowId ?? ''),
    queryFn: () => fetchInvocationSchema(workflowId ?? ''),
    enabled: Boolean(workflowId),
  })
}

/** Fetches the selected child's published invocation schema and declared outputs. */
export function useChildWorkflowSchema({
  workflowId,
  triggerNodeId,
}: Readonly<{ workflowId: string | null; triggerNodeId: string | null }>) {
  const { data: invocationSchema, error, isFetching, refetch } = useInvocationSchemaQuery(workflowId)

  const eligibleTriggers = invocationSchema?.triggers ?? []
  const selectedTriggerNodeId = getSelectedTriggerNodeId(eligibleTriggers, triggerNodeId)
  const needsTriggerSelection = requiresTriggerSelection(eligibleTriggers, selectedTriggerNodeId)
  const isTriggerUnavailable = Boolean(triggerNodeId && selectedTriggerNodeId === null)
  const childSteps = useMemo(
    () => buildChildStepSchemas(invocationSchema, selectedTriggerNodeId),
    [invocationSchema, selectedTriggerNodeId]
  )
  const retry = useCallback(() => detachPromise(refetch()), [refetch])

  return {
    invocationSchema: invocationSchema ?? null,
    publishedVersionId: invocationSchema?.published_version_id ?? null,
    publishedVersion: invocationSchema?.published_version ?? null,
    selectedTriggerNodeId,
    needsTriggerSelection,
    isTriggerUnavailable,
    childSteps,
    isLoading: Boolean(workflowId) && isFetching,
    error,
    isAccessDenied: isChildWorkflowAccessDenied(error),
    isNotFound: isChildWorkflowNotFound(error),
    isEligible: invocationSchema?.is_eligible ?? false,
    retry,
  }
}
