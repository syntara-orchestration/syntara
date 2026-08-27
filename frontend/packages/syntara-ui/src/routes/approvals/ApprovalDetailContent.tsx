import {
  ActionList,
  ActionListItem,
  Button,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Divider,
  FormGroup,
  Split,
  Stack,
  StackItem,
  TextInput,
} from '@patternfly/react-core'
import { RhUiBackwardsIcon, RhUiDislikeIcon, RhUiLikeIcon } from '@patternfly/react-icons'
import type { Approval } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { approvalsClient } from '../../client'
import { NxCodeBlock } from '../../components/details/NxCodeBlock'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { DateCell } from '../../components/table/DateCell'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useMutationErrorHandler } from '../../hooks/useMutationErrorHandler'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { useAlerts } from '../../providers/alerts'

import styles from './ApprovalDetailContent.module.css'
import { lookupMapByApprovalNodeId } from './approvalNodeId'
import { getNotesLabel } from './approvalNotes'
import { getApprovalPromptFromRecord } from './approvalPrompt'
import { ApprovalStatusBadges } from './approvalUtils'
import { buildWorkflowBuilderLink } from './buildWorkflowBuilderLink'
import { canDecideOnApproval } from './canDecideOnApproval'
import { useApprovalDecideProjects } from './useApprovalDecideProjects'
import { useCanDecideApproval } from './useCanDecideApproval'

const getDecisionCopy = (decision: 'approved' | 'rejected') => ({
  label: decision === 'approved' ? 'Approval notes' : 'Rejection notes',
  verb: decision === 'approved' ? 'approving' : 'rejecting',
})

/** Resolve human-readable approval node name from activity name map. */
function resolveApprovalName(approval: Approval, activityNameMap?: Map<string, string>): string {
  const approvalNodeId = approval.approval_node_id
  if (approvalNodeId && activityNameMap) {
    const resolvedNodeName = lookupMapByApprovalNodeId(activityNameMap, approvalNodeId)
    if (resolvedNodeName) return resolvedNodeName
  }
  return approval.name
}

type ApprovalDetailContentProps = Readonly<{
  approval: Approval
  /** Optional message to display when the approval record has no persisted prompt (e.g. node definition fallback). */
  message?: string
  /** Optional map of activity ID to human-readable name for resolving approval node names. */
  activityNameMap?: Map<string, string>
  onDecisionSubmitted?: () => void
  onWorkflowClick?: (link: string) => void
}>

function getDecideTooltip(
  permissions: { canDecide: boolean },
  canDecideBasedOnApproverList: boolean,
  approval: Approval
): string | undefined {
  if (!permissions.canDecide) {
    return permissionTooltip('approve or reject this approval', 'approval:decide')
  }
  if (!canDecideBasedOnApproverList) {
    const approverUsers = approval.approver_users?.map((u: { username: string }) => u.username) ?? []
    const approverGroups = approval.approver_groups?.map((g: { name: string }) => g.name) ?? []

    if (approverUsers.length === 0 && approverGroups.length === 0) {
      return 'This approval has no authorized approvers configured.'
    }

    const parts = []
    if (approverUsers.length > 0) {
      parts.push(`Users: ${approverUsers.join(', ')}`)
    }
    if (approverGroups.length > 0) {
      parts.push(`Groups: ${approverGroups.join(', ')}`)
    }

    return `This approval is restricted to: ${parts.join(' • ')}`
  }
  return undefined
}

function DecisionButtons({
  canDecide,
  isCheckingPermission,
  isSubmitting,
  decideTooltip,
  onApprove,
  onReject,
}: Readonly<{
  canDecide: boolean
  isCheckingPermission: boolean
  isSubmitting: boolean
  decideTooltip: string
  onApprove: () => void
  onReject: () => void
}>) {
  const buttonsDisabled = isSubmitting || isCheckingPermission || !canDecide
  return (
    <ActionList className={styles.buttonGap}>
      <ActionListItem>
        <DisabledWithTooltip isDisabled={!canDecide && !isCheckingPermission} content={decideTooltip}>
          <Button icon={<RhUiLikeIcon />} variant="secondary" isAriaDisabled={buttonsDisabled} onClick={onApprove}>
            Approve
          </Button>
        </DisabledWithTooltip>
      </ActionListItem>
      <ActionListItem>
        <DisabledWithTooltip isDisabled={!canDecide && !isCheckingPermission} content={decideTooltip}>
          <Button
            icon={<RhUiDislikeIcon />}
            variant="secondary"
            isDanger
            isAriaDisabled={buttonsDisabled}
            onClick={onReject}
          >
            Reject
          </Button>
        </DisabledWithTooltip>
      </ActionListItem>
    </ActionList>
  )
}

function PendingDecisionForm({
  pendingDecision,
  pendingReason,
  isSubmitting,
  onReasonChange,
  onUndo,
}: Readonly<{
  pendingDecision: 'approved' | 'rejected'
  pendingReason: string
  isSubmitting: boolean
  onReasonChange: (value: string) => void
  onUndo: () => void
}>) {
  const decisionCopy = getDecisionCopy(pendingDecision)
  return (
    <Stack hasGutter>
      <Split hasGutter>
        <ApprovalStatusBadges status={pendingDecision} />
        <Button
          icon={<RhUiBackwardsIcon />}
          variant="plain"
          isInline
          aria-label="Undo decision"
          isDisabled={isSubmitting}
          onClick={onUndo}
        />
      </Split>
      <FormGroup isInline label={decisionCopy.label}>
        <TextInput
          aria-label={decisionCopy.label}
          value={pendingReason}
          onChange={(_e, value: string) => onReasonChange(value)}
          placeholder={`Explain the reason for ${decisionCopy.verb} this workflow step.`}
        />
      </FormGroup>
    </Stack>
  )
}

function ApprovalSummary({
  approvalDisplayName,
  approvalInitiatedAt,
  approvalMessage,
  workflowName,
  workflowLink,
  onWorkflowClick,
}: Readonly<{
  approvalDisplayName: string
  approvalInitiatedAt: string | null | undefined
  approvalMessage: string | undefined
  workflowName: string
  workflowLink: string | undefined
  onWorkflowClick?: (link: string) => void
}>) {
  return (
    <DescriptionList>
      <DescriptionListGroup>
        <DescriptionListTerm>Approval step</DescriptionListTerm>
        <DescriptionListDescription>{approvalDisplayName}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Workflow</DescriptionListTerm>
        <DescriptionListDescription>
          {workflowLink && onWorkflowClick ? (
            <Button
              variant="link"
              isInline
              onClick={() => onWorkflowClick(workflowLink)}
              className={styles.workflowLink}
            >
              {workflowName}
            </Button>
          ) : (
            workflowName
          )}
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Approval initiated</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={approvalInitiatedAt} />
        </DescriptionListDescription>
      </DescriptionListGroup>
      {approvalMessage && (
        <DescriptionListGroup>
          <DescriptionListTerm>Message</DescriptionListTerm>
          <DescriptionListDescription className={styles.message}>{approvalMessage}</DescriptionListDescription>
        </DescriptionListGroup>
      )}
    </DescriptionList>
  )
}

/**
 * Reusable approval detail content: decision actions, summary, and context JSON.
 * Used by the execution viewer and builder approval side panels.
 *
 * Layout (top→bottom): Approve/Reject → summary fields → message → JSON block.
 */
export function ApprovalDetailContent({
  approval,
  message,
  activityNameMap,
  onDecisionSubmitted,
  onWorkflowClick,
}: ApprovalDetailContentProps) {
  const { showSuccess } = useAlerts()
  const queryClient = useQueryClient()
  const decisionMutation = approvalsClient.useMutation('patch', '/approvals/{approval_id}')
  const handleError = useMutationErrorHandler()

  // Get project list to map project_id to project name for permission check
  const { projects } = useProjectSelector()

  // Check RBAC permissions (global + project-scoped)
  const {
    canDecideAllProjects,
    canDecideProjectNames,
    isLoading: isLoadingDecideProjects,
  } = useApprovalDecideProjects()
  const hasRbacPermission = canDecideOnApproval(approval, canDecideAllProjects, canDecideProjectNames, projects)

  // Check approver list membership
  const { canDecide: canDecideBasedOnApproverList, isLoading: isCheckingApproverList } = useCanDecideApproval(approval)

  // User can decide if they have BOTH RBAC permission AND are in approver list
  const canDecide = hasRbacPermission && canDecideBasedOnApproverList
  const isCheckingPermission = isLoadingDecideProjects || isCheckingApproverList

  const [pendingDecision, setPendingDecision] = useState<'approved' | 'rejected' | undefined>(undefined)
  const [pendingReason, setPendingReason] = useState('')

  const approvalStatus = approval.status ?? 'pending'
  const isPending = approvalStatus === 'pending'
  const workflowName = approval.workflow_context?.workflow_name || 'Workflow'
  const workflowId = approval.workflow_context?.workflow_id
  const workflowVersion = approval.workflow_context?.workflow_version
  const workflowLink = workflowId ? buildWorkflowBuilderLink(workflowId, workflowVersion) : undefined
  const approvalMessage = getApprovalPromptFromRecord(approval) || message
  const approvalDisplayName = resolveApprovalName(approval, activityNameMap)
  const decisionNotes = approval.decision_notes ?? undefined
  const notesLabel = getNotesLabel(approvalStatus)
  const isSubmitting = decisionMutation.isPending
  const canSubmit = isPending && Boolean(pendingDecision) && !decisionMutation.isSuccess

  const handleSubmit = () => {
    if (!pendingDecision || !approval.id || isSubmitting) return

    decisionMutation.mutate(
      {
        params: { path: { approval_id: approval.id } },
        body: { status: pendingDecision, notes: pendingReason.trim() || null },
      },
      {
        onSuccess: async () => {
          showSuccess({
            title: pendingDecision === 'approved' ? 'Approval submitted' : 'Rejection submitted',
            description: 'The approval decision has been recorded.',
          })
          setPendingDecision(undefined)
          setPendingReason('')

          // Wait for queries to refetch before calling onDecisionSubmitted
          // This ensures the execution state and canvas update before we fetch the next approval
          await Promise.all([
            queryClient.refetchQueries({ queryKey: ['get', '/executions/{execution_id}'] }),
            queryClient.refetchQueries({ queryKey: ['get', '/approvals'] }),
            queryClient.refetchQueries({ queryKey: ['get', '/approvals/{approval_id}'] }),
          ])

          // Call onDecisionSubmitted without fresh approvals - let dismiss() fetch to avoid cache key issues
          // The race condition risk is minimal since we just did refetchQueries
          onDecisionSubmitted?.()
        },
        onError: handleError({ title: 'Failed to submit decision' }),
      }
    )
  }

  const renderDecisionActions = () => {
    if (!isPending) {
      return (
        <Stack hasGutter>
          <StackItem>
            <ApprovalStatusBadges status={approvalStatus} />
          </StackItem>
          {decisionNotes && (
            <DescriptionList>
              <DescriptionListGroup>
                <DescriptionListTerm>{notesLabel}</DescriptionListTerm>
                <DescriptionListDescription>{decisionNotes}</DescriptionListDescription>
              </DescriptionListGroup>
            </DescriptionList>
          )}
        </Stack>
      )
    }

    if (!pendingDecision) {
      const decideTooltip =
        getDecideTooltip({ canDecide: hasRbacPermission }, canDecideBasedOnApproverList, approval) ?? ''
      return (
        <DecisionButtons
          canDecide={canDecide}
          isCheckingPermission={isCheckingPermission}
          isSubmitting={isSubmitting}
          decideTooltip={decideTooltip}
          onApprove={() => setPendingDecision('approved')}
          onReject={() => setPendingDecision('rejected')}
        />
      )
    }

    return (
      <PendingDecisionForm
        pendingDecision={pendingDecision}
        pendingReason={pendingReason}
        isSubmitting={isSubmitting}
        onReasonChange={setPendingReason}
        onUndo={() => setPendingDecision(undefined)}
      />
    )
  }

  return (
    <Stack hasGutter className={styles.outerStack}>
      <StackItem>
        <Stack hasGutter>
          <StackItem>{renderDecisionActions()}</StackItem>
          {isPending && pendingDecision && (
            <StackItem>
              <Button isDisabled={!canSubmit} isLoading={isSubmitting} onClick={handleSubmit}>
                Submit decision
              </Button>
            </StackItem>
          )}
          <StackItem>
            <Divider />
          </StackItem>
        </Stack>
      </StackItem>

      <StackItem isFilled className={styles.scrollableBody}>
        <Stack hasGutter>
          <StackItem>
            <ApprovalSummary
              approvalDisplayName={approvalDisplayName}
              approvalInitiatedAt={approval.created_at}
              approvalMessage={approvalMessage}
              workflowName={workflowName}
              workflowLink={workflowLink}
              onWorkflowClick={onWorkflowClick}
            />
          </StackItem>
          <StackItem className={styles.codeBlockContainer}>
            <NxCodeBlock jsonObject={approval} enableCopy enableExpand expandTitle="Approval context" fillHeight />
          </StackItem>
        </Stack>
      </StackItem>
    </Stack>
  )
}
