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
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditIcon, RhUiErrorIcon } from '@patternfly/react-icons'
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'

import { credentialsClient } from '../../../../client'
import { FormLabelWithHelp } from '../../../../components/FormLabelWithHelp'
import { useFormMutationErrorHandler } from '../../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../../providers/alerts'
import { useSelectableProjects } from '../../../access/useAllProjects'
import type { Credential } from '../credentialConstants'

import { AuthMethodSelector } from './AuthMethodSelector'
import { credentialFormSchema, type CredentialFormData } from './credentialFormSchema'
import { CredentialTypeSelect, ProjectSelect } from './CredentialFormSelects'
import {
  buildEditInputs,
  buildExclusiveGroups,
  computeInitialGroupIndex,
  getAllExclusiveFieldIds,
  getAuthMethodInsertIndex,
  getDefaultInputs,
  getTypeInputs,
  getVisibleFields,
  stripHiddenGroupFields,
  validateAllDynamicFields,
} from './credentialFormUtils'
import { CREDENTIAL_TYPE_HELP } from './CredentialTypeHelp'
import { DynamicFieldRenderer } from './DynamicFieldRenderer'

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

// eslint-disable-next-line max-lines-per-function
export function CredentialFormModal({
  isOpen,
  onClose,
  credentialToEdit,
  onSuccess,
  preSelectedTypeId,
  onCreated,
  defaultProjectId,
}: Readonly<CredentialFormModalProps>) {
  const isEditMode = !!credentialToEdit
  const { showAlert } = useAlerts()
  const { projects, isLoading: isLoadingProjects, error: projectsError } = useSelectableProjects()

  // Track which secret fields have been touched by the user (for edit mode)
  const [touchedSecrets, setTouchedSecrets] = useState<Set<string>>(new Set())

  // Zod + react-hook-form
  const {
    control,
    handleSubmit,
    reset,
    watch,
    setValue,
    setError,
    formState: { errors },
  } = useForm<CredentialFormData>({
    resolver: zodResolver(credentialFormSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: '',
      description: '',
      project_id: '',
      credential_type_id: '',
      inputs: {},
    },
  })
  const handleMutationError = useFormMutationErrorHandler<CredentialFormData>(setError)

  // Watched values for derived state
  const selectedTypeId = watch('credential_type_id')
  const inputs = watch('inputs')

  // Fetch credential types
  const typesQuery = credentialsClient.useQuery('get', '/credential_types')
  const types = useMemo(() => typesQuery.data?.resources ?? [], [typesQuery.data])

  // Selected type
  const selectedType = useMemo(() => types.find((t) => t.id === selectedTypeId), [types, selectedTypeId])
  const typeInputs = useMemo(() => (selectedType ? getTypeInputs(selectedType) : null), [selectedType])

  // Mutually exclusive field groups
  const exclusiveGroups = useMemo(() => (typeInputs ? buildExclusiveGroups(typeInputs) : []), [typeInputs])
  const [activeGroupIndex, setActiveGroupIndex] = useState(0)

  // Render-time reset for activeGroupIndex when the modal opens/closes (§23D)
  const resetKey = isOpen ? (credentialToEdit?.id ?? preSelectedTypeId ?? 'create') : 'closed'
  const [prevResetKey, setPrevResetKey] = useState<string | null>(null)
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey)
    setActiveGroupIndex(isOpen ? computeInitialGroupIndex(credentialToEdit, types) : 0)
  }

  // Mutations
  const { mutate: createCredential, isPending: isCreating } = credentialsClient.useMutation('post', '/credentials')
  const { mutate: patchCredential, isPending: isPatching } = credentialsClient.useMutation(
    'patch',
    '/credentials/{credential_id}'
  )
  const isSubmitting = isCreating || isPatching

  // Visible fields (filtered by active exclusive group)
  const visibleFields = useMemo(
    () => (typeInputs ? getVisibleFields(typeInputs, activeGroupIndex) : []),
    [typeInputs, activeGroupIndex]
  )

  // Insert index for auth method selector within the visible fields list
  const authMethodInsertIndex = useMemo(
    () => (typeInputs ? getAuthMethodInsertIndex(visibleFields, typeInputs) : -1),
    [visibleFields, typeInputs]
  )

  // Set of all exclusive field IDs for determining required status
  const allExclusiveFieldIds = useMemo(
    () => (typeInputs ? getAllExclusiveFieldIds(typeInputs) : new Set<string>()),
    [typeInputs]
  )

  const handleGroupChange = useCallback(
    (index: number) => {
      if (!typeInputs || index === activeGroupIndex) return
      const previousGroup = typeInputs.mutually_exclusive[activeGroupIndex]
      if (previousGroup) {
        for (const fieldId of previousGroup) {
          setValue(`inputs.${fieldId}`, '')
        }
      }
      setActiveGroupIndex(index)
    },
    [typeInputs, activeGroupIndex, setValue]
  )

  // Reset form when modal opens/closes or credential changes
  useEffect(() => {
    if (!isOpen) return

    setTouchedSecrets(new Set())
    if (credentialToEdit) {
      reset({
        name: credentialToEdit.name,
        description: credentialToEdit.description ?? '',
        project_id: credentialToEdit.project_id ?? '',
        credential_type_id: credentialToEdit.credential_type_id,
        inputs: credentialToEdit.inputs as Record<string, unknown>,
      })
    } else {
      const preSelectedType = preSelectedTypeId ? types.find((t) => t.id === preSelectedTypeId) : undefined
      reset({
        name: '',
        description: '',
        project_id: defaultProjectId ?? '',
        credential_type_id: preSelectedTypeId ?? '',
        inputs: preSelectedType ? getDefaultInputs(preSelectedType) : {},
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset on modal open/close, keyed by resetKey
  }, [resetKey])

  // Auto-select first type in create mode when types load
  useEffect(() => {
    if (!isEditMode && !selectedTypeId && !preSelectedTypeId && types.length > 0) {
      const defaultType = types[0]
      setValue('credential_type_id', defaultType.id ?? '')
      setValue('inputs', getDefaultInputs(defaultType))
    }
  }, [types, isEditMode, selectedTypeId, preSelectedTypeId, setValue])

  // Reset inputs when type changes (create mode only)
  const handleTypeSelect = useCallback(
    (_event: React.MouseEvent | undefined, typeId: string | number | undefined) => {
      if (typeId == null) return
      const id = String(typeId)
      setValue('credential_type_id', id, { shouldValidate: true })
      if (!isEditMode) {
        const newType = types.find((t) => t.id === id)
        setValue('inputs', newType ? getDefaultInputs(newType) : {})
        setActiveGroupIndex(0)
      }
    },
    [isEditMode, types, setValue]
  )

  const isTypeSelectDisabled = isEditMode || !!preSelectedTypeId || typesQuery.isLoading

  const handleInputChange = useCallback(
    (fieldId: string, value: unknown) => {
      setValue(`inputs.${fieldId}`, value, { shouldValidate: true })
    },
    [setValue]
  )

  // Track secret field touches separately (DynamicFieldRenderer calls onChange,
  // but we need to know if a secret was explicitly modified by the user)
  const handleSecretInputChange = useCallback(
    (fieldId: string, value: unknown) => {
      setTouchedSecrets((prev) => new Set(prev).add(fieldId))
      handleInputChange(fieldId, value)
    },
    [handleInputChange]
  )

  function onSubmit(formData: CredentialFormData) {
    if (!validateAllDynamicFields({ typeInputs, inputs, visibleFields, isEditMode, touchedSecrets }, setError)) return

    const cleanedInputs = stripHiddenGroupFields(formData.inputs, typeInputs, visibleFields)

    if (isEditMode && credentialToEdit) {
      patchCredential(
        {
          params: { path: { credential_id: credentialToEdit.id ?? '' } },
          body: {
            name: formData.name,
            description: formData.description || null,
            inputs: buildEditInputs(cleanedInputs, typeInputs, touchedSecrets),
          },
        },
        {
          onSuccess: () => {
            showAlert({ title: 'Credential updated', variant: 'success', autoDismiss: true })
            onSuccess?.()
            onClose()
          },
          onError: handleMutationError({ title: 'Failed to update credential' }),
        }
      )
    } else {
      createCredential(
        {
          body: {
            name: formData.name,
            description: formData.description || null,
            credential_type_id: formData.credential_type_id,
            inputs: cleanedInputs,
            project_id: formData.project_id,
          },
        },
        {
          onSuccess: (response) => {
            showAlert({ title: 'Credential created', variant: 'success', autoDismiss: true })
            if (response?.id) {
              onCreated?.(response.id)
            }
            onSuccess?.()
            onClose()
          },
          onError: handleMutationError({ title: 'Failed to create credential' }),
        }
      )
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="medium">
      <ModalHeader title={isEditMode && credentialToEdit ? `Edit ${credentialToEdit.name}` : 'Create credential'} />
      <ModalBody>
        <Form>
          {/* Name */}
          <FormGroup
            label={
              <FormLabelWithHelp
                label="Name"
                helpText="A unique, descriptive name for this credential. Use a name that helps identify its purpose, such as 'Production API Key' or 'Dev SSH Key'."
              />
            }
            fieldId="credential-name"
            isRequired
          >
            <Controller
              name="name"
              control={control}
              render={({ field: { onChange, value }, fieldState: { error } }) => (
                <>
                  <TextInput
                    id="credential-name"
                    value={value}
                    onChange={(_event, val) => onChange(val)}
                    validated={error ? 'error' : 'default'}
                    placeholder="Enter credential name"
                    aria-label="Credential name"
                  />
                  {error?.message && (
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                          {error.message}
                        </HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  )}
                </>
              )}
            />
          </FormGroup>

          {/* Description */}
          <FormGroup
            label={
              <FormLabelWithHelp
                label="Description"
                helpText="An optional description to provide additional context about this credential, such as what systems it accesses or any usage restrictions."
              />
            }
            fieldId="credential-description"
          >
            <Controller
              name="description"
              control={control}
              render={({ field: { onChange, value } }) => (
                <TextInput
                  id="credential-description"
                  value={value ?? ''}
                  onChange={(_event, val) => onChange(val)}
                  placeholder="Enter description (optional)"
                  aria-label="Credential description"
                />
              )}
            />
          </FormGroup>

          {/* Project */}
          <FormGroup
            label={
              <FormLabelWithHelp
                label="Project"
                helpText="The project this credential belongs to. Credentials are scoped to a single project and can only be used by workflows within that project."
              />
            }
            fieldId="credential-project"
            isRequired={!isEditMode}
          >
            <Controller
              name="project_id"
              control={control}
              render={({ field: { onChange, value }, fieldState: { error } }) => (
                <>
                  <ProjectSelect
                    value={value}
                    onChange={onChange}
                    projects={projects}
                    isDisabled={isEditMode || isLoadingProjects}
                    isLoading={isLoadingProjects}
                    validated={error ? 'error' : 'default'}
                  />
                  {projectsError && (
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                          Failed to load projects
                        </HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  )}
                  {error?.message && (
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                          {error.message}
                        </HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  )}
                </>
              )}
            />
          </FormGroup>

          {/* Credential Type */}
          <FormGroup
            label={<FormLabelWithHelp label="Credential type" helpText={CREDENTIAL_TYPE_HELP} />}
            fieldId="credential-type"
            isRequired
          >
            <CredentialTypeSelect
              types={types}
              selectedTypeId={selectedTypeId}
              onSelect={handleTypeSelect}
              isDisabled={isTypeSelectDisabled}
              isLoading={typesQuery.isLoading}
              hasError={!!errors.credential_type_id}
            />
            {typesQuery.error && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                    Failed to load credential types
                  </HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
            {selectedType?.description && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>{selectedType.description}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
            {errors.credential_type_id?.message && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                    {errors.credential_type_id.message}
                  </HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>

          {/* Dynamic Fields with inline auth method selector */}
          {visibleFields.map((field, index) => {
            const isSecret = field.secret === true
            const isGroupField = allExclusiveFieldIds.has(field.id)
            const isRequired = isGroupField || (typeInputs?.required.includes(field.id) ?? false)
            return (
              <Fragment key={field.id}>
                {exclusiveGroups.length > 0 && index === authMethodInsertIndex && (
                  <AuthMethodSelector
                    groups={exclusiveGroups}
                    activeIndex={activeGroupIndex}
                    onChange={handleGroupChange}
                    helpText={typeInputs?.mutually_exclusive_help}
                  />
                )}
                <DynamicFieldRenderer
                  field={field}
                  value={(inputs[field.id] as string | boolean | undefined) ?? ''}
                  onChange={isSecret ? handleSecretInputChange : handleInputChange}
                  isRequired={isRequired}
                  isEditMode={isEditMode}
                  error={(errors.inputs as Record<string, { message?: string }> | undefined)?.[field.id]?.message}
                />
              </Fragment>
            )
          })}
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={handleSubmit(onSubmit)}
          isDisabled={isSubmitting}
          isLoading={isSubmitting}
          icon={isEditMode ? <RhUiEditIcon /> : <RhUiAddIcon />}
        >
          {isEditMode ? 'Save changes' : 'Create credential'}
        </Button>
        <Button variant="link" onClick={onClose} isDisabled={isSubmitting}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
