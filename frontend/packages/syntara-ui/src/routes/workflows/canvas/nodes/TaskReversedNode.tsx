import type { TaskActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynStep } from '../../../../components/steps/SynStep'
import { FlowNodeType } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { getStepTypeColor } from '../stepTypeColors'

import { stepMetadata } from './stepMetadata'
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

export function TaskReversedStepComponent(props: NodeProps<TaskReversedNode>) {
  const metadata = stepMetadata.task

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
    <SynStep
      className={metadata.className}
      nodeProps={props}
      reverseHandles
      executionState={executionState}
      topBarColor={getStepTypeColor(FlowNodeType.TASK_REVERSED, props.data)}
      semanticZoomSummary={getTaskSemanticLabels(props.data)}
    >
      <TaskActivityDetails data={props.data} iconColor={getStepTypeColor(FlowNodeType.TASK_REVERSED, props.data)} />
    </SynStep>
  )
}
