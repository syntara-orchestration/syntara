import { useEffect, useRef, useState } from 'react'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

type UseWorkflowInitializationOptions = {
  nodes: NodeType[]
  workflowVersion: number
  onLayout: (options?: { markDirty?: boolean }) => void
  onVersionChange?: () => void
  /** Called after the first automatic layout completes (useful for clearing undo history). */
  onAfterInitialLayout?: () => void
}

/**
 * Custom hook that manages workflow initialization and layout triggering.
 *
 * Handles:
 * - Initial measurement detection (waiting for all nodes to be measured)
 * - First layout trigger after initialization
 * - Layout on workflow version change
 * - Layout on external trigger
 */
export function useWorkflowInitialization({
  nodes,
  workflowVersion,
  onLayout,
  onVersionChange,
  onAfterInitialLayout,
}: UseWorkflowInitializationOptions) {
  const [isInitialized, setIsInitialized] = useState(false)
  const hasRunInitialLayoutRef = useRef(false)
  const workflowVersionRef = useRef(workflowVersion)

  // Store latest callbacks in refs to avoid them being dependencies
  const onLayoutRef = useRef(onLayout)
  useEffect(() => {
    onLayoutRef.current = onLayout
  }, [onLayout])

  const onAfterInitialLayoutRef = useRef(onAfterInitialLayout)
  useEffect(() => {
    onAfterInitialLayoutRef.current = onAfterInitialLayout
  }, [onAfterInitialLayout])

  // Reset initialization when workflow is replaced via setWorkflow (e.g., after save/redirect)
  useEffect(() => {
    if (workflowVersion !== workflowVersionRef.current) {
      // Use queueMicrotask to avoid calling setState synchronously within the effect
      queueMicrotask(() => {
        setIsInitialized(false)
      })
      hasRunInitialLayoutRef.current = false
      workflowVersionRef.current = workflowVersion

      // Notify parent of version change
      onVersionChange?.()
    }
  }, [workflowVersion, onVersionChange])

  // Apply initial layout after nodes are measured
  useEffect(() => {
    if (!isInitialized && nodes.length > 0 && nodes.every((node) => node.measured)) {
      // Schedule state update to avoid cascading renders
      queueMicrotask(() => {
        setIsInitialized(true)
      })
    }
  }, [nodes, isInitialized])

  // Run layout once after initialization completes.
  // Skip when positions are already stored (undo/redo restores exact positions).
  useEffect(() => {
    if (isInitialized && !hasRunInitialLayoutRef.current) {
      hasRunInitialLayoutRef.current = true
      const hasStoredPositions = Object.keys(useWorkflowStore.getState().nodePositions).length > 0
      if (hasStoredPositions) {
        onAfterInitialLayoutRef.current?.()
        return
      }
      const timer = setTimeout(() => {
        onLayoutRef.current()
        onAfterInitialLayoutRef.current?.()
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [isInitialized])

  return {
    isInitialized,
    hasRunInitialLayoutRef,
    workflowVersionRef,
  }
}
