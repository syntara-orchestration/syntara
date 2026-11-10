import {
  Alert,
  AlertActionLink,
  Button,
  Content,
  Form,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from '@patternfly/react-core'
import { format } from 'date-fns'
import { useEffect, type ReactNode } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { SynForm } from '../../components/forms/SynForm'
import { SynTextAreaField } from '../../components/forms/SynTextAreaField'
import { SynTextField } from '../../components/forms/SynTextField'
import { useSynForm } from '../../hooks/useSynForm'

import { publishWorkflowSchema } from './publishWorkflowSchema'
import type { PublishWorkflowFormData } from './publishWorkflowSchema'
import stepFormStyles from './step-forms/shared/stepFormStyles.module.css'

function getDefaultVersionName(): string {
  return format(new Date(), 'PPp')
}

type PublishWorkflowDialogProps = Readonly<{
  isOpen: boolean
  isPublishing: boolean
  onClose: () => void
  onPublish: (publishName?: string, description?: string) => void
  canPublish?: boolean
  editTooltip?: string
  permissionCheckError?: boolean
  permissionCheckLoading?: boolean
  blockedStepTypes?: string[]
  onRetryPermissionCheck?: () => void
}>

export function PublishWorkflowDialog({
  isOpen,
  isPublishing,
  onClose,
  onPublish,
  canPublish = true,
  editTooltip,
  permissionCheckError = false,
  permissionCheckLoading = false,
  blockedStepTypes = [],
  onRetryPermissionCheck,
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
    if (!canPublish) return
    const name = data.name.trim()
    const desc = data.description?.trim()
    onPublish(name || undefined, desc || undefined)
  }
  let permissionAlert: ReactNode = null
  if (permissionCheckError) {
    permissionAlert = (
      <Alert
        variant="danger"
        isInline
        title="Unable to check step-type permissions."
        actionLinks={
          onRetryPermissionCheck ? (
            <AlertActionLink onClick={onRetryPermissionCheck}>Retry permission check</AlertActionLink>
          ) : undefined
        }
      >
        Publishing is disabled until permissions can be checked.
      </Alert>
    )
  } else if (blockedStepTypes.length > 0) {
    permissionAlert = (
      <Alert variant="warning" isInline title="The selected version contains blocked step types.">
        Blocked step types: {blockedStepTypes.join(', ')}.
      </Alert>
    )
  } else if (permissionCheckLoading) {
    permissionAlert = <Alert variant="info" isInline title="Checking step-type permissions." />
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small" aria-label="Publish workflow">
      <ModalHeader title="Publish workflow?" />
      <ModalBody>
        {permissionAlert}
        <Content component="p" style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
          This will override any previously published workflow and your trigger step will now be able to trigger
          workflow runs. These triggered runs will happen in the background and can be viewed in run history. The
          previously published workflow can be viewed in version history.
        </Content>
        <Form onSubmit={handleSubmit(onSubmit)} id="publish-workflow-form">
          <SynForm form={form}>
            <fieldset disabled={!canPublish} className={stepFormStyles.disabledFieldset} aria-label="Version metadata">
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
            </fieldset>
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <DisabledWithTooltip isDisabled={!canPublish} content={editTooltip ?? 'Step-type permission is required.'}>
          <Button
            variant="primary"
            type="submit"
            form="publish-workflow-form"
            isLoading={isPublishing}
            isDisabled={isPublishing || !canPublish}
          >
            Publish workflow
          </Button>
        </DisabledWithTooltip>
        <Button variant="link" onClick={handleClose} isDisabled={isPublishing}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
