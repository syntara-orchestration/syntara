import { useReactFlow } from '@xyflow/react'
import { useCallback, useEffect, useMemo, useRef } from 'react'

import { useDialogState } from '../../../hooks/useDialogState'
import { useMockDataStore } from '../../../stores/useMockDataStore'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { getAncestorNodes } from '../../../utils/graphTraversal'
import type { RunStepDialogData } from '../components/RunStepDialog'

export function useRunStepDialog(
  handleSaveWorkflow: () => Promise<boolean>,
  isTerminalStatus: boolean,
  isNodeEditorOpen: boolean
) {
  const reactFlowInstance = useReactFlow()
  const runStepDialog = useDialogState<RunStepDialogData>()
  const openRunStepDialog = runStepDialog.open
  const lastRunStepNodeIdRef = useRef<string | null>(null)
  const suppressPanelCloseRef = useRef(false)

  const itemNodeId = runStepDialog.item?.nodeId
  const predecessors = runStepDialog.item?.predecessors

  const inputMocks = useMockDataStore((s) => (itemNodeId ? s.pinnedData[itemNodeId]?.inputMocks : undefined))
  const pinnedData = useMockDataStore((s) => s.pinnedData)

  const pinnedMockDataForDialog = useMemo(() => {
    if (!itemNodeId) return undefined
    const merged: Record<string, Record<string, unknown>> = inputMocks ? { ...inputMocks } : {}
    for (const pred of predecessors ?? []) {
      if (!merged[pred.id]) {
        const outputMock = pinnedData[pred.id]?.outputMock
        if (outputMock) merged[pred.id] = outputMock
      }
    }
    return Object.keys(merged).length > 0 ? merged : undefined
  }, [itemNodeId, predecessors, inputMocks, pinnedData])

  const handleRunStep = useCallback(
    async (nodeId: string) => {
      const node = reactFlowInstance.getNode(nodeId)
      if (!node?.data) return

      // Only save when there is something to persist: the node editor is open
      // (its form may hold unsaved edits) or the workflow is dirty. Skipping the
      // save on a clean, closed-editor workflow avoids a redundant PATCH.
      if (isNodeEditorOpen || useWorkflowStore.getState().isDirty) {
        // Suppress panel close during save - guardedSaveWorkflow may auto-submit
        // the node editor form, which triggers onClose() that we need to block
        suppressPanelCloseRef.current = true
        try {
          // guardedSaveWorkflow auto-submits node editor form if open, then saves
          if (!(await handleSaveWorkflow())) return
        } finally {
          suppressPanelCloseRef.current = false
        }
      }

      const edges = reactFlowInstance.getEdges()
      const nodes = reactFlowInstance.getNodes()
      const predecessors: RunStepDialogData['predecessors'] = getAncestorNodes(nodeId, edges, nodes, {
        includeTriggers: true,
      })

      openRunStepDialog({ nodeId, nodeName: (node.data as { name?: string }).name ?? nodeId, predecessors })
    },
    [reactFlowInstance, openRunStepDialog, handleSaveWorkflow, isNodeEditorOpen]
  )

  const hasCleanedUpRef = useRef(false)
  useEffect(() => {
    if (isTerminalStatus && lastRunStepNodeIdRef.current && !hasCleanedUpRef.current) {
      useMockDataStore.getState().unpinAllInputMocks(lastRunStepNodeIdRef.current)
      lastRunStepNodeIdRef.current = null
      hasCleanedUpRef.current = true
    }
    if (!isTerminalStatus) hasCleanedUpRef.current = false
  }, [isTerminalStatus])

  return { runStepDialog, lastRunStepNodeIdRef, pinnedMockDataForDialog, handleRunStep, suppressPanelCloseRef }
}
