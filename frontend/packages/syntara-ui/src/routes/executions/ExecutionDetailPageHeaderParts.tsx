import { Button, FlexItem } from '@patternfly/react-core'
import type { ExecutionsAPI } from '@syntara/contracts'

import { ApprovalPendingBadge } from '../../components/labels/ApprovalPendingBadge'
import { NxLabel } from '../../components/labels/NxLabel'
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
        <FlexItem>
          <StatusLabel status={execution.status} />
        </FlexItem>
      ) : null}
      {execution.approval_pending ? (
        <FlexItem>
          <ApprovalPendingBadge approvalPending={execution.approval_pending} />
        </FlexItem>
      ) : null}
      {execution.created_at ? (
        <FlexItem>
          <NxLabel isCompact={false}>
            Viewing run: <ExecutionTimestamp dateString={execution.created_at} />
          </NxLabel>
        </FlexItem>
      ) : null}
    </>
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
      {isCancellable && <CancelExecutionButton executionId={executionId} />}
      {isRetryable && execution && (
        <RetryExecutionButton
          executionId={executionId}
          workflowId={execution.workflow_id}
          workflowVersionId={execution.workflow_version_id}
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
