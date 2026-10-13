import { type Dispatch, type SetStateAction, useEffect } from 'react'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { detectLoopBackNodes } from '../utils/detectLoopBackNodes'
import { type ActivityWithMetadata } from '../utils/executionState'
import type { EdgeType } from '../utils/workflowToGraph'

/**
 * Apply loop-back node type transformations to a list of nodes.
 * Mutates nothing — returns a new array only when changes are needed.
 */
export function applyLoopBackNodeTypes(nodes: NodeType[], loopBackNodeIds: Set<string>): NodeType[] {
  let hasChanges = false
  const updatedNodes = nodes.map((node) => {
    const shouldBeReversed = loopBackNodeIds.has(node.id)

    if (node.type === FlowNodeType.GENERIC) {
      const currentReverseHandles = (node.data as ActivityWithMetadata).metadata?.__reverseHandles as
        boolean | undefined

      if (shouldBeReversed && !currentReverseHandles) {
        hasChanges = true
        return {
          ...node,
          data: {
            ...node.data,
            metadata: { ...(node.data as ActivityWithMetadata).metadata, __reverseHandles: true },
          },
        }
      } else if (!shouldBeReversed && currentReverseHandles) {
        hasChanges = true
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { __reverseHandles: _reverseHandles, ...restMetadata } =
          (node.data as ActivityWithMetadata).metadata ?? {}
        return {
          ...node,
          data: {
            ...node.data,
            metadata: restMetadata,
          },
        }
      }
      return node
    }

    if (node.type !== FlowNodeType.TASK && node.type !== FlowNodeType.TASK_REVERSED) {
      return node
    }

    const isCurrentlyReversed = node.type === FlowNodeType.TASK_REVERSED

    if (shouldBeReversed && !isCurrentlyReversed) {
      hasChanges = true
      return { ...node, type: FlowNodeType.TASK_REVERSED }
    } else if (!shouldBeReversed && isCurrentlyReversed) {
      hasChanges = true
      return { ...node, type: FlowNodeType.TASK }
    }

    return node
  })

  return hasChanges ? updatedNodes : nodes
}

export function useLoopBackNodeTypes({
  edges,
  isInitialized,
  setNodes,
}: {
  edges: EdgeType[]
  isInitialized: boolean
  setNodes: Dispatch<SetStateAction<NodeType[]>>
}) {
  useEffect(() => {
    if (!isInitialized) return

    setNodes((currentNodes) => {
      const loopBackNodeIds = detectLoopBackNodes(edges, currentNodes)
      return applyLoopBackNodeTypes(currentNodes, loopBackNodeIds)
    })
  }, [edges, isInitialized, setNodes])
}
