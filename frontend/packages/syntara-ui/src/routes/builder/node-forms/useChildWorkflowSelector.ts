import type { ProjectsAPI, WorkflowAPI } from '@syntara/contracts'
import { useInfiniteQuery, useQueries } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { workflowClient, workflowFetchClient } from '../../../client'
import { detachPromise } from '../../../utils/detachPromise'
import { accessFetchClient } from '../../access/accessClient'

const WORKFLOW_PAGE_SIZE = 20

type InvocationSchema = WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead']
type InvocationTrigger = WorkflowAPI.components['schemas']['WorkflowInvocationTriggerSchema']
type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']
type ProjectWorkflowListQuery = NonNullable<ProjectsAPI.operations['list_project_workflows']['parameters']['query']> & {
  is_enabled?: boolean
  'name[contains]'?: string
}

export type ChildWorkflowOption = {
  value: string
  label: string
  description?: string
  triggers: InvocationTrigger[]
}

type SchemaQueryResult = {
  data?: InvocationSchema
  error: unknown
  isError: boolean
  isPending: boolean
}

function workflowLabel(workflow: Workflow): string {
  const version = workflow.published_version_number
  return version == null ? workflow.name : `${workflow.name} (v${version})`
}

function buildWorkflowOptions(
  workflows: Workflow[],
  schemasByWorkflowId: ReadonlyMap<string, SchemaQueryResult | undefined>
): ChildWorkflowOption[] {
  return workflows.flatMap((workflow) => {
    const invocationSchema = schemasByWorkflowId.get(workflow.id)?.data
    if (!invocationSchema?.is_eligible || (invocationSchema.triggers ?? []).length === 0) return []

    return [
      {
        value: workflow.id,
        label: `${workflow.name} (v${invocationSchema.published_version})`,
        description: workflow.description ?? undefined,
        triggers: invocationSchema.triggers ?? [],
      },
    ]
  })
}

function selectedWorkflowOption({
  existingOption,
  workflowId,
  workflow,
  schema,
  label,
}: Readonly<{
  existingOption?: ChildWorkflowOption
  workflowId: string | null
  workflow?: Workflow
  schema?: InvocationSchema
  label?: string
}>): ChildWorkflowOption | undefined {
  if (existingOption) return existingOption
  if (!workflowId || !workflow || !schema?.is_eligible || (schema.triggers ?? []).length === 0) return undefined

  return {
    value: workflowId,
    label: label ?? workflow.name,
    description: workflow.description ?? undefined,
    triggers: schema.triggers ?? [],
  }
}

function getSchemaLookupState(
  schemasByWorkflowId: ReadonlyMap<string, SchemaQueryResult | undefined>,
  selectedWorkflowId: string | null
) {
  const entries = [...schemasByWorkflowId.entries()]
  const errors = entries.filter(([workflowId, query]) => {
    if (!query?.isError) return false
    if (workflowId !== selectedWorkflowId) return true
    return !isInvocationSchemaForbidden(query.error) && !isInvocationSchemaNotFound(query.error)
  })

  return {
    isLoading: entries.some(([, query]) => query?.isPending ?? false),
    hasError: errors.length > 0,
    hasPermissionError: errors.some(
      ([workflowId, query]) => workflowId !== selectedWorkflowId && isInvocationSchemaForbidden(query?.error)
    ),
    hasNotFoundError: errors.some(
      ([workflowId, query]) => workflowId !== selectedWorkflowId && isInvocationSchemaNotFound(query?.error)
    ),
    hasRetryableError: errors.some(
      ([, query]) =>
        query?.isError && !isInvocationSchemaForbidden(query.error) && !isInvocationSchemaNotFound(query.error)
    ),
  }
}

class ProjectWorkflowFetchError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`Failed to load project workflows (${status})`)
    this.name = 'ProjectWorkflowFetchError'
    this.status = status
  }
}

function getWorkflowErrorMessage({
  workflowsError,
  selectedWorkflowError,
  hasPermissionError,
  hasNotFoundError,
}: Readonly<{
  workflowsError: unknown
  selectedWorkflowError: boolean
  hasPermissionError: boolean
  hasNotFoundError: boolean
}>): string {
  if (workflowsError instanceof ProjectWorkflowFetchError && workflowsError.status === 403) {
    return 'You do not have permission to view workflows in this project.'
  }
  if (workflowsError) return 'Unable to load workflows.'
  if (selectedWorkflowError) return 'Unable to load the selected workflow name.'
  if (hasPermissionError) return 'Some workflows could not be checked because of permissions.'
  if (hasNotFoundError) return 'Some workflows are no longer published or eligible.'
  return 'Unable to verify some workflows.'
}

export class InvocationSchemaFetchError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`Failed to load child workflow invocation schema (${status})`)
    this.name = 'InvocationSchemaFetchError'
    this.status = status
  }
}

export function isInvocationSchemaForbidden(error: unknown): error is InvocationSchemaFetchError {
  return error instanceof InvocationSchemaFetchError && error.status === 403
}

export function isInvocationSchemaNotFound(error: unknown): error is InvocationSchemaFetchError {
  return error instanceof InvocationSchemaFetchError && error.status === 404
}

async function fetchInvocationSchema(workflowId: string): Promise<InvocationSchema> {
  const { data, error, response } = await workflowFetchClient.GET('/workflows/{workflow_id}/invocation_schema', {
    params: { path: { workflow_id: workflowId } },
  })

  if (error || !data) {
    throw new InvocationSchemaFetchError(response.status)
  }

  return data
}

function invocationSchemaQueryKey(workflowId: string) {
  return ['workflow-invocation-schema', workflowId] as const
}

/**
 * Fetch same-project workflows and their published invocation schemas.
 * Only workflows exposing at least one Subworkflow Trigger are selectable.
 */
export function useChildWorkflowSelector({
  projectId,
  selectedWorkflowId,
}: {
  projectId: string | null
  selectedWorkflowId: string | null
}) {
  const [searchTerm, setSearchTerm] = useState('')
  const nameFilter = searchTerm.trim()

  const workflowsQuery = useInfiniteQuery({
    queryKey: ['child-workflows', projectId, nameFilter],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const query: ProjectWorkflowListQuery = {
        limit: WORKFLOW_PAGE_SIZE,
        cursor: pageParam,
        sort: 'name',
        include_total: false,
        is_enabled: true,
        ...(nameFilter ? { 'name[contains]': nameFilter } : {}),
      }
      const { data, error, response } = await accessFetchClient.GET('/projects/{project_id}/workflows', {
        params: { path: { project_id: projectId ?? '' }, query },
      })

      if (error || !data) throw new ProjectWorkflowFetchError(response.status)
      return data
    },
    getNextPageParam: (lastPage) => lastPage.next ?? undefined,
    enabled: !!projectId,
    placeholderData: (previousData) => previousData,
  })

  const workflows = useMemo(
    () => workflowsQuery.data?.pages.flatMap((page) => page.resources ?? []) ?? [],
    [workflowsQuery.data]
  )

  const publishedWorkflows = useMemo(
    () => workflows.filter((workflow) => workflow.id && workflow.published_version_number != null),
    [workflows]
  )

  const workflowIds = useMemo(() => {
    const ids = publishedWorkflows.map((workflow) => workflow.id)
    if (selectedWorkflowId) ids.push(selectedWorkflowId)
    return [...new Set(ids)]
  }, [publishedWorkflows, selectedWorkflowId])

  const schemasByWorkflowId = useQueries({
    queries: workflowIds.map((workflowId) => ({
      queryKey: invocationSchemaQueryKey(workflowId),
      queryFn: () => fetchInvocationSchema(workflowId),
      enabled: !!projectId,
    })),
    combine: (results) => new Map(workflowIds.map((workflowId, index) => [workflowId, results[index]])),
  })

  const selectedWorkflowFromList = workflows.find((workflow) => workflow.id === selectedWorkflowId)
  const selectedWorkflowQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}',
    { params: { path: { workflow_id: selectedWorkflowId ?? '' } } },
    { enabled: !!projectId && !!selectedWorkflowId && !selectedWorkflowFromList }
  )

  const options = useMemo(
    () => buildWorkflowOptions(publishedWorkflows, schemasByWorkflowId),
    [publishedWorkflows, schemasByWorkflowId]
  )

  const selectedOption = options.find((option) => option.value === selectedWorkflowId)
  const selectedSchemaQuery = selectedWorkflowId ? schemasByWorkflowId.get(selectedWorkflowId) : undefined
  const selectedWorkflow = selectedWorkflowFromList ?? selectedWorkflowQuery.data
  const selectedWorkflowLabel = selectedWorkflow ? workflowLabel(selectedWorkflow) : undefined
  const selectedSchema = selectedSchemaQuery?.data
  const resolvedSelectedOption = selectedWorkflowOption({
    existingOption: selectedOption,
    workflowId: selectedWorkflowId,
    workflow: selectedWorkflow,
    schema: selectedSchema,
    label: selectedWorkflowLabel,
  })
  const schemaLookup = getSchemaLookupState(schemasByWorkflowId, selectedWorkflowId)
  const hasError = workflowsQuery.isError || selectedWorkflowQuery.isError || schemaLookup.hasError
  const errorMessage = getWorkflowErrorMessage({
    workflowsError: workflowsQuery.error,
    selectedWorkflowError: selectedWorkflowQuery.isError,
    hasPermissionError: schemaLookup.hasPermissionError,
    hasNotFoundError: schemaLookup.hasNotFoundError,
  })
  const errorVariant: 'danger' | 'warning' =
    workflowsQuery.isError || selectedWorkflowQuery.isError || schemaLookup.hasRetryableError ? 'danger' : 'warning'

  function retryFailedLookups(workflowId?: string) {
    if (projectId) detachPromise(workflowsQuery.refetch())
    if (selectedWorkflowQuery.isError) detachPromise(selectedWorkflowQuery.refetch())
    const queries = workflowId ? [schemasByWorkflowId.get(workflowId)] : [...schemasByWorkflowId.values()]
    for (const query of queries) {
      if (query) detachPromise(query.refetch())
    }
  }

  return {
    options,
    selectedOption: resolvedSelectedOption,
    selectedWorkflowLabel,
    selectedSchema,
    selectedSchemaQuery,
    selectedSchemaError: selectedSchemaQuery?.error,
    isLoading: workflowsQuery.isLoading || schemaLookup.isLoading,
    hasNextPage: workflowsQuery.hasNextPage,
    isFetchingNextPage: workflowsQuery.isFetchingNextPage,
    loadMoreWorkflows: () => {
      if (workflowsQuery.hasNextPage && !workflowsQuery.isFetchingNextPage) {
        detachPromise(workflowsQuery.fetchNextPage())
      }
    },
    hasError,
    errorMessage,
    errorVariant,
    retryFailedLookups,
    searchTerm,
    setSearchTerm,
  }
}

export type { InvocationTrigger }
