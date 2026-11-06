import { type Node, type NodeTypes } from '@xyflow/react'

import { FlowNodeType } from '../../../../constants'

import { type ApprovalNode, ApprovalStepComponent } from './ApprovalNode'
import { type ConditionNode, ConditionStepComponent } from './ConditionNode'
import { type ConvergeNode, ConvergeStepComponent } from './ConvergeNode'
import { type GenericNode, GenericStepComponent } from './GenericNode'
import { type LoopNode, LoopStepComponent } from './LoopNode'
import { type SwitchNode, SwitchStepComponent } from './SwitchNode'
import { type TaskNode, TaskStepComponent } from './TaskNode'
import { type TaskReversedNode, TaskReversedStepComponent } from './TaskReversedNode'
import { type TriggerNode, TriggerStepComponent } from './TriggerNode'
import { type WaitNode, WaitStepComponent } from './WaitNode'

/** Invisible React Flow node used only as a valid target for button edges (not a workflow step). */
export type ButtonEdgePlaceholderNode = Node<Record<string, unknown>, typeof FlowNodeType.PLACEHOLDER>

export type NodeType =
  | TriggerNode
  | TaskNode
  | TaskReversedNode
  | ApprovalNode
  | ConditionNode
  | ConvergeNode
  | LoopNode
  | SwitchNode
  | WaitNode
  | GenericNode
  | ButtonEdgePlaceholderNode

export const nodeTypes: NodeTypes = {
  [FlowNodeType.TRIGGER]: TriggerStepComponent,
  [FlowNodeType.TASK]: TaskStepComponent,
  [FlowNodeType.TASK_REVERSED]: TaskReversedStepComponent,
  [FlowNodeType.APPROVAL]: ApprovalStepComponent,
  [FlowNodeType.CONDITION]: ConditionStepComponent,
  [FlowNodeType.CONVERGE]: ConvergeStepComponent,
  [FlowNodeType.LOOP]: LoopStepComponent,
  [FlowNodeType.SWITCH]: SwitchStepComponent,
  [FlowNodeType.WAIT]: WaitStepComponent,
  [FlowNodeType.GENERIC]: GenericStepComponent,
}
