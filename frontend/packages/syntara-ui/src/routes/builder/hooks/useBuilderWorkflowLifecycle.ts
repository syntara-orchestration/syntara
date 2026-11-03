import type { WorkflowAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, type Dispatch } from 'react'

import { workflowClient } from '../../../client'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { detachPromise } from '../../../utils/detachPromise'
import type { BuilderAction } from '../builderReducer'
import type { EdgeConnection } from '../types/edge'
import { processExistingWorkflow } from '../utils/processExistingWorkflow'
import { WORKFLOWS_LIST_PARAMS_FOR_DEFAULT_NAME } from '../utils/workflowListQuery'
import { DEFAULT_WORKFLOW_NAME, getNextDefaultWorkflowName } from '../utils/workflowNaming'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']

export function useBuilderWorkflowLifecycle(options: {
  workflowId: string | null
  isNew: boolean
  workflow: WorkflowWithVersion | undefined
  workflowName: string
  initialViewVersion?: number | null
  workflowsListResources: { name: string }[] | undefined
  workflowsListDataUndefined: boolean
  workflowsListIsPending: boolean
  workflowsListError: unknown
  dispatch: Dispatch<BuilderAction>
  setWorkflow: (def: WorkflowDefinition | null) => void
  setStoredEdges: (edges: EdgeConnection[]) => void
  loadWorkflowWithEdges: (
    def: WorkflowDefinition,
    edges: EdgeConnection[],
    nodePositions?: Record<string, { x: number; y: number }>,
    projectId?: string | null
  ) => void
}): void {
  const {
    workflowId,
    isNew,
    workflow,
    workflowName,
    initialViewVersion,
    workflowsListResources,
    workflowsListDataUndefined,
    workflowsListIsPending,
    workflowsListError,
    dispatch,
    setWorkflow,
    setStoredEdges,
    loadWorkflowWithEdges,
  } = options

  const queryClient = useQueryClient()

  const hasLoadedRef = useRef(false)
  /** Start null so the first mount after leaving the builder always clears stale store data. */
  const prevWorkflowIdRef = useRef<string | null>(null)
  const hasInitedNewWorkflowRef = useRef(false)
  const hasAppliedDefaultNameRef = useRef(false)
  const hasRefetchedWorkflowsOnceRef = useRef(false)

  useEffect(() => {
    if (prevWorkflowIdRef.current !== workflowId) {
      setWorkflow(null)
      setStoredEdges([])
      hasLoadedRef.current = false
      hasInitedNewWorkflowRef.current = false
      hasAppliedDefaultNameRef.current = false
      hasRefetchedWorkflowsOnceRef.current = false
      prevWorkflowIdRef.current = workflowId
    }
  }, [workflowId, setWorkflow, setStoredEdges])

  useEffect(() => {
    if (isNew) {
      if (hasInitedNewWorkflowRef.current) return
      hasInitedNewWorkflowRef.current = true
      const resources = workflowsListResources ?? []
      const defaultName = getNextDefaultWorkflowName(resources)
      const newWorkflow: WorkflowDefinition = {
        schema_version: '2.0.0',
        name: defaultName,
        description: 'New workflow',
        workflow: {
          activities: [],
        },
      }
      queueMicrotask(() => {
        loadWorkflowWithEdges(newWorkflow, [])
        dispatch({
          type: 'INIT_WORKFLOW',
          payload: { name: defaultName, description: 'New workflow' },
        })
      })
    } else if (workflow?.version?.workflow_definition && !hasLoadedRef.current && workflow.id === workflowId) {
      const { flattenedWorkflow, generatedEdges, nodePositions, initPayload } = processExistingWorkflow(workflow)

      queueMicrotask(() => {
        loadWorkflowWithEdges(flattenedWorkflow, generatedEdges, nodePositions, workflow.project_id ?? null)
        dispatch({ type: 'INIT_WORKFLOW', payload: { ...initPayload, initialViewVersion } })
        hasLoadedRef.current = true
      })
    }
  }, [isNew, workflow, workflowId, loadWorkflowWithEdges, workflowsListResources, dispatch, initialViewVersion])

  useEffect(() => {
    if (!workflow || isNew || hasLoadedRef.current || workflow.id !== workflowId) {
      return
    }
    queueMicrotask(() => {
      if (hasLoadedRef.current) {
        return
      }
      dispatch({
        type: 'INIT_WORKFLOW',
        payload: {
          name: workflow.name,
          description: workflow.description ?? workflow.name ?? DEFAULT_WORKFLOW_NAME,
        },
      })
    })
  }, [workflow, workflowId, isNew, dispatch])

  useEffect(() => {
    if (!isNew) return
    if (workflowsListResources === undefined) return
    if (workflowName !== DEFAULT_WORKFLOW_NAME) return
    if (hasAppliedDefaultNameRef.current) return
    const nextName = getNextDefaultWorkflowName(workflowsListResources)
    if (nextName === DEFAULT_WORKFLOW_NAME) return
    hasAppliedDefaultNameRef.current = true
    dispatch({ type: 'SET_WORKFLOW_NAME', payload: nextName })
  }, [isNew, workflowsListResources, workflowName, dispatch])

  useEffect(() => {
    if (!isNew) return
    if (!workflowsListDataUndefined) return
    if (workflowsListIsPending) return
    if (workflowsListError) return
    if (hasRefetchedWorkflowsOnceRef.current) return
    hasRefetchedWorkflowsOnceRef.current = true
    detachPromise(
      queryClient.refetchQueries({
        queryKey: workflowClient.queryOptions('get', '/workflows', WORKFLOWS_LIST_PARAMS_FOR_DEFAULT_NAME).queryKey,
      })
    )
  }, [isNew, queryClient, workflowsListDataUndefined, workflowsListIsPending, workflowsListError])
}
