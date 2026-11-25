import { Alert, Button, Content, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'
import { format } from 'date-fns'
import { useEffect, type ReactNode } from 'react'

import { SynForm } from '../../components/forms/SynForm'
import { SynTextAreaField } from '../../components/forms/SynTextAreaField'
import { SynTextField } from '../../components/forms/SynTextField'
import { useSynForm } from '../../hooks/useSynForm'
import { useWorkflowUsedBy } from '../workflows/useWorkflowUsedBy'

import { OutputContractChangeSummary } from './components/OutputContractChangeSummary'
import { publishWorkflowSchema } from './publishWorkflowSchema'
import type { PublishWorkflowFormData } from './publishWorkflowSchema'

function getDefaultVersionName(): string {
  return format(new Date(), 'PPp')
}

type PublishImpactAlertProps = Readonly<{
  /** The dependency impact could not be verified (diff or affected-count query failed). */
  unverifiable: boolean
  /** The dependency impact is still being verified. */
  pending: boolean
  hasRemovedTriggers: boolean
  removedCount: number
  affectedByRemovalCount: number
  totalCount: number
}>

/**
 * One explanatory alert for the publish impact (Finding #3): can't-verify, checking, the
 * trigger-removal "N of M" warning, or the plain "used by M" info. Extracted from the dialog so
 * the dialog stays simple; returns null when there is nothing to say.
 */
function PublishImpactAlert({
  unverifiable,
  pending,
  hasRemovedTriggers,
  removedCount,
  affectedByRemovalCount,
  totalCount,
}: PublishImpactAlertProps): ReactNode {
  let alert: ReactNode = null
  if (unverifiable) {
    alert = (
      <Alert variant="warning" isInline title="Can't verify dependency impact">
        We couldn&apos;t check whether this publish affects workflows that use it as a sub-workflow. Try again in a
        moment.
      </Alert>
    )
  } else if (pending) {
    alert = <Alert variant="info" isInline isPlain title="Checking dependency impact…" />
  } else if (hasRemovedTriggers && affectedByRemovalCount > 0) {
    alert = (
      <Alert
        variant="warning"
        isInline
        title={`Removing the workflow trigger${removedCount > 1 ? 's' : ''} will affect ${affectedByRemovalCount} of ${totalCount} published ${totalCount === 1 ? 'workflow' : 'workflows'} using this workflow`}
      >
        <Content component="p">
          Those workflows will no longer be able to invoke this workflow through the removed trigger
          {removedCount > 1 ? 's' : ''}.
        </Content>
      </Alert>
    )
  } else if (!hasRemovedTriggers && totalCount > 0) {
    alert = (
      <Alert
        variant="info"
        isInline
        title={`${totalCount} published ${totalCount === 1 ? 'workflow uses' : 'workflows use'} this workflow as a sub-workflow`}
      >
        <Content component="p">Future sub-workflow runs will use this version.</Content>
      </Alert>
    )
  }

  if (!alert) return null
  return <div style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>{alert}</div>
}

type ContractChange = WorkflowAPI.components['schemas']['TriggerBreakingChanges']

type DerivePublishStateInput = Readonly<{
  triggerDiffLoading?: boolean
  triggerDiffError?: boolean
  hasRemovedTriggers: boolean
  usedByState: { isLoading: boolean; isError: boolean }
  triggerRemovalState: { isLoading: boolean; isError: boolean }
  breakingChanges: ContractChange[]
  contractChanges: ContractChange[]
  parentWorkflows: WorkflowAPI.components['schemas']['WorkflowReferenceRead'][]
}>

type PublishState = {
  blockPublish: boolean
  unverifiable: boolean
  impactPending: boolean
  hasBreakingChanges: boolean
  reviewedContractChanges: ContractChange[]
  requiresContractConfirmation: boolean
}

/**
 * Derive the dialog's gating flags (Findings #1-#3) from the trigger diff, the dependency-impact
 * queries and the output-contract review. Pure and extracted so the component stays simple.
 */
function derivePublishState({
  triggerDiffLoading,
  triggerDiffError,
  hasRemovedTriggers,
  usedByState,
  triggerRemovalState,
  breakingChanges,
  contractChanges,
  parentWorkflows,
}: DerivePublishStateInput): PublishState {
  const diffPending = !!triggerDiffLoading
  const diffError = !!triggerDiffError
  const removalImpactPending = hasRemovedTriggers && (triggerRemovalState.isLoading || usedByState.isLoading)
  const removalImpactError = hasRemovedTriggers && (triggerRemovalState.isError || usedByState.isError)
  const hasBreakingChanges = breakingChanges.length > 0
  const reviewedContractChanges = contractChanges.length > 0 ? contractChanges : breakingChanges
  return {
    blockPublish: diffPending || diffError || removalImpactPending || removalImpactError,
    unverifiable: diffError || removalImpactError,
    impactPending: diffPending || removalImpactPending,
    hasBreakingChanges,
    reviewedContractChanges,
    requiresContractConfirmation:
      hasBreakingChanges || (reviewedContractChanges.length > 0 && parentWorkflows.length > 0),
  }
}

type PublishWorkflowDialogProps = Readonly<{
  isOpen: boolean
  isPublishing: boolean
  onClose: () => void
  onPublish: (publishName?: string, description?: string, options?: { confirm?: boolean }) => void
  /** The workflow being published; enables the "used by published workflows" impact alert. */
  workflowId?: string
  /** Subworkflow Trigger node ids this publish would remove (builder only); drives the stronger warning. */
  removedTriggerNodeIds?: string[]
  /** True while the published-vs-draft trigger diff is still resolving (removal set not yet known). */
  triggerDiffLoading?: boolean
  /** True if the trigger diff could not be resolved (removal set unverified). */
  triggerDiffError?: boolean
  breakingChanges?: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  contractChanges?: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  parentWorkflows?: WorkflowAPI.components['schemas']['WorkflowReferenceRead'][]
  onConfirmContractChanges?: () => void
  onCancelBreakingChanges?: () => void
}>

export function PublishWorkflowDialog({
  isOpen,
  isPublishing,
  onClose,
  onPublish,
  workflowId,
  removedTriggerNodeIds,
  triggerDiffLoading,
  triggerDiffError,
  breakingChanges = [],
  contractChanges = [],
  parentWorkflows = [],
  onConfirmContractChanges,
  onCancelBreakingChanges,
}: PublishWorkflowDialogProps) {
  const form = useSynForm({
    schema: publishWorkflowSchema,
    defaultValues: { name: '', description: '' },
    onClose,
  })
  const { handleSubmit, handleClose, reset } = form

  useEffect(() => {
    if (isOpen) {
      reset({ name: getDefaultVersionName(), description: '' })
    }
  }, [isOpen, reset])

  const removedCount = removedTriggerNodeIds?.length ?? 0
  const hasRemovedTriggers = removedCount > 0

  const usedBy = useWorkflowUsedBy(workflowId, { enabled: isOpen })
  const totalCount = usedBy.totalCount

  const triggerRemoval = useWorkflowUsedBy(workflowId, {
    triggerNodeIds: removedTriggerNodeIds ?? [],
    enabled: isOpen && hasRemovedTriggers,
  })
  const affectedByRemovalCount = triggerRemoval.totalCount

  // Finding #1: never publish before the dependency impact is known. The trigger diff (did this
  // publish remove a trigger?) and the affected-count query must both resolve before Publish is
  // allowed; while they load we block, and on failure we block and say so, rather than submitting
  // confirm=false into a 409 the builder cannot recover from.
  const {
    blockPublish,
    unverifiable,
    impactPending,
    hasBreakingChanges,
    reviewedContractChanges,
    requiresContractConfirmation,
  } = derivePublishState({
    triggerDiffLoading,
    triggerDiffError,
    hasRemovedTriggers,
    usedByState: usedBy,
    triggerRemovalState: triggerRemoval,
    breakingChanges,
    contractChanges,
    parentWorkflows,
  })

  const onSubmit = (data: PublishWorkflowFormData) => {
    const name = data.name.trim()
    const desc = data.description?.trim()
    onPublish(name || undefined, desc || undefined, { confirm: affectedByRemovalCount > 0 })
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small" aria-label="Publish workflow">
      <ModalHeader title="Publish workflow?" />
      <ModalBody>
        <Content component="p" style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
          This will override any previously published workflow and your trigger step will now be able to trigger
          workflow runs. These triggered runs will happen in the background and can be viewed in run history. The
          previously published workflow can be viewed in version history.
        </Content>
        <PublishImpactAlert
          unverifiable={unverifiable}
          pending={impactPending}
          hasRemovedTriggers={hasRemovedTriggers}
          removedCount={removedCount}
          affectedByRemovalCount={affectedByRemovalCount}
          totalCount={totalCount}
        />
        {requiresContractConfirmation && (
          <Alert
            variant="warning"
            isInline
            title={hasBreakingChanges ? 'Breaking output contract changes' : 'Output contract changes'}
          >
            <Content component="p">
              Review the contract edits and any visible published parent workflows that reference this child.
            </Content>
            <OutputContractChangeSummary
              context="publish"
              contractChanges={reviewedContractChanges}
              parentWorkflows={parentWorkflows}
            />
          </Alert>
        )}
        <Form onSubmit={handleSubmit(onSubmit)} id="publish-workflow-form">
          <SynForm form={form}>
            <SynTextField name="name" label="Version name" fieldId="publish-name" isRequired ariaLabel="Version name" />
            <SynTextAreaField
              name="description"
              label="Description"
              fieldId="publish-description"
              placeholder="Describe what changed"
              rows={4}
              ariaLabel="Description"
            />
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type={requiresContractConfirmation ? 'button' : 'submit'}
          form={requiresContractConfirmation ? undefined : 'publish-workflow-form'}
          onClick={requiresContractConfirmation ? onConfirmContractChanges : undefined}
          isLoading={isPublishing}
          isDisabled={isPublishing || blockPublish}
        >
          {hasBreakingChanges ? 'Publish anyway' : 'Publish workflow'}
        </Button>
        <Button
          variant="link"
          onClick={() => {
            onCancelBreakingChanges?.()
            handleClose()
          }}
          isDisabled={isPublishing}
        >
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
