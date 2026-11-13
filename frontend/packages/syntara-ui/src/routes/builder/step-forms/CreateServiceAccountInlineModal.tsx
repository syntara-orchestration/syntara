import {
  Alert,
  Button,
  Checkbox,
  ClipboardCopy,
  Form,
  FormGroup,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useCallback, useEffect } from 'react'

import { SynForm } from '../../../components/forms/SynForm'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'
import { formatExpirationDate } from '../../../utils/dateUtils'
import { detachPromise } from '../../../utils/detachPromise'
import { CredentialExpirationField } from '../../access-management/service-accounts/CredentialExpirationField'
import {
  createServiceAccountSchema,
  SERVICE_ACCOUNT_NAME_HINT,
  type CreateServiceAccountFormData,
} from '../../access-management/service-accounts/serviceAccountFormSchema'
import { useCredentialExpirationDate } from '../../access-management/service-accounts/useCredentialExpirationDate'

import { type CredentialInfo, useCreateServiceAccountInline } from './useCreateServiceAccountInline'

export function CredentialRevealBody({ credentials }: Readonly<{ credentials: CredentialInfo }>) {
  return (
    <>
      <Alert variant="warning" isInline title="Save these credentials now">
        The client secret will not be shown again. Copy and store it securely before closing this dialog.
      </Alert>
      <FormGroup label="Client ID" fieldId="sa-inline-identifier">
        <ClipboardCopy isReadOnly textAriaLabel="Client ID" hoverTip="Copy" clickTip="Copied">
          {credentials.identifier}
        </ClipboardCopy>
      </FormGroup>
      <FormGroup label="Client secret" fieldId="sa-inline-secret">
        <ClipboardCopy isReadOnly textAriaLabel="Client secret" hoverTip="Copy" clickTip="Copied">
          {credentials.client_secret}
        </ClipboardCopy>
      </FormGroup>
      {credentials.expiresAt && (
        <FormGroup label="Expires" fieldId="sa-inline-expires-at">
          <TextInput
            id="sa-inline-expires-at"
            value={formatExpirationDate(credentials.expiresAt)}
            readOnlyVariant="plain"
          />
        </FormGroup>
      )}
      <Alert variant="info" isInline title="Next step">
        Assign roles to this service account later in Access Management to grant it permissions.
      </Alert>
    </>
  )
}

function CreateFormBody() {
  return (
    <>
      <SynTextField
        name="name"
        label="Name"
        fieldId="sa-inline-name"
        isRequired
        placeholder="my-service-account"
        hint={SERVICE_ACCOUNT_NAME_HINT}
      />
      <SynTextAreaField
        name="description"
        label="Description"
        fieldId="sa-inline-description"
        placeholder="Describe the purpose of this service account"
        rows={3}
      />
    </>
  )
}

type Props = Readonly<{
  isOpen: boolean
  onClose: () => void
  onCreated: (saId: string) => void
  projectId?: string
}>

export function CreateServiceAccountInlineModal({ isOpen, onClose, onCreated, projectId }: Props) {
  const {
    value: expiresAt,
    error: expirationError,
    handleChange: handleExpirationChange,
    validator: expirationValidator,
    helperText: expirationHelperText,
    validate: validateExpirationDate,
    reset: resetExpirationDate,
  } = useCredentialExpirationDate()

  const form = useSynForm({
    schema: createServiceAccountSchema,
    defaultValues: { name: '', description: '' },
  })
  const { handleSubmit, handleError, reset } = form

  useEffect(() => {
    if (isOpen) {
      reset({ name: '', description: '' })
    }
  }, [isOpen, reset])

  const { credentials, savedAck, setSavedAck, isPending, submitForm, resetState, showCredentials } =
    useCreateServiceAccountInline(expiresAt, projectId)

  const handleClose = useCallback(() => {
    const saId = resetState()
    reset({ name: '', description: '' })
    resetExpirationDate()
    onClose()
    if (saId) onCreated(saId)
  }, [resetState, onClose, onCreated, reset, resetExpirationDate])

  const onSubmit = useCallback(
    async (formData: CreateServiceAccountFormData) => {
      await submitForm(formData, handleError)
    },
    [submitForm, handleError]
  )

  const handleCreateClick = useCallback(() => {
    if (!validateExpirationDate()) {
      return
    }
    detachPromise(handleSubmit(onSubmit)())
  }, [validateExpirationDate, handleSubmit, onSubmit])

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium">
      <ModalHeader title={showCredentials ? 'Service account created' : 'Create service account'} />
      <ModalBody>
        <Form onSubmit={(e) => e.preventDefault()}>
          {showCredentials && credentials ? (
            <>
              <CredentialRevealBody credentials={credentials} />
              <Checkbox
                id="sa-inline-saved-ack"
                label="I have saved the credentials"
                isChecked={savedAck}
                onChange={(_event, checked) => setSavedAck(checked)}
              />
            </>
          ) : (
            <>
              <SynForm form={form}>
                <CreateFormBody />
              </SynForm>
              <CredentialExpirationField
                selectedDate={expiresAt}
                onDateChange={handleExpirationChange}
                dateError={expirationError}
                validator={expirationValidator}
                helperText={expirationHelperText}
                label="Credential expiration date"
                fieldId="sa-inline-expires-at"
              />
            </>
          )}
        </Form>
      </ModalBody>
      <ModalFooter>
        {showCredentials ? (
          <Button variant="primary" isDisabled={!savedAck} onClick={handleClose}>
            Close
          </Button>
        ) : (
          <>
            <Button
              variant="primary"
              onClick={handleCreateClick}
              isDisabled={isPending}
              isLoading={isPending}
              icon={<RhUiAddIcon />}
            >
              Create service account
            </Button>
            <Button variant="link" onClick={handleClose} isDisabled={isPending}>
              Cancel
            </Button>
          </>
        )}
      </ModalFooter>
    </Modal>
  )
}
