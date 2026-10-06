import type { FormsAPI } from '@syntara/contracts'
import { useCallback, useEffect, useRef, useState } from 'react'

import { FlowNodeType } from '../../../constants'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import type { WorkflowDefShape } from '../../builder/useActivityNameMap'
import { ACTIVITY_STATUS } from '../../builder/utils/executionState/executionHelpers'
import { latestActivityStateForCanvasNode } from '../../workflows/execution/utils/activityState'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'
import {
  canvasNodeIdFromPromptNodeId,
  findFormPromptIndexForLookupKeys,
  resolveFormPromptLookupKeys,
} from '../formPrompt/formPromptNodeId'
import { normalizeFormPromptNavigationList } from '../formPrompt/sortFormPromptsForNavigation'

import type { ExecutionNode } from './useExecutionApprovals'
import { useFetchFormPromptsForExecution } from './useFetchFormPromptsForExecution'

type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']

const LIST_RETRY_DELAY_MS = 600
const LIST_RETRY_ATTEMPTS = 4

async function fetchFormPromptsWithRetry(
  nodeId: string,
  attempt: number,
  fetchFormPromptsForExecution: () => Promise<FormPromptSummary[]>
): Promise<FormPromptSummary[]> {
  const fetched = await fetchFormPromptsForExecution()
  if (fetched.length > 0) {
    return fetched
  }
  const shouldRetry = attempt < LIST_RETRY_ATTEMPTS - 1 && isCanvasNodeWaitingForPrompt(nodeId)
  if (!shouldRetry) {
    return fetched
  }
  await sleep(LIST_RETRY_DELAY_MS)
  return fetchFormPromptsWithRetry(nodeId, attempt + 1, fetchFormPromptsForExecution)
}

export function isFormPromptNode(node: ExecutionNode): boolean {
  return node.type === FlowNodeType.FORM_PROMPT
}

export function isWaitingFormPromptNode(node: ExecutionNode): boolean {
  if (node.type !== FlowNodeType.FORM_PROMPT) return false
  const executionState = node.data.__executionState
  if (!executionState || typeof executionState !== 'object') return false
  const status = 'status' in executionState ? executionState.status : undefined
  return status === ACTIVITY_STATUS.WAITING
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function isCanvasNodeWaitingForPrompt(nodeId: string): boolean {
  const activityStates = useExecutionStore.getState().activityStates
  const lookupKeys = resolveFormPromptLookupKeys(nodeId, activityStates)
  for (const key of lookupKeys) {
    const direct = activityStates.get(key)
    if (direct?.status === ACTIVITY_STATUS.WAITING) return true
    const canvasId = canvasNodeIdFromPromptNodeId(key)
    const latest = latestActivityStateForCanvasNode(activityStates, canvasId)
    if (latest?.status === ACTIVITY_STATUS.WAITING) return true
  }
  return false
}

function formPromptNotFoundDescription(fetchedCount: number, nodeId: string): string {
  if (fetchedCount > 0) {
    return 'This form prompt has been resolved or is no longer available for this step.'
  }
  if (isCanvasNodeWaitingForPrompt(nodeId)) {
    return 'The form prompt is still being created for this step. Wait a moment and try again.'
  }
  return 'No form prompt was recorded for this step on this run.'
}

type UseExecutionFormPromptsResult = {
  formPrompts: FormPromptSummary[]
  currentIndex: number
  currentFormPrompt: FormPromptSummary | null
  isLoading: boolean
  handleNodeClick: (event: React.MouseEvent, node: ExecutionNode) => void
  handleActivityRowClick: (canvasNodeId: string) => void
  navigateToIndex: (index: number) => void
  clearFormPrompts: () => void
  setFormPromptsAndIndex: (prompts: FormPromptSummary[], index: number) => void
  fetchFormPrompts: () => Promise<FormPromptSummary[]>
  fetchPendingFormPrompts: () => Promise<FormPromptSummary[]>
}

export function useExecutionFormPrompts(
  executionId: string | undefined,
  workflowDefinition?: WorkflowDefShape
): UseExecutionFormPromptsResult {
  const [formPrompts, setFormPrompts] = useState<FormPromptSummary[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const {
    fetchPendingFormPrompts: fetchPendingFromApi,
    fetchFormPromptsForExecution,
    clear,
    isLoading,
  } = useFetchFormPromptsForExecution(executionId ?? '')
  const { showInfo, showError } = useAlerts()
  const executionIdRef = useRef(executionId)
  const latestNodeIdRef = useRef<string | null>(null)
  const lastFetchErrorKeyRef = useRef<string | null>(null)
  const [trackedExecutionId, setTrackedExecutionId] = useState(executionId)

  const currentFormPrompt = formPrompts[currentIndex] ?? null

  const applyNavigationList = useCallback(
    (prompts: FormPromptSummary[], selectedPromptId?: string) => {
      const { sorted, index } = normalizeFormPromptNavigationList(
        prompts,
        selectedPromptId,
        workflowDefinition,
        useExecutionStore.getState().activityStates
      )
      setFormPrompts(sorted)
      setCurrentIndex(index)
      return sorted
    },
    [workflowDefinition]
  )

  if (trackedExecutionId !== executionId) {
    setTrackedExecutionId(executionId)
    setFormPrompts([])
    setCurrentIndex(0)
  }

  useEffect(() => {
    if (executionIdRef.current !== executionId) {
      latestNodeIdRef.current = null
      lastFetchErrorKeyRef.current = null
    }
    executionIdRef.current = executionId
  }, [executionId])

  useEffect(() => {
    clear()
  }, [executionId, clear])

  const fetchPromptsForNodeWithRetry = useCallback(
    (nodeId: string): Promise<FormPromptSummary[]> =>
      fetchFormPromptsWithRetry(nodeId, 0, fetchFormPromptsForExecution),
    [fetchFormPromptsForExecution]
  )

  const loadPromptsForNode = useCallback(
    (nodeId: string, notFoundTitle: string) => {
      latestNodeIdRef.current = nodeId
      const capturedExecutionId = executionIdRef.current
      if (!capturedExecutionId) {
        showError({
          title: 'Failed to load form prompt',
          description: 'Execution is not available yet. Refresh the page and try again.',
        })
        return
      }

      const lookupKeys = resolveFormPromptLookupKeys(nodeId, useExecutionStore.getState().activityStates)

      detachPromise(
        fetchPromptsForNodeWithRetry(nodeId)
          .then((fetched) => {
            if (executionIdRef.current !== capturedExecutionId || latestNodeIdRef.current !== nodeId) return
            lastFetchErrorKeyRef.current = null

            const index = findFormPromptIndexForLookupKeys(fetched, lookupKeys)
            if (index >= 0) {
              applyNavigationList(fetched, fetched[index]?.id)
            } else {
              showInfo({
                title: notFoundTitle,
                description: formPromptNotFoundDescription(fetched.length, nodeId),
              })
            }
          })
          .catch((error: unknown) => {
            if (executionIdRef.current !== capturedExecutionId || latestNodeIdRef.current !== nodeId) return
            const message = getErrorMessage(error)
            const key = `${nodeId}::Failed to load form prompt::${message}`
            if (lastFetchErrorKeyRef.current === key) return
            lastFetchErrorKeyRef.current = key
            showError({
              title: 'Failed to load form prompt',
              description: message,
            })
          })
      )
    },
    [applyNavigationList, fetchPromptsForNodeWithRetry, showInfo, showError]
  )

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: ExecutionNode) => {
      if (!isWaitingFormPromptNode(node)) return
      loadPromptsForNode(node.id, 'Form prompt not found')
    },
    [loadPromptsForNode]
  )

  const handleActivityRowClick = useCallback(
    (canvasNodeId: string) => {
      loadPromptsForNode(canvasNodeId, 'Form prompt not found')
    },
    [loadPromptsForNode]
  )

  const navigateToIndex = useCallback(
    (index: number) => {
      if (formPrompts.length === 0) {
        setCurrentIndex(0)
        return
      }
      setCurrentIndex(Math.max(0, Math.min(index, formPrompts.length - 1)))
    },
    [formPrompts.length]
  )

  const clearFormPrompts = useCallback(() => {
    setFormPrompts([])
    setCurrentIndex(0)
    latestNodeIdRef.current = null
    clear()
  }, [clear])

  const setFormPromptsAndIndex = useCallback(
    (newPrompts: FormPromptSummary[], index: number) => {
      const selectedId = newPrompts[index]?.id ?? newPrompts[0]?.id
      applyNavigationList(newPrompts, selectedId)
    },
    [applyNavigationList]
  )

  const fetchFormPrompts = useCallback(async (): Promise<FormPromptSummary[]> => {
    const fetched = await fetchFormPromptsForExecution()
    return applyNavigationList(fetched, currentFormPrompt?.id)
  }, [applyNavigationList, fetchFormPromptsForExecution, currentFormPrompt?.id])

  const fetchPendingFormPrompts = useCallback(async (): Promise<FormPromptSummary[]> => {
    const fetched = await fetchPendingFromApi()
    return applyNavigationList(fetched, fetched[0]?.id)
  }, [applyNavigationList, fetchPendingFromApi])

  return {
    formPrompts,
    currentIndex,
    currentFormPrompt,
    isLoading,
    handleNodeClick,
    handleActivityRowClick,
    navigateToIndex,
    clearFormPrompts,
    setFormPromptsAndIndex,
    fetchFormPrompts,
    fetchPendingFormPrompts,
  }
}
