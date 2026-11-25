import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditIcon } from '@patternfly/react-icons'
import { useCallback, useId } from 'react'

import { credentialsClient } from '../../../../client'
import { SynErrorState } from '../../../../components/states/SynErrorState'
import { SynLoadingState } from '../../../../components/states/SynLoadingState'
import { useSynForm } from '../../../../hooks/useSynForm'
import { detachPromise } from '../../../../utils/detachPromise'
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
  /** Limits credential types when opened from a filtered CredentialSelector */
  compatibleTypeNames?: string[]
}

export function CredentialFormModal({
  isOpen,
  onClose,
  credentialToEdit,
  onSuccess,
  preSelectedTypeId,
  onCreated,
  defaultProjectId,
  compatibleTypeNames,
}: Readonly<CredentialFormModalProps>) {
  const isEditMode = Boolean(credentialToEdit)
  const title = isEditMode && credentialToEdit ? `Edit ${credentialToEdit.name}` : 'Create credential'
  const titleId = useId()

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
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium" aria-labelledby={titleId}>
      {isOpen && (
        <CredentialFormModalLoader
          key={credentialToEdit?.id ?? 'create'}
          form={form}
          isOpen={isOpen}
          credentialToEdit={credentialToEdit}
          isEditMode={isEditMode}
          preSelectedTypeId={preSelectedTypeId}
          onCreated={onCreated}
          defaultProjectId={defaultProjectId}
          compatibleTypeNames={compatibleTypeNames}
          onSuccess={onSuccess}
          title={title}
          titleId={titleId}
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
  compatibleTypeNames?: string[]
  onSuccess?: () => void
  title: string
  titleId: string
}

function CredentialFormModalLoader(props: Readonly<CredentialFormModalContentProps>) {
  if (!props.credentialToEdit) return <CredentialFormModalContent {...props} />
  return <CredentialEditFormLoader {...props} credentialToEdit={props.credentialToEdit} />
}

function CredentialEditFormLoader(props: Readonly<CredentialFormModalContentProps & { credentialToEdit: Credential }>) {
  const query = credentialsClient.useQuery('get', '/credentials/{credential_id}', {
    params: { path: { credential_id: props.credentialToEdit.id ?? '' } },
  })

  // Once mounted, the editor owns its draft. Background refetches must not
  // unmount it or replace the values it initialized from the first response.
  if (query.data) return <CredentialFormModalContent {...props} credentialToEdit={query.data} />

  return (
    <>
      <ModalHeader title={props.title} labelId={props.titleId} />
      <ModalBody>
        {query.isError ? (
          <SynErrorState
            title="Unable to load credential"
            message={query.error}
            onRetry={() => detachPromise(query.refetch())}
          />
        ) : (
          <SynLoadingState />
        )}
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" isDisabled>
          Save credential
        </Button>
        <Button variant="link" onClick={props.form.handleClose}>
          Cancel
        </Button>
      </ModalFooter>
    </>
  )
}

function CredentialFormModalContent({
  form,
  isOpen,
  credentialToEdit,
  isEditMode,
  preSelectedTypeId,
  onCreated,
  defaultProjectId,
  compatibleTypeNames,
  onSuccess,
  title,
  titleId,
}: Readonly<CredentialFormModalContentProps>) {
  const modalState = useCredentialFormModal({
    form,
    isOpen,
    credentialToEdit,
    isEditMode,
    preSelectedTypeId,
    defaultProjectId,
    compatibleTypeNames,
    onCreated,
    onSuccess,
  })

  const { handleSubmit, handleClose, onSubmit, onInvalidSubmit, isSubmitting, isMtlsIdentity } = modalState
  const isMtlsEdit = isEditMode && isMtlsIdentity
  const saveLabel = isMtlsEdit ? 'Save changes' : 'Save credential'
  const editIcon = isMtlsEdit ? <RhUiEditIcon /> : undefined

  // Explicit click submit (not form= association) so create works inside the builder
  // action-node-form without the outer form swallowing the footer submit.
  const handlePrimaryClick = useCallback(() => {
    detachPromise(handleSubmit(onSubmit, onInvalidSubmit)())
  }, [handleSubmit, onSubmit, onInvalidSubmit])

  return (
    <>
      <ModalHeader title={isMtlsEdit ? 'Edit credential' : title} labelId={titleId} />
      <ModalBody>
        <Form id={CREDENTIAL_FORM_ID} onSubmit={handleSubmit(onSubmit, onInvalidSubmit)}>
          <CredentialFormModalFields form={form} state={modalState} />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type="button"
          onClick={handlePrimaryClick}
          isDisabled={isSubmitting}
          isLoading={isSubmitting}
          icon={isEditMode ? editIcon : <RhUiAddIcon />}
        >
          {isEditMode ? saveLabel : 'Create credential'}
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isSubmitting}>
          Cancel
        </Button>
      </ModalFooter>
    </>
  )
}
