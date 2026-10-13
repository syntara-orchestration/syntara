import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'

import { useSynForm } from '../../../../hooks/useSynForm'
import type { Credential } from '../credentialConstants'

import { CredentialFormModalFields } from './CredentialFormModalFields'
import { credentialFormSchema } from './credentialFormSchema'
import { useCredentialFormModal } from './useCredentialFormModal'

const CREDENTIAL_FORM_ID = 'credential-form-modal'

type CredentialFormModalProps = {
  isOpen: boolean
  onClose: () => void
  credentialToEdit?: Credential | null
  onSuccess?: () => void
  /** When provided, pre-selects the credential type and disables the type dropdown */
  preSelectedTypeId?: string
  /** Called with the new credential's ID on successful creation */
  onCreated?: (credentialId: string) => void
  /** When provided, pre-selects the project in the Project dropdown */
  defaultProjectId?: string
}

export function CredentialFormModal({
  isOpen,
  onClose,
  credentialToEdit,
  onSuccess,
  preSelectedTypeId,
  onCreated,
  defaultProjectId,
}: Readonly<CredentialFormModalProps>) {
  const isEditMode = Boolean(credentialToEdit)
  const title = isEditMode && credentialToEdit ? `Edit ${credentialToEdit.name}` : 'Create credential'

  const form = useSynForm({
    schema: credentialFormSchema,
    defaultValues: {
      name: '',
      description: '',
      project_id: '',
      credential_type_id: '',
      inputs: {},
    },
    onClose,
  })
  const { handleClose } = form

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium">
      <ModalHeader title={title} />
      {isOpen && (
        <CredentialFormModalContent
          form={form}
          isOpen={isOpen}
          credentialToEdit={credentialToEdit}
          isEditMode={isEditMode}
          preSelectedTypeId={preSelectedTypeId}
          onCreated={onCreated}
          defaultProjectId={defaultProjectId}
          onSuccess={onSuccess}
        />
      )}
    </Modal>
  )
}

type CredentialFormModalContentProps = {
  form: ReturnType<typeof useSynForm<import('./credentialFormSchema').CredentialFormData>>
  isOpen: boolean
  credentialToEdit?: Credential | null
  isEditMode: boolean
  preSelectedTypeId?: string
  onCreated?: (credentialId: string) => void
  defaultProjectId?: string
  onSuccess?: () => void
}

function CredentialFormModalContent({
  form,
  isOpen,
  credentialToEdit,
  isEditMode,
  preSelectedTypeId,
  onCreated,
  defaultProjectId,
  onSuccess,
}: Readonly<CredentialFormModalContentProps>) {
  const modalState = useCredentialFormModal({
    form,
    isOpen,
    credentialToEdit,
    isEditMode,
    preSelectedTypeId,
    defaultProjectId,
    onCreated,
    onSuccess,
  })

  const { handleSubmit, handleClose, onSubmit, isSubmitting } = modalState

  return (
    <>
      <ModalBody>
        <Form id={CREDENTIAL_FORM_ID} onSubmit={handleSubmit(onSubmit)}>
          <CredentialFormModalFields form={form} state={modalState} />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type="submit"
          form={CREDENTIAL_FORM_ID}
          isDisabled={isSubmitting}
          isLoading={isSubmitting}
          icon={isEditMode ? undefined : <RhUiAddIcon />}
        >
          {isEditMode ? 'Save credential' : 'Create credential'}
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isSubmitting}>
          Cancel
        </Button>
      </ModalFooter>
    </>
  )
}
