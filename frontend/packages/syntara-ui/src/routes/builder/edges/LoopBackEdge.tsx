import { useReactFlow, Position, useStore } from '@xyflow/react'

import { EdgeActions } from './EdgeActions'
import { EdgeLabel } from './EdgeLabel'
import { EdgePath } from './EdgePath'
import { adjustSourceCoordinates } from './edgeUtils'
import type { BaseEdgeProps } from './types'
import { useEdgeHandlers } from './useEdgeHandlers'

function getNodeBottom(node: { position: { y: number }; measured?: { height?: number } }): number {
  return node.position.y + (node.measured?.height ?? 0)
}

/**
 * Loop-back edge component with custom path routing
 * This edge type is optimized for connections that loop back to a loop node's end handle
 * Routes the edge below the loop body nodes for clear visual flow
 */
export function LoopBackEdge(props: BaseEdgeProps) {
  const { sourceX, sourceY, targetX, targetY, label, style, id, source, target, data, markerEnd, selected } = props
  const reactFlowInstance = useReactFlow()
  const { getNodes } = reactFlowInstance
  const nodesConnectable = useStore((s) => s.nodesConnectable)

  const {
    isHovered,
    isEdgeHovered,
    effectiveMarkerEnd,
    handleEdgeMouseEnter,
    handleEdgeMouseLeave,
    handleButtonMouseEnter,
    handleButtonMouseLeave,
    handleDelete,
    handleAddNode,
  } = useEdgeHandlers({
    edgeId: id,
    source,
    target,
    markerEnd,
    selected,
    data,
  })

  // Calculate vertical offset dynamically based on nodes in the loop body
  // Find the loop node (target of this edge)
  const targetNode = getNodes().find((n) => n.id === target)
  const sourceNode = getNodes().find((n) => n.id === source)

  // Calculate the maximum bottom position so the edge's horizontal segment goes below the loop node and all loop body nodes
  let maxBottomY = sourceY

  if (targetNode && sourceNode) {
    // Include the loop node (target) so the edge passes below it and isn't hidden underneath
    maxBottomY = Math.max(maxBottomY, getNodeBottom(targetNode))

    // Include the source node (last node in the loop body)
    maxBottomY = Math.max(maxBottomY, getNodeBottom(sourceNode))

    // Also include any other nodes between target and source
    const allNodes = getNodes()
    const loopBodyNodes = allNodes.filter((node) => {
      if (!node.position || node.measured?.height == null) return false // Skip nodes without position or height (include height === 0)
      if (node.id === source || node.id === target) return false // Already handled by target/source nodes
      const nodeY = node.position.y + node.measured.height / 2
      const nodeX = node.position.x
      // Nodes at similar Y level to target/source and between them horizontally
      return (
        Math.abs(nodeY - targetY) < 100 && // Similar Y level (within 100px)
        nodeX > targetX && // To the right of target (loop node)
        nodeX < sourceX // To the left of source (last node in loop)
      )
    })

    // Find the maximum bottom edge of these nodes
    loopBodyNodes.forEach((node) => {
      maxBottomY = Math.max(maxBottomY, getNodeBottom(node))
    })
  }

  const { x: adjustedSourceX, y: adjustedSourceY } = adjustSourceCoordinates(sourceX, sourceY, Position.Right)

  // Add padding below the lowest node for clear visual separation
  // Use moderate padding to avoid excessive whitespace
  // Calculate vertical offset using adjusted sourceY to maintain correct spacing
  const verticalOffset = Math.max(40, maxBottomY - adjustedSourceY + 20)

  // Calculate the path with rounded corners for better visual flow:
  // 1. Go right from source
  // 2. Drop down below the nodes
  // 3. Route horizontally back to target X
  // 4. Come up to target
  const cornerRadius = 8
  const horizontalOffset = 15

  const edgePath = `
    M ${adjustedSourceX},${adjustedSourceY}
    L ${adjustedSourceX + horizontalOffset - cornerRadius},${adjustedSourceY}
    Q ${adjustedSourceX + horizontalOffset},${adjustedSourceY} ${adjustedSourceX + horizontalOffset},${adjustedSourceY + cornerRadius}
    L ${adjustedSourceX + horizontalOffset},${adjustedSourceY + verticalOffset - cornerRadius}
    Q ${adjustedSourceX + horizontalOffset},${adjustedSourceY + verticalOffset} ${adjustedSourceX + horizontalOffset - cornerRadius},${adjustedSourceY + verticalOffset}
    L ${targetX - horizontalOffset + cornerRadius},${adjustedSourceY + verticalOffset}
    Q ${targetX - horizontalOffset},${adjustedSourceY + verticalOffset} ${targetX - horizontalOffset},${adjustedSourceY + verticalOffset - cornerRadius}
    L ${targetX - horizontalOffset},${targetY + cornerRadius}
    Q ${targetX - horizontalOffset},${targetY} ${targetX - horizontalOffset + cornerRadius},${targetY}
    L ${targetX},${targetY}
  `

  // Position label in the middle of the horizontal bottom segment
  // Use adjusted coordinates for consistency with the edge path
  const labelX = (adjustedSourceX + targetX) / 2
  const labelY = adjustedSourceY + verticalOffset

  return (
    <>
      <EdgePath
        edgePath={edgePath}
        markerEnd={effectiveMarkerEnd}
        style={style}
        selected={selected}
        isEdgeHovered={isEdgeHovered}
        data={data}
        onMouseEnter={handleEdgeMouseEnter}
        onMouseLeave={handleEdgeMouseLeave}
      />
      <EdgeLabel labelX={labelX} labelY={labelY} label={label} />
      {(isHovered || data?.isActive) && !data?.isPending && !data?.executionStatus && nodesConnectable && (
        <EdgeActions
          labelX={labelX}
          labelY={labelY}
          onButtonMouseEnter={handleButtonMouseEnter}
          onButtonMouseLeave={handleButtonMouseLeave}
          onAddNode={handleAddNode}
          onDelete={handleDelete}
        />
      )}
    </>
  )
}
