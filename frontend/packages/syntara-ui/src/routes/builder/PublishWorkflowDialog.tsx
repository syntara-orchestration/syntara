import {
  Alert,
  Button,
  Content,
  Form,
  List,
  ListItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'
import { format } from 'date-fns'
import { useEffect } from 'react'

import { SynForm } from '../../components/forms/SynForm'
import { SynTextAreaField } from '../../components/forms/SynTextAreaField'
import { SynTextField } from '../../components/forms/SynTextField'
import { useSynForm } from '../../hooks/useSynForm'

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
  onConfirmBreakingChanges?: () => void
  onCancelBreakingChanges?: () => void
}>

export function PublishWorkflowDialog({
  isOpen,
  isPublishing,
  onClose,
  onPublish,
  breakingChanges = [],
  onConfirmBreakingChanges,
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

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small" aria-label="Publish workflow">
      <ModalHeader title="Publish workflow?" />
      <ModalBody>
        <Content component="p" style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
          This will override any previously published workflow and your trigger step will now be able to trigger
          workflow runs. These triggered runs will happen in the background and can be viewed in run history. The
          previously published workflow can be viewed in version history.
        </Content>
        {hasBreakingChanges && (
          <Alert variant="warning" isInline title="Breaking output contract changes">
            <Content component="p">
              Parent workflows may rely on these outputs. Review the changes before publishing.
            </Content>
            {breakingChanges.map((trigger) => (
              <section key={trigger.trigger_id}>
                <Content component="h4">{trigger.trigger_name || trigger.trigger_id}</Content>
                <List isPlain>
                  {trigger.changes.map((change) => (
                    <ListItem key={`${change.change_type}-${change.field_path}`}>{change.description}</ListItem>
                  ))}
                </List>
              </section>
            ))}
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
          type={hasBreakingChanges ? 'button' : 'submit'}
          form={hasBreakingChanges ? undefined : 'publish-workflow-form'}
          onClick={hasBreakingChanges ? onConfirmBreakingChanges : undefined}
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
