import { ExecutionStatusEnum, type Approval } from '@syntara/contracts'

import { activityExecutions, type ActivityExecutionMockSeed } from './activityExecutions'
import { executions } from './executions'
import { mockDate } from './mockDates'
import { workflows } from './workflows'

type WorkflowEdge = { from: string; to: string; from_port?: string }

/**
 * After PATCH /approvals/{id}, simulate Temporal resuming the workflow on mock API
 * (no worker). Keeps self-contained approval E2E aligned with real backend behavior.
 */
export function applyMockApprovalDecisionEffects(
  approval: Pick<Approval, 'execution_id' | 'approval_node_id' | 'decision_notes'>,
  decision: 'approved' | 'rejected' | 'cancelled'
): void {
  const executionId = approval.execution_id
  const approvalNodeId = approval.approval_node_id
  if (!executionId || !approvalNodeId || decision === 'cancelled') return

  const execution = executions.find((e) => e.id === executionId)
  if (!execution) return

  const workflow = workflows.find((w) => w.id === execution.workflow_id)
  const definition = workflow?.version?.workflow_definition as { edges?: WorkflowEdge[] } | undefined
  const edges = definition?.edges ?? []

  const approvedSuccessors = edges
    .filter((e) => e.from === approvalNodeId && e.from_port === 'approved')
    .map((e) => e.to)
  const rejectedSuccessors = edges
    .filter((e) => e.from === approvalNodeId && e.from_port === 'rejected')
    .map((e) => e.to)

  const activities = activityExecutions[executionId]
  const now = mockDate.now

  const markExecutionTerminal = () => {
    execution.status = ExecutionStatusEnum.COMPLETED
    execution.completed_at = now
    execution.updated_at = now
    const mutable = execution as {
      approval_pending?: boolean
      current_activities?: Array<unknown>
    }
    mutable.approval_pending = false
    mutable.current_activities = []
  }

  if (!activities) {
    markExecutionTerminal()
    return
  }
  const decisionNotes = approval.decision_notes ?? null

  const touch = (activityName: string, patch: Partial<ActivityExecutionMockSeed>) => {
    const act = activities.find((a) => a.activity_name === activityName)
    if (!act) return
    Object.assign(act, patch, { updated_at: now })
  }

  const complete = (activityName: string, output: Record<string, unknown>) => {
    const act = activities.find((a) => a.activity_name === activityName)
    touch(activityName, {
      status: 'completed',
      started_at: act?.started_at ?? now,
      completed_at: now,
      output_data: output,
    })
  }

  const skip = (activityName: string) => {
    touch(activityName, { status: 'skipped', completed_at: now })
  }

  if (decision === 'rejected') {
    complete(approvalNodeId, {
      status: 'completed',
      decision: 'rejected',
      decision_notes: decisionNotes,
    })
    if (rejectedSuccessors.length > 0) {
      for (const nodeId of rejectedSuccessors) complete(nodeId, {})
      for (const nodeId of approvedSuccessors) skip(nodeId)
    } else {
      for (const nodeId of approvedSuccessors) skip(nodeId)
    }
  } else {
    complete(approvalNodeId, {
      status: 'completed',
      decision: 'approved',
      decision_notes: decisionNotes,
    })
    for (const nodeId of approvedSuccessors) complete(nodeId, {})
    for (const nodeId of rejectedSuccessors) skip(nodeId)
  }

  markExecutionTerminal()
}
