import {
  Alert,
  Button,
  Checkbox,
  ClipboardCopy,
  Form,
  FormGroup,
  MenuToggle,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  SelectList,
  SelectOption,
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { SynSelect } from '../../../components/SynSelect'
import { useSynForm } from '../../../hooks/useSynForm'
import { formatExpirationDate } from '../../../utils/dateUtils'
import { detachPromise } from '../../../utils/detachPromise'
import { useSelectableProjects } from '../../access/useAllProjects'
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
        <ClipboardCopy isReadOnly hoverTip="Copy" clickTip="Copied">
          {credentials.identifier}
        </ClipboardCopy>
      </FormGroup>
      <FormGroup label="Client secret" fieldId="sa-inline-secret">
        <ClipboardCopy isReadOnly hoverTip="Copy" clickTip="Copied">
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

export function ProjectSelectToggle({
  toggleRef,
  label,
  isOpen,
  onToggle,
}: Readonly<{
  toggleRef: React.Ref<HTMLButtonElement>
  label: string
  isOpen: boolean
  onToggle: () => void
}>) {
  return (
    <MenuToggle ref={toggleRef} onClick={onToggle} isExpanded={isOpen} isFullWidth>
      {label}
    </MenuToggle>
  )
}

function InlineProjectSelect({
  value,
  onChange,
  projectOptions,
}: Readonly<{
  value: string
  onChange: (val: string) => void
  projectOptions: ReadonlyArray<{ id: string; name: string }>
}>) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = projectOptions.find((p) => p.id === value)?.name ?? 'Select a project'

  const renderToggle = useCallback(
    (ref: React.Ref<HTMLButtonElement>) => (
      <ProjectSelectToggle
        toggleRef={ref}
        label={selectedLabel}
        isOpen={isOpen}
        onToggle={() => setIsOpen((prev) => !prev)}
      />
    ),
    [selectedLabel, isOpen]
  )

  return (
    <SynSelect
      id="sa-inline-project"
      aria-label="Project"
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      onSelect={(_e, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      selected={value}
      popperProps={{ appendTo: 'inline' }}
      toggle={renderToggle}
    >
      <SelectList>
        {projectOptions.map((p) => (
          <SelectOption key={p.id} value={p.id} isSelected={p.id === value}>
            {p.name}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

type CreateFormBodyProps = Readonly<{
  projectOptions: ReadonlyArray<{ id: string; name: string }>
}>

function CreateFormBody({ projectOptions }: CreateFormBodyProps) {
  return (
    <>
      <SynFormField name="project_id" label="Project" fieldId="sa-inline-project" isRequired>
        {({ field }) => (
          <InlineProjectSelect
            value={field.value as string}
            onChange={field.onChange}
            projectOptions={projectOptions}
          />
        )}
      </SynFormField>
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
  const { projects } = useSelectableProjects()
  const projectOptions = useMemo(
    () =>
      projects
        .filter((p): p is typeof p & { id: string } => typeof p.id === 'string')
        .map((p) => ({ id: p.id, name: p.name })),
    [projects]
  )

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
    defaultValues: { name: '', description: '', project_id: projectId ?? '' },
  })
  const { handleSubmit, handleError, reset } = form

  useEffect(() => {
    if (isOpen) {
      reset({ name: '', description: '', project_id: projectId ?? '' })
    }
  }, [isOpen, projectId, reset])

  const { credentials, savedAck, setSavedAck, isPending, submitForm, resetState, showCredentials } =
    useCreateServiceAccountInline(expiresAt)

  const handleClose = useCallback(() => {
    const saId = resetState()
    reset({ name: '', description: '', project_id: projectId ?? '' })
    resetExpirationDate()
    onClose()
    if (saId) onCreated(saId)
  }, [resetState, onClose, onCreated, reset, resetExpirationDate, projectId])

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
                <CreateFormBody projectOptions={projectOptions} />
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
