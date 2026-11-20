import { Alert, Button, Content, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
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

type PublishWorkflowDialogProps = Readonly<{
  isOpen: boolean
  isPublishing: boolean
  isCheckingContractChanges?: boolean
  isPublishDisabled?: boolean
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

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small" aria-label="Publish workflow">
      <ModalHeader title="Publish workflow?" />
      <ModalBody>
        <Content component="p" style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
          This will override any previously published workflow and your trigger step will now be able to trigger
          workflow runs. These triggered runs will happen in the background and can be viewed in run history. The
          previously published workflow can be viewed in version history.
        </Content>
        {requiresContractConfirmation && (
          <Alert
            variant="warning"
            isInline
            title={hasBreakingChanges ? 'Breaking output contract changes' : 'Output contract changes'}
          >
            <Content component="p">Review the impact on parent workflows before publishing this version.</Content>
            <OutputContractChangeSummary
              context="publish"
              contractChanges={reviewedContractChanges}
              parentWorkflows={parentWorkflows}
            />
          </Alert>
        )}
        {isCheckingContractChanges && (
          <Alert variant="info" isInline title="Checking published parent impact">
            Checking how this version may change the outputs used by published parent workflows.
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
          type="submit"
          form="publish-workflow-form"
          isLoading={isPublishing}
          isDisabled={isPublishing || isCheckingContractChanges || isPublishDisabled}
        >
          {requiresContractConfirmation ? 'Publish anyway' : 'Publish workflow'}
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
