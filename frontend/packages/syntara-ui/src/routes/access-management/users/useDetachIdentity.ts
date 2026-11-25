import { useState } from 'react'

import { usersClient } from '../../../client'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts/AlertContext'

import type { UserIdentity } from './identityUtils'

export function useDetachIdentity(userId: string, refetch: () => void) {
  const { showAlert } = useAlerts()
  const handleMutationError = useMutationErrorHandler()
  const [identityToDetach, setIdentityToDetach] = useState<UserIdentity | null>(null)

  const { mutate: detachIdentity, isPending: isDetaching } = usersClient.useMutation(
    'delete',
    '/users/{user_id}/identities/{identity_id}'
  )

  const confirmDetach = () => {
    if (!identityToDetach) return
    detachIdentity(
      { params: { path: { user_id: userId, identity_id: identityToDetach.id } } },
      {
        onSuccess: () => {
          showAlert({ title: 'Identity disconnected', variant: 'success', autoDismiss: true })
          refetch()
        },
        onError: handleMutationError({ title: 'Failed to disconnect identity' }),
        onSettled: () => setIdentityToDetach(null),
      }
    )
  }

  return { identityToDetach, setIdentityToDetach, isDetaching, confirmDetach }
}
