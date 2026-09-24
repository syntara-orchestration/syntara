import { useCallback, useEffect, useMemo, useState } from 'react'
import type { UseFormReturn } from 'react-hook-form'

import { credentialsClient } from '../../../../client'
import { useSynForm } from '../../../../hooks/useSynForm'
import { useAlerts } from '../../../../providers/alerts'
import { useSelectableProjects } from '../../../access/useAllProjects'
import type { Credential } from '../credentialConstants'

import type { CredentialFormData } from './credentialFormSchema'
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

type UseCredentialFormModalOptions = {
  form: ReturnType<typeof useSynForm<CredentialFormData>>
  credentialToEdit?: Credential | null
  isEditMode: boolean
  preSelectedTypeId?: string
  defaultProjectId?: string
  onCreated?: (credentialId: string) => void
  onSuccess?: () => void
}

export function useCredentialFormModal({
  form,
  credentialToEdit,
  isEditMode,
  preSelectedTypeId,
  defaultProjectId,
  onCreated,
  onSuccess,
}: UseCredentialFormModalOptions) {
  const { showAlert } = useAlerts()
  const { projects, isLoading: isLoadingProjects, error: projectsError } = useSelectableProjects()
  const [touchedSecrets, setTouchedSecrets] = useState<Set<string>>(() => new Set())

  const { handleSubmit, handleError, handleClose, reset, watch, setValue, setError } = form

  const selectedTypeId = watch('credential_type_id')
  const inputs = watch('inputs')

  const typesQuery = credentialsClient.useQuery('get', '/credential_types')
  const types = useMemo(() => typesQuery.data?.resources ?? [], [typesQuery.data])

  const selectedType = useMemo(() => types.find((t) => t.id === selectedTypeId), [types, selectedTypeId])
  const typeInputs = useMemo(() => (selectedType ? getTypeInputs(selectedType) : null), [selectedType])

  const exclusiveGroups = useMemo(() => (typeInputs ? buildExclusiveGroups(typeInputs) : []), [typeInputs])
  const [activeGroupIndex, setActiveGroupIndex] = useState(0)

  const resetKey = credentialToEdit?.id ?? preSelectedTypeId ?? 'create'
  const [prevResetKey, setPrevResetKey] = useState<string | null>(null)
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey)
    setActiveGroupIndex(computeInitialGroupIndex(credentialToEdit, types))
    setTouchedSecrets(new Set())
  }

  const { mutate: createCredential, isPending: isCreating } = credentialsClient.useMutation('post', '/credentials')
  const { mutate: patchCredential, isPending: isPatching } = credentialsClient.useMutation(
    'patch',
    '/credentials/{credential_id}'
  )
  const isSubmitting = isCreating || isPatching

  const visibleFields = useMemo(
    () => (typeInputs ? getVisibleFields(typeInputs, activeGroupIndex) : []),
    [typeInputs, activeGroupIndex]
  )

  const authMethodInsertIndex = useMemo(
    () => (typeInputs ? getAuthMethodInsertIndex(visibleFields, typeInputs) : -1),
    [visibleFields, typeInputs]
  )

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
    [typeInputs, activeGroupIndex, setValue, setActiveGroupIndex]
  )

  useEffect(() => {
    if (credentialToEdit) {
      reset({
        name: credentialToEdit.name,
        description: credentialToEdit.description ?? '',
        project_id: credentialToEdit.project_id ?? '',
        credential_type_id: credentialToEdit.credential_type_id,
        inputs: credentialToEdit.inputs as Record<string, unknown>,
      })
      return
    }

    const preSelectedType = preSelectedTypeId ? types.find((t) => t.id === preSelectedTypeId) : undefined
    reset({
      name: '',
      description: '',
      project_id: defaultProjectId ?? '',
      credential_type_id: preSelectedTypeId ?? '',
      inputs: preSelectedType ? getDefaultInputs(preSelectedType) : {},
    })
  }, [resetKey, credentialToEdit, preSelectedTypeId, defaultProjectId, types, reset])

  useEffect(() => {
    if (!isEditMode && !selectedTypeId && !preSelectedTypeId && types.length > 0) {
      const defaultType = types[0]
      setValue('credential_type_id', defaultType.id ?? '')
      setValue('inputs', getDefaultInputs(defaultType))
    }
  }, [types, isEditMode, selectedTypeId, preSelectedTypeId, setValue])

  const isTypeSelectDisabled = isEditMode || Boolean(preSelectedTypeId) || typesQuery.isLoading

  const handleSecretTouch = useCallback((fieldId: string) => {
    setTouchedSecrets((prev) => new Set(prev).add(fieldId))
  }, [])

  const onSubmit = (formData: CredentialFormData) => {
    if (!validateAllDynamicFields({ typeInputs, inputs, visibleFields, isEditMode, touchedSecrets }, setError)) {
      return
    }

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
            handleClose()
          },
          onError: handleError({ title: 'Failed to update credential' }),
        }
      )
      return
    }

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
          handleClose()
        },
        onError: handleError({ title: 'Failed to create credential' }),
      }
    )
  }

  const credentialTypeHint =
    selectedType?.description && !typesQuery.error ? selectedType.description : undefined

  const handleTypeSelect = useCallback(
    (typeId: string | number | undefined, onTypeChange: (value: string) => void) => {
      if (typeId == null) return
      const id = String(typeId)
      onTypeChange(id)
      if (!isEditMode) {
        const newType = types.find((t) => t.id === id)
        setValue('inputs', newType ? getDefaultInputs(newType) : {})
        setActiveGroupIndex(0)
      }
    },
    [isEditMode, types, setValue, setActiveGroupIndex]
  )

  return {
    handleSubmit,
    handleClose,
    onSubmit,
    isSubmitting,
    projects,
    isLoadingProjects,
    projectsError,
    types,
    typesQuery,
    isEditMode,
    isTypeSelectDisabled,
    exclusiveGroups,
    activeGroupIndex,
    handleGroupChange,
    authMethodInsertIndex,
    allExclusiveFieldIds,
    typeInputs,
    visibleFields,
    handleSecretTouch,
    credentialTypeHint,
    handleTypeSelect,
  }
}

export type CredentialFormModalForm = UseFormReturn<CredentialFormData>
