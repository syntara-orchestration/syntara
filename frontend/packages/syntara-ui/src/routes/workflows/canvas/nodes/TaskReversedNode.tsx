import type { TaskActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { FlowNodeType } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { getNodeTypeColor } from '../nodeTypeColors'

import { NodeComponent } from './common/NodeComponent'
import { nodeMetadata } from './nodeMetadata'
import { TaskActivityDetails } from './TaskNode'
import { getTaskSemanticLabels } from './taskSemanticLabels'

/**
 * TaskReversedNode - A task node with reversed handles (input on right, output on left)
 *
 * This node type is used for tasks in loop-back paths to prevent edge crossings.
 * When a task is connected from a loop's 'loop' handle and back to the loop's 'end' handle,
 * reversing the handles creates a cleaner visual flow.
 *
 * The node shares the same rendering logic as TaskNode (via TaskActivityDetails)
 * but uses the reverseHandles prop to flip the handle positions.
 */
export type TaskReversedNode = { type: typeof FlowNodeType.TASK_REVERSED } & Node<TaskActivity>

export function TaskReversedNodeComponent(props: NodeProps<TaskReversedNode>) {
  const metadata = nodeMetadata.task

  // Extract execution state if present
  const executionState = (props.data as Record<string, unknown>).__executionState as
    | {
        status: ActivityStatus
        started_at?: string
        completed_at?: string
        error_details?: string
        retry_count?: number
      }
    | undefined

  return (
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      reverseHandles
      executionState={executionState}
      topBarColor={getNodeTypeColor(FlowNodeType.TASK_REVERSED, props.data)}
      semanticZoomSummary={getTaskSemanticLabels(props.data)}
    >
      <TaskActivityDetails data={props.data} iconColor={getNodeTypeColor(FlowNodeType.TASK_REVERSED, props.data)} />
    </NodeComponent>
  )
}
