import type { User } from '@syntara/contracts'

import { adminClient } from '../../client'
import { useDialogState } from '../../hooks/useDialogState'
import { useMutationErrorHandler } from '../../hooks/useMutationErrorHandler'
import { useAlerts } from '../../providers/alerts/AlertContext'

export function useRevokeUserTokens() {
  const dialog = useDialogState<User>()
  const { showSuccess } = useAlerts()
  const handleMutationError = useMutationErrorHandler()
  const { mutate: revokeUserTokens } = adminClient.useMutation('post', '/admin/revocation/users/{username}')

  const handleRevoke = () => {
    if (!dialog.item) return
    const username = dialog.item.username
    revokeUserTokens(
      { params: { path: { username } } },
      {
        onSuccess: (responseData) => {
          showSuccess({
            title: 'Tokens revoked',
            description: responseData.message,
          })
        },
        onError: handleMutationError({
          title: 'Failed to revoke tokens',
          context: `User "${username}"`,
        }),
        onSettled: dialog.close,
      }
    )
  }

  return { revokeDialog: dialog, handleRevoke }
}
