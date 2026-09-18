import { useReactFlow } from '@xyflow/react'
import { useEffect, useRef, useState } from 'react'

/**
 * Shared hook for edge hover state management.
 * Handles hover detection with delayed cleanup to allow moving from edge to buttons.
 */
export function useEdgeHover() {
  const [isHovered, setIsHovered] = useState(false)
  const [isEdgeHovered, setIsEdgeHovered] = useState(false)
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) {
        clearTimeout(hoverTimeoutRef.current)
      }
    }
  }, [])

  const handleMouseEnter = () => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current)
      hoverTimeoutRef.current = null
    }
    setIsHovered(true)
    setIsEdgeHovered(true)
  }

  const handleMouseLeave = () => {
    setIsEdgeHovered(false)
    hoverTimeoutRef.current = setTimeout(() => {
      setIsHovered(false)
    }, 200) // Delay to allow moving between edge and buttons
  }

  return {
    isHovered,
    isEdgeHovered,
    handleEdgeMouseEnter: handleMouseEnter,
    handleEdgeMouseLeave: handleMouseLeave,
    handleButtonMouseEnter: handleMouseEnter,
    handleButtonMouseLeave: handleMouseLeave,
  }
}

/**
 * Gets the source handle from an edge, since ReactFlow doesn't always pass it as a prop.
 */
export function useEdgeSourceHandle(edgeId: string): string | undefined {
  const reactFlowInstance = useReactFlow()
  const fullEdge = reactFlowInstance.getEdge(edgeId)
  return fullEdge?.sourceHandle ?? undefined
}
