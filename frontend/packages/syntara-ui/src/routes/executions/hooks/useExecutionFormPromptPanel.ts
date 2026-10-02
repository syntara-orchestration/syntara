import type { FormsAPI } from '@syntara/contracts'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { FlowNodeType } from '../../../constants'
import { useAlerts } from '../../../providers/alerts'
import { ACTIVITY_STATUS, isTerminalState } from '../../builder/utils/executionState/executionHelpers'
import { latestActivityStateForCanvasNode } from '../../workflows/execution/utils/activityState'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'
import {
  canvasNodeIdFromPromptNodeId,
  findFormPromptIndexForLookupKeys,
  resolveFormPromptLookupKeys,
} from '../formPrompt/formPromptNodeId'
import { resolveCanvasNodeType, type WorkflowDefinitionLike } from '../formPrompt/resolveCanvasNodeType'

import { useAutoWaitingNodeDetection } from './useAutoWaitingNodeDetection'
import type { useExecutionNodeClick } from './useExecutionNodeClick'
import { useFetchFormPromptForUrlParam } from './useFetchFormPromptForUrlParam'
import { useFormPromptPanelUrlSync } from './useFormPromptPanelUrlSync'

type NodeClickResult = ReturnType<typeof useExecutionNodeClick>
type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']

export function useExecutionFormPromptPanel(
  executionId: string | undefined,
  searchParams: string,
  nodeClick: NodeClickResult,
  workflowDefinition: WorkflowDefinitionLike | undefined
) {
  const {
    clearFormPrompts,
    setFormPromptsAndIndex,
    fetchPendingFormPrompts,
    fetchFormPrompts,
    currentFormPrompt,
    formPrompts,
  } = nodeClick
  const [panelOpen, setPanelOpen] = useState(false)
  const prevPromptsLengthRef = useRef(0)
  const handledUrlPromptIdRef = useRef<string | null>(null)
  const [trackedExecutionId, setTrackedExecutionId] = useState(executionId)
  const { showError } = useAlerts()

  if (trackedExecutionId !== executionId) {
    setTrackedExecutionId(executionId)
    setPanelOpen(false)
  }

  const formPromptIdFromUrl = useMemo(() => new URLSearchParams(searchParams).get('form_prompt'), [searchParams])
  const urlFormPromptLookup = useFetchFormPromptForUrlParam(searchParams)
  const urlFormPrompt = urlFormPromptLookup.formPrompt

  useFormPromptPanelUrlSync({
    executionId,
    formPromptIdFromUrl,
    urlFormPromptLookup,
    urlFormPrompt,
    handledUrlPromptIdRef,
    fetchPendingFormPrompts,
    setFormPromptsAndIndex,
    setPanelOpen,
    showError,
  })

  const shouldDetectNode = useCallback(
    (nodeId: string) => resolveCanvasNodeType(nodeId, workflowDefinition) === FlowNodeType.FORM_PROMPT,
    [workflowDefinition]
  )

  const open = useCallback(() => {
    setPanelOpen(true)
  }, [])

  const close = useCallback(() => {
    setPanelOpen(false)
  }, [])

  const dismissInFlightRef = useRef(false)
  const dismiss = useCallback(() => {
    if (dismissInFlightRef.current) return
    dismissInFlightRef.current = true

    fetchPendingFormPrompts()
      .then((fetched) => {
        if (fetched.length > 0) {
          setFormPromptsAndIndex(fetched, 0)
        } else {
          setPanelOpen(false)
          clearFormPrompts()
        }
      })
      .catch(() => {
        setPanelOpen(false)
        clearFormPrompts()
      })
      .finally(() => {
        dismissInFlightRef.current = false
      })
  }, [fetchPendingFormPrompts, setFormPromptsAndIndex, clearFormPrompts])

  const lastAutoDetectErrorKeyRef = useRef<string | null>(null)

  const handleDetected = useCallback(
    (detected: FormPromptSummary) => {
      fetchFormPrompts()
        .then((fetched) => {
          const index = fetched.findIndex((p) => p.id === detected.id)
          if (index >= 0) {
            setFormPromptsAndIndex(fetched, index)
            setPanelOpen(true)
          }
        })
        .catch(() => {
          showError({
            title: 'Failed to load form prompt',
            description: 'Could not fetch form prompt details. Please try again.',
          })
        })
    },
    [fetchFormPrompts, setFormPromptsAndIndex, showError]
  )

  useAutoWaitingNodeDetection({
    executionId,
    shouldDetectNode,
    fetchForNode: async (nodeId: string) => {
      const fetched = await fetchFormPrompts()
      const lookupKeys = resolveFormPromptLookupKeys(nodeId, useExecutionStore.getState().activityStates)
      const index = findFormPromptIndexForLookupKeys(fetched, lookupKeys)
      return index >= 0 ? (fetched[index] ?? null) : null
    },
    onDetected: handleDetected,
    onFetchError: (_nodeId, error) => {
      const message = error instanceof Error ? error.message : 'Request failed'
      const key = `auto-detect::${message}`
      if (lastAutoDetectErrorKeyRef.current === key) return
      lastAutoDetectErrorKeyRef.current = key
      showError({
        title: 'Failed to load form prompt',
        description: 'Could not load the waiting form prompt automatically. Try selecting the step again.',
      })
    },
  })

  useEffect(() => {
    const prevLength = prevPromptsLengthRef.current
    const currentLength = formPrompts.length

    if (panelOpen && prevLength > 0 && currentLength === 0) {
      const timer = setTimeout(() => {
        setPanelOpen(false)
        clearFormPrompts()
      }, 0)
      prevPromptsLengthRef.current = currentLength
      return () => clearTimeout(timer)
    }

    prevPromptsLengthRef.current = currentLength
  }, [panelOpen, formPrompts.length, clearFormPrompts])

  useEffect(() => {
    if (!panelOpen || !currentFormPrompt) return

    const canvasId = canvasNodeIdFromPromptNodeId(currentFormPrompt.prompt_node_id)

    const unsubscribe = useExecutionStore.subscribe(() => {
      const activityState = latestActivityStateForCanvasNode(useExecutionStore.getState().activityStates, canvasId)
      const status = activityState?.status
      if (status && status !== ACTIVITY_STATUS.WAITING && isTerminalState(status)) {
        dismiss()
      }
    })

    return unsubscribe
  }, [panelOpen, currentFormPrompt, dismiss])

  return { panelOpen, open, close, dismiss }
}
