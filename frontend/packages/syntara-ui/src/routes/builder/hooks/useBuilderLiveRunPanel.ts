import { type ExecutionStatus, ExecutionStatusEnum } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { detachPromise } from '../../../utils/detachPromise'
import { useExecutionWebSocket } from '../../workflows/hooks/useExecutionWebSocket'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

type UseBuilderLiveRunPanelParams = {
  mostRecentExecutionId: string | null | undefined
  mostRecentRunPanelOpen: boolean
  executionStatus: ExecutionStatus | null | undefined
  isViewingExecution: boolean
  onClosePanel: () => void
}

type UseBuilderLiveRunPanelResult = {
  showMostRecentRunPanelInEditor: boolean
  isTerminalStatus: boolean
  isLiveRunActive: boolean
  canvasExecutionStatus: ExecutionStatus | null | undefined
  mostRecentSelectedNodeId: string | null
  mostRecentSelectedNodeName: string | null
  mostRecentPanelHeight: number
  handleMostRecentResize: (deltaY: number) => void
  handleMostRecentNodeSelect: (nodeId: string, nodeName: string) => void
  handleMostRecentDeselectNode: () => void
  handleCloseMostRecentRunPanel: () => void
}

const MIN_PANEL_HEIGHT = 100
const MAX_PANEL_HEIGHT = 600

export function useBuilderLiveRunPanel({
  mostRecentExecutionId,
  mostRecentRunPanelOpen,
  executionStatus,
  isViewingExecution,
  onClosePanel,
}: UseBuilderLiveRunPanelParams): UseBuilderLiveRunPanelResult {
  const queryClient = useQueryClient()

  const [mostRecentSelectedNodeId, setMostRecentSelectedNodeId] = useState<string | null>(null)
  const [mostRecentSelectedNodeName, setMostRecentSelectedNodeName] = useState<string | null>(null)
  const [mostRecentPanelHeight, setMostRecentPanelHeight] = useState(300)

  const prevExecutionIdRef = useRef<string | null | undefined>(null)

  useEffect(() => {
    if (mostRecentExecutionId && prevExecutionIdRef.current !== mostRecentExecutionId) {
      useExecutionStore.getState().reset()
    }
    prevExecutionIdRef.current = mostRecentExecutionId
  }, [mostRecentExecutionId])

  const isActive = mostRecentRunPanelOpen && !!mostRecentExecutionId
  const isTerminalStatus =
    executionStatus === ExecutionStatusEnum.COMPLETED ||
    executionStatus === ExecutionStatusEnum.FAILED ||
    executionStatus === ExecutionStatusEnum.CANCELLED ||
    executionStatus === ExecutionStatusEnum.DENIED
  // Preserve undefined (status still loading) vs null (explicitly no execution).
  // resolveExecutionStatus uses null as the "edit mode" sentinel; undefined lets
  // the WebSocket store's visualization status take over while REST is in-flight.
  const canvasExecutionStatus = isActive ? executionStatus : null
  const showMostRecentRunPanelInEditor = isActive && !isViewingExecution
  const isLiveRunActive = showMostRecentRunPanelInEditor && !isTerminalStatus

  useExecutionWebSocket(mostRecentExecutionId ?? '', {
    // Connect whenever the panel is active, regardless of what REST says about
    // terminal status. The WS's own EVENTS_EXPIRED event gates the disconnect via
    // onExecutionComplete — not the REST status. This avoids a race where a fast
    // execution completes before the WS delivers per-node activity events:
    // if we disabled on REST terminal status, activityStates would stay empty and
    // no canvas badges would ever appear.
    enabled: isActive,
    onExecutionComplete: () => {
      detachPromise(
        Promise.all([
          queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}'] }),
          queryClient.invalidateQueries({ queryKey: ['get', '/executions'] }),
          queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}/activities'] }),
        ])
      )
    },
  })

  const handleMostRecentResize = useCallback((deltaY: number) => {
    setMostRecentPanelHeight((prev) => Math.min(MAX_PANEL_HEIGHT, Math.max(MIN_PANEL_HEIGHT, prev - deltaY)))
  }, [])

  const handleMostRecentNodeSelect = useCallback((nodeId: string, nodeName: string) => {
    setMostRecentSelectedNodeId(nodeId)
    setMostRecentSelectedNodeName(nodeName)
  }, [])

  const handleMostRecentDeselectNode = useCallback(() => {
    setMostRecentSelectedNodeId(null)
    setMostRecentSelectedNodeName(null)
  }, [])

  return {
    showMostRecentRunPanelInEditor,
    isTerminalStatus,
    isLiveRunActive,
    canvasExecutionStatus,
    mostRecentSelectedNodeId,
    mostRecentSelectedNodeName,
    mostRecentPanelHeight,
    handleMostRecentResize,
    handleMostRecentNodeSelect,
    handleMostRecentDeselectNode,
    handleCloseMostRecentRunPanel: onClosePanel,
  }
}
