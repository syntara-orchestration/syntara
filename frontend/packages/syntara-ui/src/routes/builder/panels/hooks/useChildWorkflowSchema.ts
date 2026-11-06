import { getNodeOutputSchema, type OutputFieldDef, type WorkflowAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'

import { detachPromise } from '../../../../utils/detachPromise'
import {
  ChildWorkflowSchemaFetchError,
  childWorkflowDetailQueryKey,
  childWorkflowVersionQueryKey,
  fetchChildWorkflowDetail,
  fetchChildWorkflowVersion,
  fetchInvocationSchema,
  invocationSchemaQueryKey,
  isChildWorkflowAccessDenied,
  isChildWorkflowNotFound,
} from '../../childWorkflowSchemaApi'

type ChildWorkflowStepNode = { id: string; name?: string | null; type: string }
type ChildWorkflowGraph = {
  triggers: Array<{ id: string; type: string }>
  nodes: ChildWorkflowStepNode[]
  edges: Array<{ from: string; to: string }>
}

export type ChildWorkflowStepSchema = {
  id: string
  name: string
  type: string
  outputSchema: Record<string, unknown> | null
  outputFields: OutputFieldDef[] | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseChildWorkflowGraph(value: unknown): ChildWorkflowGraph | null {
  if (
    !isRecord(value) ||
    !Array.isArray(value['triggers']) ||
    !Array.isArray(value['nodes']) ||
    !Array.isArray(value['edges'])
  ) {
    return null
  }

  const triggers = value['triggers'].flatMap((trigger) =>
    isRecord(trigger) && typeof trigger['id'] === 'string' && typeof trigger['type'] === 'string'
      ? [{ id: trigger['id'], type: trigger['type'] }]
      : []
  )
  const nodes = value['nodes'].flatMap((node) =>
    isRecord(node) && typeof node['id'] === 'string' && typeof node['type'] === 'string'
      ? [
          {
            id: node['id'],
            name: typeof node['name'] === 'string' ? node['name'] : null,
            type: node['type'],
          },
        ]
      : []
  )
  const edges = value['edges'].flatMap((edge) =>
    isRecord(edge) && typeof edge['from'] === 'string' && typeof edge['to'] === 'string'
      ? [{ from: edge['from'], to: edge['to'] }]
      : []
  )

  return { triggers, nodes, edges }
}

function getReachableStepIds(definition: ChildWorkflowGraph, triggerNodeId: string): Set<string> {
  const outgoingEdges = new Map<string, string[]>()
  for (const edge of definition.edges) {
    const successors = outgoingEdges.get(edge.from) ?? []
    successors.push(edge.to)
    outgoingEdges.set(edge.from, successors)
  }

  const reachable = new Set<string>()
  const pending = [...(outgoingEdges.get(triggerNodeId) ?? [])]
  while (pending.length > 0) {
    const stepId = pending.pop()
    if (!stepId || reachable.has(stepId)) continue
    reachable.add(stepId)
    pending.push(...(outgoingEdges.get(stepId) ?? []))
  }
  return reachable
}

function getTerminalStepIds(definition: ChildWorkflowGraph): Set<string> {
  const stepsWithSuccessors = new Set(definition.edges.map((edge) => edge.from))
  return new Set(definition.nodes.filter((step) => !stepsWithSuccessors.has(step.id)).map((step) => step.id))
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

function shouldLoadPublishedDefinition(
  workflowId: string | null,
  invocationSchema: WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead'] | undefined,
  selectedTriggerNodeId: string | null
): boolean {
  return Boolean(
    workflowId &&
    invocationSchema?.is_eligible &&
    selectedTriggerNodeId &&
    invocationSchema.published_version_id &&
    invocationSchema.published_version != null
  )
}

function isSelectedTriggerUnavailable(
  requestedTriggerNodeId: string | null,
  selectedTriggerNodeId: string | null,
  childGraph: ChildWorkflowGraph | null
): boolean {
  if (requestedTriggerNodeId && selectedTriggerNodeId === null) return true
  return Boolean(
    selectedTriggerNodeId && childGraph && !childGraph.triggers.some((trigger) => trigger.id === selectedTriggerNodeId)
  )
}

function buildChildStepSchemas(
  definition: ChildWorkflowGraph | null,
  selectedTriggerNodeId: string | null,
  stepMetadata: WorkflowAPI.components['schemas']['WorkflowStepMetadataRead'][] | null
): ChildWorkflowStepSchema[] {
  if (
    !definition ||
    !selectedTriggerNodeId ||
    !definition.triggers.some((trigger) => trigger.id === selectedTriggerNodeId)
  ) {
    return []
  }

  const reachableStepIds = getReachableStepIds(definition, selectedTriggerNodeId)
  const terminalStepIds = getTerminalStepIds(definition)
  const stepMetadataById = new Map((stepMetadata ?? []).map((step) => [step.id, step]))
  return definition.nodes
    .filter((step) => reachableStepIds.has(step.id) && terminalStepIds.has(step.id))
    .map((step) => {
      const metadata = stepMetadataById.get(step.id)
      const outputSchema = metadata?.output_schema ?? null
      return {
        id: step.id,
        name: step.name?.trim() || step.id,
        type: step.type,
        outputSchema,
        outputFields: outputSchema ? getNodeOutputSchema(step.type) : null,
      }
    })
}

function useInvocationSchemaQuery(workflowId: string | null) {
  return useQuery({
    queryKey: invocationSchemaQueryKey(workflowId ?? ''),
    queryFn: () => fetchInvocationSchema(workflowId ?? ''),
    enabled: Boolean(workflowId),
  })
}

function usePublishedWorkflowMetadataQueries(
  workflowId: string | null,
  invocationSchema: WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead'] | undefined,
  selectedTriggerNodeId: string | null
) {
  const publishedVersionId = invocationSchema?.published_version_id ?? null
  const publishedVersion = invocationSchema?.published_version ?? null
  const shouldLoadDefinition = shouldLoadPublishedDefinition(workflowId, invocationSchema, selectedTriggerNodeId)
  const {
    data: publishedVersionRead,
    error: publishedVersionError,
    isFetching: isFetchingPublishedVersion,
    refetch: refetchPublishedVersion,
  } = useQuery({
    queryKey: childWorkflowVersionQueryKey(workflowId ?? '', publishedVersionId ?? '', publishedVersion ?? 0),
    queryFn: () => fetchChildWorkflowVersion(workflowId ?? '', publishedVersion ?? 0),
    enabled: shouldLoadDefinition,
    staleTime: 5 * 60 * 1000,
  })
  const {
    data: workflowDetail,
    error: workflowDetailError,
    isFetching: isFetchingWorkflowDetail,
    refetch: refetchWorkflowDetail,
  } = useQuery({
    queryKey: childWorkflowDetailQueryKey(workflowId ?? '', publishedVersionId ?? ''),
    queryFn: () => fetchChildWorkflowDetail(workflowId ?? ''),
    enabled: shouldLoadDefinition,
    staleTime: 5 * 60 * 1000,
  })

  return {
    publishedVersionId,
    publishedVersion,
    shouldLoadDefinition,
    publishedVersionRead,
    publishedVersionError,
    isFetchingPublishedVersion,
    refetchPublishedVersion,
    workflowDetail,
    workflowDetailError,
    isFetchingWorkflowDetail,
    refetchWorkflowDetail,
  }
}

function getPublishedStepMetadata(
  workflowDetail: WorkflowAPI.components['schemas']['WorkflowDetailRead'] | undefined,
  publishedVersionId: string | null
): WorkflowAPI.components['schemas']['WorkflowStepMetadataRead'][] | null {
  return workflowDetail?.published_step_metadata?.version_id === publishedVersionId
    ? workflowDetail.published_step_metadata.steps
    : null
}

function isSchemaLoading({
  workflowId,
  isFetchingInvocationSchema,
  shouldLoadDefinition,
  isFetchingPublishedVersion,
  isFetchingWorkflowDetail,
}: Readonly<{
  workflowId: string | null
  isFetchingInvocationSchema: boolean
  shouldLoadDefinition: boolean
  isFetchingPublishedVersion: boolean
  isFetchingWorkflowDetail: boolean
}>): boolean {
  return (
    Boolean(workflowId) &&
    (isFetchingInvocationSchema || (shouldLoadDefinition && (isFetchingPublishedVersion || isFetchingWorkflowDetail)))
  )
}

/**
 * Fetches the selected child's invocation schema and its exact published graph.
 * The version detail is cached by workflow and published-version ID so a new
 * publication cannot reuse step metadata from the previous version.
 */
export function useChildWorkflowSchema({
  workflowId,
  triggerNodeId,
}: Readonly<{ workflowId: string | null; triggerNodeId: string | null }>) {
  const {
    data: invocationSchema,
    error: invocationSchemaError,
    isFetching: isFetchingInvocationSchema,
    refetch: refetchInvocationSchema,
  } = useInvocationSchemaQuery(workflowId)

  const eligibleTriggers = invocationSchema?.triggers ?? []
  const selectedTriggerNodeId = getSelectedTriggerNodeId(eligibleTriggers, triggerNodeId)
  const publishedWorkflowMetadata = usePublishedWorkflowMetadataQueries(
    workflowId,
    invocationSchema,
    selectedTriggerNodeId
  )
  const {
    publishedVersionId,
    publishedVersion,
    shouldLoadDefinition,
    publishedVersionRead,
    publishedVersionError,
    isFetchingPublishedVersion,
    refetchPublishedVersion,
    workflowDetail,
    workflowDetailError,
    isFetchingWorkflowDetail,
    refetchWorkflowDetail,
  } = publishedWorkflowMetadata

  const needsTriggerSelection = requiresTriggerSelection(eligibleTriggers, selectedTriggerNodeId)
  const workflowDefinition = publishedVersionRead?.workflow_definition
  const childGraph = useMemo(() => parseChildWorkflowGraph(workflowDefinition), [workflowDefinition])
  const publishedStepMetadata = getPublishedStepMetadata(workflowDetail, publishedVersionId)
  const childSteps = useMemo(
    () => buildChildStepSchemas(childGraph, selectedTriggerNodeId, publishedStepMetadata),
    [childGraph, publishedStepMetadata, selectedTriggerNodeId]
  )

  const error = invocationSchemaError ?? workflowDetailError ?? publishedVersionError
  const isTriggerUnavailable = isSelectedTriggerUnavailable(triggerNodeId, selectedTriggerNodeId, childGraph)
  const retry = useCallback(() => {
    detachPromise(refetchInvocationSchema())
    if (invocationSchema) {
      detachPromise(refetchPublishedVersion())
      detachPromise(refetchWorkflowDetail())
    }
  }, [invocationSchema, refetchInvocationSchema, refetchPublishedVersion, refetchWorkflowDetail])

  return {
    invocationSchema: invocationSchema ?? null,
    publishedVersionId,
    publishedVersion: publishedVersion ?? null,
    selectedTriggerNodeId,
    needsTriggerSelection,
    isTriggerUnavailable,
    childSteps,
    isLoading: isSchemaLoading({
      workflowId,
      isFetchingInvocationSchema,
      shouldLoadDefinition,
      isFetchingPublishedVersion,
      isFetchingWorkflowDetail,
    }),
    error,
    isAccessDenied: isChildWorkflowAccessDenied(error),
    isNotFound: isChildWorkflowNotFound(error),
    isEligible: invocationSchema?.is_eligible ?? false,
    retry,
  }
}

export { ChildWorkflowSchemaFetchError }
