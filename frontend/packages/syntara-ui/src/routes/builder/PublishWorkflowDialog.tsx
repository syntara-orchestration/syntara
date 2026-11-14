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
  onClose: () => void
  onPublish: (publishName?: string, description?: string) => void
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
    onPublish(name || undefined, desc || undefined)
  }
  const hasBreakingChanges = breakingChanges.length > 0
  const reviewedContractChanges = contractChanges.length > 0 ? contractChanges : breakingChanges
  const requiresContractConfirmation =
    hasBreakingChanges || (reviewedContractChanges.length > 0 && parentWorkflows.length > 0)

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
            <Content component="p">
              Review the contract edits and the published parent workflows that reference it.
            </Content>
            <OutputContractChangeSummary contractChanges={reviewedContractChanges} parentWorkflows={parentWorkflows} />
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
          isDisabled={isPublishing}
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
