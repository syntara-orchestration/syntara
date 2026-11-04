import type { UseFormSetError } from 'react-hook-form'

import type { Credential, CredentialType } from '../credentialConstants'

import type { CredentialFormData } from './credentialFormSchema'
import {
  buildEditInputs,
  getTypeInputs,
  getVisibleFields,
  stripHiddenGroupFields,
  validateAllDynamicFields,
  type TypeInputs,
} from './credentialFormUtils'
import type { FieldDefinition } from './DynamicFieldRenderer'

type SubmitCredentialFormModalParams = {
  formData: CredentialFormData
  allTypes: CredentialType[]
  typeInputs: TypeInputs | null
  visibleFields: FieldDefinition[]
  activeGroupIndex: number
  getValues: () => CredentialFormData
  setError: UseFormSetError<CredentialFormData>
  isEditMode: boolean
  credentialToEdit?: Credential | null
  touchedSecrets: Set<string>
  patchCredential: (
    variables: {
      params: { path: { credential_id: string } }
      body: {
        name: string
        description: string | null
        inputs: Record<string, unknown>
      }
    },
    options: {
      onSuccess: () => void
      onError: (error: unknown) => void
    }
  ) => void
  createCredential: (
    variables: {
      body: {
        name: string
        description: string | null
        credential_type_id: string
        inputs: Record<string, unknown>
        project_id: string
      }
    },
    options: {
      onSuccess: (response: { id?: string } | undefined) => void
      onError: (error: unknown) => void
    }
  ) => void
  showAlert: (alert: { title: string; variant: 'success'; autoDismiss: true }) => void
  onSuccess?: () => void
  onCreated?: (credentialId: string) => void
  handleClose: () => void
  handleError: (context: { title: string }) => (error: unknown) => void
}

export function submitCredentialFormModal({
  formData,
  allTypes,
  typeInputs,
  visibleFields,
  activeGroupIndex,
  getValues,
  setError,
  isEditMode,
  credentialToEdit,
  touchedSecrets,
  patchCredential,
  createCredential,
  showAlert,
  onSuccess,
  onCreated,
  handleClose,
  handleError,
}: SubmitCredentialFormModalParams): void {
  const submitType = allTypes.find((t) => t.id === formData.credential_type_id)
  const submitTypeInputs = submitType ? getTypeInputs(submitType) : typeInputs
  const submitVisibleFields = submitTypeInputs ? getVisibleFields(submitTypeInputs, activeGroupIndex) : visibleFields
  const latestInputs = getValues().inputs ?? formData.inputs ?? {}

  if (!submitTypeInputs) {
    setError('credential_type_id', { message: 'Credential type is required' })
    return
  }

  if (
    !validateAllDynamicFields(
      {
        typeInputs: submitTypeInputs,
        inputs: latestInputs,
        visibleFields: submitVisibleFields,
        isEditMode,
        touchedSecrets,
      },
      setError
    )
  ) {
    return
  }

  const cleanedInputs = stripHiddenGroupFields(latestInputs, submitTypeInputs, submitVisibleFields)

  if (isEditMode && credentialToEdit) {
    patchCredential(
      {
        params: { path: { credential_id: credentialToEdit.id ?? '' } },
        body: {
          name: formData.name,
          description: formData.description || null,
          inputs: buildEditInputs(cleanedInputs, submitTypeInputs, touchedSecrets),
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
