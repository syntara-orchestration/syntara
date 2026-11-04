import {
  Alert,
  AlertActionLink,
  Button,
  Form,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from '@patternfly/react-core'
import { useEffect } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { SynForm } from '../../components/forms/SynForm'
import { SynTextAreaField } from '../../components/forms/SynTextAreaField'
import { SynTextField } from '../../components/forms/SynTextField'
import { useSynForm } from '../../hooks/useSynForm'

import { editVersionSchema } from './editVersionSchema'
import type { EditVersionFormData } from './editVersionSchema'
import stepFormStyles from './step-forms/shared/stepFormStyles.module.css'

type EditVersionDialogProps = Readonly<{
  isOpen: boolean
  isSaving: boolean
  onClose: () => void
  onSave: (publishName: string | null, changeDescription: string | null) => void
  initialName?: string | null
  initialDescription?: string | null
  canEdit?: boolean
  editTooltip?: string
  permissionCheckError?: boolean
  onRetryPermissionCheck?: () => void
}>

export function EditVersionDialog({
  isOpen,
  isSaving,
  onClose,
  onSave,
  initialName,
  initialDescription,
  canEdit = true,
  editTooltip,
  permissionCheckError = false,
  onRetryPermissionCheck,
}: EditVersionDialogProps) {
  const form = useSynForm({
    schema: editVersionSchema,
    defaultValues: { name: '', change_description: '' },
    onClose,
  })
  const { handleSubmit, handleClose, reset } = form

  useEffect(() => {
    if (isOpen) {
      reset({
        name: initialName ?? '',
        change_description: initialDescription ?? '',
      })
    }
  }, [isOpen, initialName, initialDescription, reset])

  const onSubmit = (data: EditVersionFormData) => {
    if (!canEdit) return
    const name = data.name?.trim()
    const desc = data.change_description?.trim()
    onSave(name || null, desc || null)
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small">
      <ModalHeader title="Edit version name and description" />
      <ModalBody>
        {permissionCheckError && (
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
            Version metadata is disabled until permissions can be checked.
          </Alert>
        )}
        <Form onSubmit={handleSubmit(onSubmit)} id="edit-version-form">
          <SynForm form={form}>
            <fieldset disabled={!canEdit} className={stepFormStyles.disabledFieldset} aria-label="Version metadata">
              <SynTextField name="name" label="Version name" fieldId="edit-version-name" ariaLabel="Version name" />
              <SynTextAreaField
                name="change_description"
                label="Description"
                fieldId="edit-version-description"
                placeholder="Describe what changed"
                rows={4}
                ariaLabel="Description"
              />
            </fieldset>
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <DisabledWithTooltip isDisabled={!canEdit} content={editTooltip ?? 'Step-type permission is required.'}>
          <Button
            variant="primary"
            type="submit"
            form="edit-version-form"
            isLoading={isSaving}
            isDisabled={isSaving || !canEdit}
          >
            Save version
          </Button>
        </DisabledWithTooltip>
        <Button variant="link" onClick={handleClose} isDisabled={isSaving}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
