import {
  Alert,
  Button,
  Content,
  Form,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'
import { format } from 'date-fns'
import { useEffect } from 'react'

import { SynForm } from '../../components/forms/SynForm'
import { SynTextAreaField } from '../../components/forms/SynTextAreaField'
import { SynTextField } from '../../components/forms/SynTextField'
import { useSynForm } from '../../hooks/useSynForm'

import { OutputContractChangeSummary } from './components/OutputContractChangeSummary'
import { publishWorkflowSchema } from './publishWorkflowSchema'
import type { PublishWorkflowFormData } from './publishWorkflowSchema'

function getDefaultVersionName(): string {
  return format(new Date(), 'PPp')
}

function getPublishButtonLabel(hasBreakingChanges: boolean, requiresContractConfirmation: boolean): string {
  if (hasBreakingChanges) return 'Publish anyway'
  if (requiresContractConfirmation) return 'Publish with changes'
  return 'Publish workflow'
}

type PublishWorkflowDialogProps = Readonly<{
  isOpen: boolean
  isPublishing: boolean
  isCheckingContractChanges?: boolean
  isPublishDisabled?: boolean
  hasContractReviewError?: boolean
  onRetryContractReview?: () => void
  onClose: () => void
  onPublish: (publishName?: string, description?: string) => void
  breakingChanges?: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  contractChanges?: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  parentWorkflows?: WorkflowAPI.components['schemas']['WorkflowReferenceRead'][]
  onConfirmContractChanges?: (publishName?: string, description?: string) => void
  onCancelBreakingChanges?: () => void
}>

export function PublishWorkflowDialog({
  isOpen,
  isPublishing,
  isCheckingContractChanges = false,
  isPublishDisabled = false,
  hasContractReviewError = false,
  onRetryContractReview,
  onClose,
  onPublish,
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

  const onSubmit = (data: PublishWorkflowFormData) => {
    const name = data.name.trim()
    const desc = data.description?.trim()
    if (requiresContractConfirmation && onConfirmContractChanges) {
      onConfirmContractChanges(name || undefined, desc || undefined)
      return
    }
    onPublish(name || undefined, desc || undefined)
  }
  const hasBreakingChanges = breakingChanges.length > 0
  const reviewedContractChanges = contractChanges.length > 0 ? contractChanges : breakingChanges
  const requiresContractConfirmation = hasBreakingChanges || reviewedContractChanges.length > 0
  const publishButtonLabel = getPublishButtonLabel(hasBreakingChanges, requiresContractConfirmation)

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small" aria-label="Publish workflow">
      <ModalHeader title="Publish workflow?" />
      <ModalBody>
        <Stack hasGutter>
          <StackItem>
            <Content component="p">
              This will override any previously published workflow and your trigger step will now be able to trigger
              workflow runs. These triggered runs will happen in the background and can be viewed in run history. The
              previously published workflow can be viewed in version history.
            </Content>
          </StackItem>
          {requiresContractConfirmation && (
            <StackItem>
              <Alert
                variant="warning"
                isInline
                component="h2"
                title={hasBreakingChanges ? 'Breaking output contract changes' : 'Output contract changes'}
              >
                <OutputContractChangeSummary
                  context="publish"
                  contractChanges={reviewedContractChanges}
                  breakingChanges={breakingChanges}
                  hasBreakingChanges={hasBreakingChanges}
                  parentWorkflows={parentWorkflows}
                />
              </Alert>
            </StackItem>
          )}
          {isCheckingContractChanges && (
            <StackItem>
              <Alert variant="info" isInline component="h2" title="Checking published parent impact">
                Checking how this version may change the outputs used by published parent workflows.
              </Alert>
            </StackItem>
          )}
          {hasContractReviewError && (
            <StackItem>
              <Alert variant="warning" isInline component="h2" title="Unable to verify output contract changes">
                <Content component="p">Retry the check before publishing.</Content>
                {onRetryContractReview && (
                  <Button
                    variant="link"
                    type="button"
                    onClick={onRetryContractReview}
                    isDisabled={isPublishing || isCheckingContractChanges}
                  >
                    Retry check
                  </Button>
                )}
              </Alert>
            </StackItem>
          )}
          <StackItem>
            <Form onSubmit={handleSubmit(onSubmit)} id="publish-workflow-form">
              <SynForm form={form}>
                <SynTextField
                  name="name"
                  label="Version name"
                  fieldId="publish-name"
                  isRequired
                  ariaLabel="Version name"
                />
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
          </StackItem>
        </Stack>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type="submit"
          form="publish-workflow-form"
          isLoading={isPublishing}
          isDisabled={isPublishing || isCheckingContractChanges || isPublishDisabled || hasContractReviewError}
        >
          {publishButtonLabel}
        </Button>
        <Button
          variant="link"
          onClick={() => {
            onCancelBreakingChanges?.()
            handleClose()
          }}
          isDisabled={isPublishing || isCheckingContractChanges}
        >
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
