import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { useEffect } from 'react'

import { SynForm } from '../../../components/forms/SynForm'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'

import { serviceAccountHelp } from './serviceAccountFieldHelp'
import { editServiceAccountSchema, type EditServiceAccountFormData } from './serviceAccountFormSchema'
import type { ServiceAccountRead } from './serviceAccountTypes'

type EditServiceAccountModalProps = {
  serviceAccount: ServiceAccountRead
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

export function EditServiceAccountModal({
  serviceAccount,
  isOpen,
  onClose,
  onSuccess,
}: Readonly<EditServiceAccountModalProps>) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="medium">
      <ModalHeader title={`Edit ${serviceAccount.name}`} />
      {isOpen && <EditServiceAccountForm serviceAccount={serviceAccount} onClose={onClose} onSuccess={onSuccess} />}
    </Modal>
  )
}

type EditServiceAccountFormProps = {
  serviceAccount: ServiceAccountRead
  onClose: () => void
  onSuccess: () => void
}

function EditServiceAccountForm({ serviceAccount, onClose, onSuccess }: Readonly<EditServiceAccountFormProps>) {
  const { showSuccess } = useAlerts()

  const form = useSynForm({
    schema: editServiceAccountSchema,
    defaultValues: {
      name: serviceAccount.name,
      description: serviceAccount.description ?? '',
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose, reset } = form

  useEffect(() => {
    reset({
      name: serviceAccount.name,
      description: serviceAccount.description ?? '',
    })
  }, [serviceAccount, reset])

  const { mutate: updateServiceAccount, isPending } = accessClient.useMutation(
    'patch',
    '/service_accounts/{service_account_id}'
  )

  const onSubmit = (formData: EditServiceAccountFormData) => {
    updateServiceAccount(
      {
        params: { path: { service_account_id: serviceAccount.id } },
        body: {
          name: formData.name,
          description: formData.description ?? undefined,
        },
      },
      {
        onSuccess: () => {
          showSuccess({
            title: 'Service account updated',
            description: `Service account "${formData.name}" has been updated successfully.`,
          })
          handleClose()
          onSuccess()
        },
        onError: handleError({
          title: 'Failed to update service account',
          context: formData.name,
        }),
      }
    )
  }

  return (
    <>
      <ModalBody>
        <Form id="edit-service-account-form" onSubmit={handleSubmit(onSubmit)}>
          <SynForm form={form}>
            <SynTextField
              name="name"
              label="Name"
              fieldId="edit-sa-name"
              isRequired
              placeholder="my-service-account"
              labelHelp={serviceAccountHelp.name}
            />
            <SynTextAreaField
              name="description"
              label="Description"
              fieldId="edit-sa-description"
              placeholder="Describe the purpose of this service account"
              rows={3}
              labelHelp={serviceAccountHelp.description}
            />
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type="submit"
          form="edit-service-account-form"
          isDisabled={isPending}
          isLoading={isPending}
        >
          Save
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </>
  )
}
