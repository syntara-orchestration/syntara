import { zodResolver } from '@hookform/resolvers/zod'
import {
  Alert,
  Button,
  Checkbox,
  ClipboardCopy,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  SelectList,
  SelectOption,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiErrorIcon } from '@patternfly/react-icons'
import { useCallback, useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'

import { SynSelect } from '../../../components/SynSelect'
import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { formatExpirationDate } from '../../../utils/dateUtils'
import { detachPromise } from '../../../utils/detachPromise'
import { useSelectableProjects } from '../../access/useAllProjects'
import { CredentialExpirationField } from '../../access-management/service-accounts/CredentialExpirationField'
import {
  createServiceAccountSchema,
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

export function ProjectField({
  value,
  onChange,
  error,
  projectOptions,
}: Readonly<{
  value: string
  onChange: (val: string) => void
  error?: string
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
    <FormGroup label="Project" fieldId="sa-inline-project" isRequired>
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

      {error && (
        <FormHelperText>
          <HelperText>
            <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
              {error}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      )}
    </FormGroup>
  )
}

type CreateFormBodyProps = Readonly<{
  control: ReturnType<typeof useForm<CreateServiceAccountFormData>>['control']
  projectOptions: ReadonlyArray<{ id: string; name: string }>
}>

function CreateFormBody({ control, projectOptions }: CreateFormBodyProps) {
  return (
    <>
      <Controller
        name="project_id"
        control={control}
        render={({ field, fieldState }) => (
          <ProjectField
            value={field.value}
            onChange={field.onChange}
            error={fieldState.error?.message}
            projectOptions={projectOptions}
          />
        )}
      />
      <Controller
        name="name"
        control={control}
        render={({ field, fieldState }) => (
          <FormGroup label="Name" fieldId="sa-inline-name" isRequired>
            <TextInput
              id="sa-inline-name"
              aria-label="Name"
              placeholder="my-service-account"
              validated={fieldState.error ? 'error' : 'default'}
              value={field.value ?? ''}
              onChange={field.onChange}
              onBlur={field.onBlur}
              name={field.name}
            />
            <FormHelperText>
              <HelperText>
                <HelperTextItem
                  variant={fieldState.error ? 'error' : 'default'}
                  icon={fieldState.error ? <RhUiErrorIcon /> : undefined}
                >
                  {fieldState.error?.message ??
                    'Lowercase letters, numbers, and hyphens. Must start and end with a letter or number.'}
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          </FormGroup>
        )}
      />
      <Controller
        name="description"
        control={control}
        render={({ field, fieldState }) => (
          <FormGroup label="Description" fieldId="sa-inline-description">
            <TextArea
              id="sa-inline-description"
              aria-label="Description"
              placeholder="Describe the purpose of this service account"
              validated={fieldState.error ? 'error' : 'default'}
              value={field.value ?? ''}
              onChange={field.onChange}
              onBlur={field.onBlur}
              name={field.name}
              rows={3}
            />
          </FormGroup>
        )}
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

  const { control, handleSubmit, setError, reset } = useForm<CreateServiceAccountFormData>({
    resolver: zodResolver(createServiceAccountSchema, undefined, { mode: 'sync' }),
    defaultValues: { name: '', description: '', project_id: projectId ?? '' },
  })

  const handleError = useFormMutationErrorHandler<CreateServiceAccountFormData>(setError)
  const { credentials, savedAck, setSavedAck, isPending, submitForm, resetState, showCredentials } =
    useCreateServiceAccountInline(expiresAt)

  const handleClose = useCallback(() => {
    const saId = resetState()
    reset()
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
              <CreateFormBody control={control} projectOptions={projectOptions} />
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
