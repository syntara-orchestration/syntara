import type { Node, ReactFlowInstance } from '@xyflow/react'
import { useCallback, type Dispatch } from 'react'

import { getActivityMetadata, useWorkflowStore } from '../../../stores/useWorkflowStore'
import { selectTriggers } from '../../../stores/workflowStoreSelectors'
import { toReactFlowNodeId } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { BuilderAction } from '../builderReducer'

const EMPTY_TRIGGERS: Array<{ id: string }> = []

export function useNodePanelNavigation(
  reactFlowInstance: ReactFlowInstance,
  dispatch: Dispatch<BuilderAction>
): (nodeId: string) => void {
  const triggers = useWorkflowStore(selectTriggers) ?? EMPTY_TRIGGERS

  return useCallback(
    (nodeId: string) => {
      const flowNodeId = toReactFlowNodeId(nodeId, triggers)
      const node = reactFlowInstance.getNode(flowNodeId)
      if (!node) return
      const isGeneric = getActivityMetadata(node.data)?.__isGeneric === true
      dispatch({
        type: 'NODE_CLICK',
        payload: { node: node as Node<NodeType['data']>, isGeneric },
      })
    },
    [reactFlowInstance, dispatch, triggers]
  )
}
