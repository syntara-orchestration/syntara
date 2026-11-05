import { Button, FlexItem } from '@patternfly/react-core'
import type { ExecutionsAPI } from '@syntara/contracts'

import { executionsClient } from '../../client'
import { ApprovalPendingBadge } from '../../components/labels/ApprovalPendingBadge'
import { SynLabel } from '../../components/labels/SynLabel'
import { SynLink } from '../../components/SynLink'
import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { StatusLabel } from '../builder/ExecutionStatus'
import { RunHistoryToggleButton } from '../builder/RunHistoryToggleButton'

import { ApprovalActionButtons } from './ApprovalActionButtons'
import { CancelExecutionButton } from './CancelExecutionButton'
import { isExecutionRetryable } from './executionRetryable'
import { RetryExecutionButton } from './RetryExecutionButton'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']

export function ExecutionDetailTitleRowAddons({ execution }: Readonly<{ execution: Execution | undefined }>) {
  if (!execution?.status && !execution?.created_at) {
    return null
  }
  return (
    <>
      {execution.status ? (
        <FlexItem data-testid="execution-status-badge">
          <StatusLabel status={execution.status} />
        </FlexItem>
      ) : null}
      {execution.approval_pending ? (
        <FlexItem data-testid="approval-status-badge">
          <ApprovalPendingBadge approvalPending={execution.approval_pending} />
        </FlexItem>
      ) : null}
      {execution.created_at ? (
        <FlexItem>
          <SynLabel isCompact={false}>
            Viewing run: <ExecutionTimestamp dateString={execution.created_at} />
          </SynLabel>
        </FlexItem>
      ) : null}
    </>
  )
}

/**
 * "View parent run" link for a sub-workflow execution. Rendered as secondary context
 * directly beneath the title (via SynPageHeader `titleSubRow`) so the parent relationship
 * reads as context for this run and stays grouped with its title. Resolves the parent
 * workflow name from its execution id so the return link matches the forward link, and
 * renders nothing for a top-level execution.
 */
export function ExecutionDetailParentRunLink({ execution }: Readonly<{ execution: Execution | undefined }>) {
  const parentExecutionId =
    typeof execution?.execution_metadata?.parent_execution_id === 'string'
      ? execution.execution_metadata.parent_execution_id
      : undefined
  const parentQuery = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}',
    { params: { path: { execution_id: parentExecutionId ?? '' } } },
    { enabled: Boolean(parentExecutionId) }
  )
  const parentName = parentQuery.data?.workflow_name ?? null

  if (!parentExecutionId) {
    return null
  }
  return (
    <div data-testid="view-parent-run">
      <SynLink to={`/executions/${parentExecutionId}`}>View parent run{parentName ? `: ${parentName}` : ''}</SynLink>
    </div>
  )
}

export type ExecutionDetailHeaderToolbarProps = Readonly<{
  showApprovalActionStrip: boolean
  isApprovalLoading: boolean
  isApprovalPanelOpen?: boolean
  onReviewClick: () => void
  historyCardOpen: boolean
  onToggleHistory: () => void
  onBackToEditor: () => void
  onCopyToEditor: () => void
  isCancellable: boolean
  executionId: string
  execution: Execution | undefined
}>

export function ExecutionDetailHeaderToolbar({
  showApprovalActionStrip,
  isApprovalLoading,
  isApprovalPanelOpen,
  onReviewClick,
  historyCardOpen,
  onToggleHistory,
  onBackToEditor,
  onCopyToEditor,
  isCancellable,
  executionId,
  execution,
}: ExecutionDetailHeaderToolbarProps) {
  const isRetryable = isExecutionRetryable(execution?.status, execution?.mode)

  return (
    <>
      {showApprovalActionStrip && (
        <ApprovalActionButtons
          isLoading={isApprovalLoading}
          isDisabled={isApprovalPanelOpen}
          onReviewClick={onReviewClick}
        />
      )}
      {isCancellable && execution && (
        <CancelExecutionButton executionId={executionId} projectId={execution.project_id} />
      )}
      {isRetryable && execution && (
        <RetryExecutionButton
          executionId={executionId}
          workflowId={execution.workflow_id}
          workflowVersionId={execution.workflow_version_id}
          projectId={execution.project_id}
        />
      )}
      <Button variant="secondary" onClick={onCopyToEditor}>
        Copy to editor
      </Button>
      <Button variant={showApprovalActionStrip ? 'secondary' : 'primary'} onClick={onBackToEditor}>
        Back to editor
      </Button>
      <RunHistoryToggleButton onClick={onToggleHistory} isActive={historyCardOpen} />
    </>
  )
}
