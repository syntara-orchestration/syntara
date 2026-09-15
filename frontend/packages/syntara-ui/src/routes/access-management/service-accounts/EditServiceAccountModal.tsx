import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import { Controller, useForm } from 'react-hook-form'

import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
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

  const { control, handleSubmit, setError } = useForm<EditServiceAccountFormData>({
    resolver: zodResolver(editServiceAccountSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: serviceAccount.name,
      description: serviceAccount.description ?? '',
    },
  })

  const handleError = useFormMutationErrorHandler<EditServiceAccountFormData>(setError)

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
          onClose()
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
          <Controller
            name="name"
            control={control}
            render={({ field, fieldState }) => (
              <FormGroup label="Name" fieldId="edit-sa-name" isRequired labelHelp={serviceAccountHelp.name}>
                <TextInput
                  id="edit-sa-name"
                  aria-label="Name"
                  placeholder="my-service-account"
                  validated={fieldState.error ? 'error' : 'default'}
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  name={field.name}
                />
                {fieldState.error && (
                  <FormHelperText>
                    <HelperText>
                      <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                        {fieldState.error.message}
                      </HelperTextItem>
                    </HelperText>
                  </FormHelperText>
                )}
              </FormGroup>
            )}
          />
          <Controller
            name="description"
            control={control}
            render={({ field, fieldState }) => (
              <FormGroup label="Description" fieldId="edit-sa-description" labelHelp={serviceAccountHelp.description}>
                <TextArea
                  id="edit-sa-description"
                  aria-label="Description"
                  placeholder="Describe the purpose of this service account"
                  validated={fieldState.error ? 'error' : 'default'}
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  name={field.name}
                  rows={3}
                />
                {fieldState.error && (
                  <FormHelperText>
                    <HelperText>
                      <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                        {fieldState.error.message}
                      </HelperTextItem>
                    </HelperText>
                  </FormHelperText>
                )}
              </FormGroup>
            )}
          />
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
          Save service account
        </Button>
        <Button variant="link" onClick={onClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </>
  )
}
