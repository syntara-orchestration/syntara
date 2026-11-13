import { useCallback, useState } from 'react'

import { useActiveAdminCount } from '../../hooks/useActiveAdminCount'
import { useMutationErrorHandler } from '../../hooks/useMutationErrorHandler'
import { useAlerts } from '../../providers/alerts/AlertContext'
import { useAuthStore } from '../../stores/useAuthStore'
import { getUserIdFromToken } from '../../utils/jwtUtils'
import { accessClient } from '../access/accessClient'

import { logoutWithAlert } from './logoutWithAlert'

type AdminUser = {
  id: string
  is_enabled: boolean
}

export type AdminToggleState = {
  canToggle: boolean
  showConfirm: boolean
  handleToggle: (checked: boolean) => void
  confirmDisable: () => void
  cancelDisable: () => void
}

export function useAdminToggle(builtinUser: AdminUser | undefined, refetch: () => void): AdminToggleState {
  const [showConfirm, setShowConfirm] = useState(false)
  const { showAlert } = useAlerts()
  const handleMutationError = useMutationErrorHandler()

  const accessToken = useAuthStore((s) => s.accessToken)
  const logout = useAuthStore((s) => s.logout)
  const currentUserId = getUserIdFromToken(accessToken)
  const isSelf = !!builtinUser && currentUserId === builtinUser.id
  const isEnabled = builtinUser?.is_enabled ?? true

  const activeAdminCount = useActiveAdminCount(!!builtinUser && isSelf)
  // Re-enable (!isEnabled) is intentionally unrestricted — any admin can re-enable
  // the built-in account. Only disabling requires self + other admins present.
  const canToggle = !isEnabled || (isSelf && activeAdminCount > 1)

  const { mutate: updateUser } = accessClient.useMutation('patch', '/users/{user_id}')

  const executeToggle = useCallback(
    (checked: boolean) => {
      if (!builtinUser) return
      updateUser(
        { params: { path: { user_id: builtinUser.id } }, body: { is_enabled: checked } },
        {
          onSuccess: () => {
            if (checked) {
              refetch()
            } else {
              logoutWithAlert(logout, showAlert, 'Administrator disabled — signing out')
            }
          },
          onError: handleMutationError({ title: 'Failed to update administrator' }),
        }
      )
    },
    [builtinUser, updateUser, showAlert, refetch, handleMutationError, logout]
  )

  const handleToggle = useCallback(
    (checked: boolean) => {
      if (!checked) {
        setShowConfirm(true)
        return
      }
      executeToggle(true)
    },
    [executeToggle]
  )

  const confirmDisable = useCallback(() => {
    setShowConfirm(false)
    executeToggle(false)
  }, [executeToggle])

  const cancelDisable = useCallback(() => {
    setShowConfirm(false)
  }, [])

  return { canToggle, showConfirm, handleToggle, confirmDisable, cancelDisable }
}
