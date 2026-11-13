import { useCallback, useState } from 'react'

import type { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { accessClient } from '../../access/accessClient'
import type { CreateServiceAccountFormData } from '../../access-management/service-accounts/serviceAccountFormSchema'

export type CredentialInfo = Readonly<{ identifier: string; client_secret: string; expiresAt?: string | null }>

export function useCreateServiceAccountInline(expiresAt: string, projectId?: string) {
  const [credentials, setCredentials] = useState<CredentialInfo | null>(null)
  const [createdSaId, setCreatedSaId] = useState<string | null>(null)
  const [savedAck, setSavedAck] = useState(false)

  const { mutateAsync: createSA, isPending: isCreatingSA } = accessClient.useMutation('post', '/service_accounts')
  const { mutateAsync: createCred, isPending: isCreatingCred } = accessClient.useMutation(
    'post',
    '/service_accounts/{service_account_id}/credentials'
  )
  const isPending = isCreatingSA || isCreatingCred

  const submitForm = useCallback(
    async (formData: CreateServiceAccountFormData, handleError: ReturnType<typeof useFormMutationErrorHandler>) => {
      try {
        const saResponse = await createSA({
          body: {
            name: formData.name,
            description: formData.description ?? undefined,
            ...(projectId ? { project_id: projectId } : {}),
          },
        })
        setCreatedSaId(saResponse.id)

        const credResponse = await createCred({
          params: { path: { service_account_id: saResponse.id } },
          body: {
            credential_type: 'client_credentials',
            ...(expiresAt ? { expires_at: `${expiresAt}T00:00:00Z` } : {}),
          },
        })
        setCredentials({
          identifier: credResponse.identifier,
          client_secret: credResponse.client_secret ?? '',
          expiresAt: credResponse.expires_at,
        })
      } catch (error: unknown) {
        handleError({ title: 'Failed to create service account', context: formData.name })(error)
      }
    },
    [createSA, createCred, expiresAt, projectId]
  )

  const resetState = useCallback(() => {
    const saId = createdSaId
    setCredentials(null)
    setCreatedSaId(null)
    setSavedAck(false)
    return saId
  }, [createdSaId])

  return {
    credentials,
    createdSaId,
    savedAck,
    setSavedAck,
    isPending,
    submitForm,
    resetState,
    showCredentials: credentials !== null,
  }
}
