import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { useEffect } from 'react'

import { SynForm } from '../../components/forms/SynForm'
import { SynTextAreaField } from '../../components/forms/SynTextAreaField'
import { SynTextField } from '../../components/forms/SynTextField'
import { useSynForm } from '../../hooks/useSynForm'

import { editVersionSchema } from './editVersionSchema'
import type { EditVersionFormData } from './editVersionSchema'

type EditVersionDialogProps = Readonly<{
  isOpen: boolean
  isSaving: boolean
  onClose: () => void
  onSave: (publishName: string | null, changeDescription: string | null) => void
  initialName?: string | null
  initialDescription?: string | null
}>

export function EditVersionDialog({
  isOpen,
  isSaving,
  onClose,
  onSave,
  initialName,
  initialDescription,
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
    const name = data.name?.trim()
    const desc = data.change_description?.trim()
    onSave(name || null, desc || null)
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small">
      <ModalHeader title="Edit version name and description" />
      <ModalBody>
        <Form onSubmit={handleSubmit(onSubmit)} id="edit-version-form">
          <SynForm form={form}>
            <SynTextField name="name" label="Version name" fieldId="edit-version-name" ariaLabel="Version name" />
            <SynTextAreaField
              name="change_description"
              label="Description"
              fieldId="edit-version-description"
              placeholder="Describe what changed"
              rows={4}
              ariaLabel="Description"
            />
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" type="submit" form="edit-version-form" isLoading={isSaving} isDisabled={isSaving}>
          Save version
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isSaving}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
