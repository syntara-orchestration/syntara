/**
 * Read-only approval view shown to unauthorized users in execution details.
 *
 * Displays approval context and shows who IS authorized to approve (users/groups),
 * providing actionable information instead of just disabled controls.
 *
 * Used by ApprovalReviewView when useCanDecideApproval returns false.
 */

import {
  Alert,
  Button,
  Content,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  Label,
  Stack,
  StackItem,
  Title,
} from '@patternfly/react-core'
import type { Approval } from '@syntara/contracts'

import { NxCodeBlock } from '../../components/details/NxCodeBlock'
import { SynPanel } from '../../components/layout/SynPanel'
import { ApprovalSummaryList } from '../approvals/ApprovalSummaryList'

import styles from './ApprovalReadOnlyView.module.css'

type NextStep = { id: string; name: string; type: string; config?: Record<string, unknown> }

function NextStepLabel({
  step,
  resolveName,
}: Readonly<{
  step: NextStep
  resolveName: (id: string, fallback: string) => string
}>) {
  const displayName = resolveName(step.id, step.name)
  return (
    <Content component="p">
      {displayName} <Label isCompact>{step.type}</Label>
    </Content>
  )
}

type ApprovalReadOnlyViewProps = Readonly<{
  approval: Approval
  activityNameMap?: ReadonlyMap<string, string>
  approverUsernames: readonly string[]
  approverGroups: readonly string[]
  onClose: () => void
}>

export function ApprovalReadOnlyView({
  approval,
  activityNameMap,
  approverUsernames,
  approverGroups,
  onClose,
}: ApprovalReadOnlyViewProps) {
  const {
    workflow_context: workflowContext,
    next_step_approved: nextStepApproved,
    next_step_rejected: nextStepRejected,
  } = approval

  const resolveName = (id: string, fallback: string) => activityNameMap?.get(id) ?? fallback
  const approvalNodeId = approval.approval_node_id
  const resolvedNodeName = approvalNodeId ? activityNameMap?.get(approvalNodeId) : undefined
  const approvalDisplayName = resolvedNodeName ? `Approval for ${resolvedNodeName}` : approval.name

  const approverSummaryParts: string[] = []
  if (approverUsernames.length > 0) {
    approverSummaryParts.push(`Users: ${approverUsernames.join(', ')}`)
  }
  if (approverGroups.length > 0) {
    approverSummaryParts.push(`Groups: ${approverGroups.join(', ')}`)
  }

  return (
    <SynPanel isFullHeight className={styles.panel}>
      <Stack hasGutter className={styles.stack}>
        <StackItem>
          <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
            <FlexItem>
              <Title headingLevel="h2">{approvalDisplayName}</Title>
            </FlexItem>
            <Button variant="link" onClick={onClose}>
              Close
            </Button>
          </Flex>
        </StackItem>

        <StackItem>
          <ApprovalSummaryList workflowName={workflowContext.workflow_name} approvalInitiatedAt={approval.created_at} />
        </StackItem>

        <StackItem>
          <Title headingLevel="h3">Next steps</Title>
          <DescriptionList isAutoColumnWidths columnModifier={{ default: '2Col' }}>
            <DescriptionListGroup>
              <DescriptionListTerm>If approved</DescriptionListTerm>
              <DescriptionListDescription>
                <NextStepLabel step={nextStepApproved} resolveName={resolveName} />
              </DescriptionListDescription>
            </DescriptionListGroup>
            <DescriptionListGroup>
              <DescriptionListTerm>If rejected</DescriptionListTerm>
              <DescriptionListDescription>
                {nextStepRejected ? (
                  <NextStepLabel step={nextStepRejected} resolveName={resolveName} />
                ) : (
                  'Workflow ends'
                )}
              </DescriptionListDescription>
            </DescriptionListGroup>
          </DescriptionList>
        </StackItem>

        <StackItem isFilled className={styles.scrollContent}>
          <Title headingLevel="h3">Approval context</Title>
          <NxCodeBlock jsonObject={approval} enableCopy />
        </StackItem>

        {(approverUsernames.length > 0 || approverGroups.length > 0) && (
          <StackItem className={styles.alertContainer}>
            <Alert variant="info" isInline isPlain title="You are not authorized to approve or reject this request">
              <Content component="p">This approval is restricted to: {approverSummaryParts.join('; ')}</Content>
            </Alert>
          </StackItem>
        )}
      </Stack>
    </SynPanel>
  )
}
