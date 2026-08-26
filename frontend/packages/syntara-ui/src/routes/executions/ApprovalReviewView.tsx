import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Label,
  Stack,
  StackItem,
  TextArea,
  Title,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import type { Approval } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { Controller, useForm, useWatch } from 'react-hook-form'

import { approvalsClient } from '../../client'
import { NxCodeBlock } from '../../components/details/NxCodeBlock'
import { SynPanel } from '../../components/layout/SynPanel'
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import { lookupMapByApprovalNodeId } from '../approvals/approvalNodeId'
import { ApprovalSummaryList } from '../approvals/ApprovalSummaryList'
import { useApprovalPermissions } from '../approvals/useApprovalPermissions'
import { useCanDecideApproval } from '../approvals/useCanDecideApproval'

import { approvalDecisionSchema, type ApprovalDecisionFormData } from './approvalDecisionSchema'
import { ApprovalReadOnlyView } from './ApprovalReadOnlyView'

type NextStep = { id: string; name: string; type: string; parameters?: Record<string, unknown> }

function NextStepSummary({
  step,
  resolveName,
}: {
  step: NextStep
  resolveName: (id: string, fallback: string) => string
}) {
  const displayName = resolveName(step.id, step.name)
  const configEntries = step.parameters ? Object.entries(step.parameters).filter(([k]) => k !== 'name') : []

  return (
    <Stack hasGutter={false}>
      <StackItem>
        {displayName} <Label isCompact>{step.type}</Label>
      </StackItem>
      {configEntries.length > 0 && (
        <StackItem>
          <DescriptionList isCompact isHorizontal>
            {configEntries.map(([key, value]) => {
              let display = ''
              if (value != null) {
                display = typeof value === 'string' ? value : JSON.stringify(value)
              }
              return (
                <DescriptionListGroup key={key}>
                  <DescriptionListTerm>{key}</DescriptionListTerm>
                  <DescriptionListDescription>{display}</DescriptionListDescription>
                </DescriptionListGroup>
              )
            })}
          </DescriptionList>
        </StackItem>
      )}
    </Stack>
  )
}

type ApprovalReviewViewProps = {
  approval: Approval
  /** Maps activity IDs to human-readable names from the workflow definition. */
  activityNameMap?: Map<string, string>
  onClose: () => void
}

export function ApprovalReviewView({ approval, activityNameMap, onClose }: ApprovalReviewViewProps) {
  const { showSuccess } = useAlerts()
  const queryClient = useQueryClient()
  const decisionMutation = approvalsClient.useMutation('patch', '/approvals/{approval_id}')

  // SECURITY: Client-side checks for UX only - disable controls for unauthorized users
  // Backend ALWAYS validates and returns 403 via ApprovalService._is_user_authorized_approver()

  // Check 1: RBAC permission check (approval:decide)
  const permissions = useApprovalPermissions(approval.project_id)

  // Check 2: Approver list check (user is in approver_users or approver_groups)
  const { canDecide: canDecideBasedOnApproverList, isLoading: isCheckingApproverList } = useCanDecideApproval(approval)

  // User can decide only if BOTH checks pass
  const canDecide = permissions.canDecide && canDecideBasedOnApproverList
  const isCheckingPermissions = permissions.isChecking || isCheckingApproverList

  const {
    handleSubmit,
    setValue,
    setError,
    control,
    formState: { errors },
  } = useForm<ApprovalDecisionFormData>({
    resolver: zodResolver(approvalDecisionSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      status: 'approved',
      notes: '',
    },
  })

  const handleError = useFormMutationErrorHandler(setError)
  const currentStatus = useWatch({ control, name: 'status' })
  const approvalId = approval.id

  if (!approvalId) return null

  const onSubmit = (data: ApprovalDecisionFormData) => {
    decisionMutation.mutate(
      {
        params: { path: { approval_id: approvalId } },
        body: {
          status: data.status,
          notes: data.notes?.trim() || null,
        },
      },
      {
        onSuccess: () => {
          detachPromise(queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}'] }))
          detachPromise(queryClient.invalidateQueries({ queryKey: ['get', '/approvals'] }))
          showSuccess({
            title: data.status === 'approved' ? 'Approval submitted' : 'Rejection submitted',
            description: 'The approval decision has been recorded.',
          })
          onClose()
        },
        onError: handleError({ title: 'Failed to submit decision' }),
      }
    )
  }

  const {
    workflow_context: workflowContext,
    next_step_approved: nextStepApproved,
    next_step_rejected: nextStepRejected,
  } = approval

  const resolveName = (id: string, fallback: string) => lookupMapByApprovalNodeId(activityNameMap, id) ?? fallback
  const approvalNodeId = approval.approval_node_id
  const resolvedNodeName = lookupMapByApprovalNodeId(activityNameMap, approvalNodeId)
  const approvalDisplayName = resolvedNodeName ? `Approval for ${resolvedNodeName}` : approval.name

  // If user is not authorized, show read-only view with approver information
  if (!isCheckingPermissions && !canDecide) {
    const approverUsernames = approval.approver_users?.map((u) => u.username) ?? []
    const approverGroupNames = approval.approver_groups?.map((g) => g.name) ?? []
    return (
      <ApprovalReadOnlyView
        approval={approval}
        activityNameMap={activityNameMap}
        approverUsernames={approverUsernames}
        approverGroups={approverGroupNames}
        onClose={onClose}
      />
    )
  }

  return (
    <SynPanel isFullHeight style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Stack hasGutter style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <StackItem>
          <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
            <FlexItem>
              <Title headingLevel="h2">{approvalDisplayName}</Title>
            </FlexItem>
            <Flex gap={{ default: 'gapSm' }}>
              <Button variant="link" onClick={onClose}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleSubmit(onSubmit)}
                isLoading={decisionMutation.isPending}
                isDisabled={decisionMutation.isPending || isCheckingPermissions || !canDecide}
              >
                Submit decision
              </Button>
            </Flex>
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
                <NextStepSummary step={nextStepApproved} resolveName={resolveName} />
              </DescriptionListDescription>
            </DescriptionListGroup>
            <DescriptionListGroup>
              <DescriptionListTerm>If rejected</DescriptionListTerm>
              <DescriptionListDescription>
                {nextStepRejected ? (
                  <NextStepSummary step={nextStepRejected} resolveName={resolveName} />
                ) : (
                  'Workflow ends'
                )}
              </DescriptionListDescription>
            </DescriptionListGroup>
          </DescriptionList>
        </StackItem>

        <StackItem isFilled style={{ minHeight: 0, overflow: 'auto' }}>
          <Title headingLevel="h3">Approval context</Title>
          <NxCodeBlock jsonObject={approval} enableCopy />
        </StackItem>

        <StackItem style={{ flexShrink: 0 }}>
          <Title headingLevel="h3">Decision</Title>
          <Form>
            <FormGroup label="Action" isRequired role="group">
              <ToggleGroup aria-label="Approval decision">
                <ToggleGroupItem
                  text="Approve"
                  buttonId="approve-toggle"
                  isSelected={currentStatus === 'approved'}
                  onChange={() => setValue('status', 'approved')}
                  isDisabled={isCheckingPermissions || !canDecide}
                />
                <ToggleGroupItem
                  text="Reject"
                  buttonId="reject-toggle"
                  isSelected={currentStatus === 'rejected'}
                  onChange={() => setValue('status', 'rejected')}
                  isDisabled={isCheckingPermissions || !canDecide}
                />
              </ToggleGroup>
            </FormGroup>

            <FormGroup label="Notes" fieldId="approval-notes">
              <Controller
                name="notes"
                control={control}
                render={({ field }) => (
                  <TextArea
                    id="approval-notes"
                    aria-label="Decision notes"
                    placeholder="Explain the reason for your decision..."
                    validated={errors.notes ? 'error' : 'default'}
                    value={field.value}
                    onChange={(_event, value) => field.onChange(value)}
                    onBlur={field.onBlur}
                  />
                )}
              />
              {errors.notes && (
                <FormHelperText>
                  <HelperText>
                    <HelperTextItem variant="error">{errors.notes.message}</HelperTextItem>
                  </HelperText>
                </FormHelperText>
              )}
            </FormGroup>
          </Form>
        </StackItem>
      </Stack>
    </SynPanel>
  )
}
