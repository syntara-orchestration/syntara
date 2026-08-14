import type { User } from '@syntara/contracts'
import { startTransition, useCallback, useMemo, useOptimistic, useState } from 'react'

import { useActiveAdminCount } from '../../hooks/useActiveAdminCount'
import { useMutationErrorHandler } from '../../hooks/useMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'
import { useAuthStore } from '../../stores/useAuthStore'
import { getUserIdFromToken } from '../../utils/jwtUtils'
import { accessClient } from '../access/accessClient'

import { BUILTIN_ADMINS_GROUP_NAME } from './adminConstants'
import { logoutWithAlert } from './logoutWithAlert'
import { computeToggleStatus } from './userToggleStatus'
import { useUserPermissions } from './useUserPermissions'

type EnabledUpdate = {
  id: string
  is_enabled: boolean
}

function applyEnabledUpdate(users: User[], update: EnabledUpdate): User[] {
  return users.map((user) => (user.id === update.id ? { ...user, is_enabled: update.is_enabled } : user))
}

export type UseUsersEnabledToggleResult = {
  users: User[]
  getToggleDisabledReason: (user: User) => string | undefined
  handleToggleEnabled: (user: User) => void
  disableConfirm: {
    isOpen: boolean
    user: User | undefined
    close: () => void
    confirm: () => void
  }
}

/**
 * Optimistic enable/disable for the users list State column.
 * Applies last-admin / builtin-admin guards and confirms before disable.
 */
export function useUsersEnabledToggle(
  users: User[],
  onRefetch: () => void | Promise<unknown>
): UseUsersEnabledToggleResult {
  const permissions = useUserPermissions()
  const { showAlert } = useAlerts()
  const handleMutationError = useMutationErrorHandler()
  const accessToken = useAuthStore((s) => s.accessToken)
  const logout = useAuthStore((s) => s.logout)
  const currentUserId = getUserIdFromToken(accessToken)

  const activeAdminCount = useActiveAdminCount(true)

  const groupsQuery = accessClient.useQuery('get', '/groups', {
    params: { query: { limit: 100, name: BUILTIN_ADMINS_GROUP_NAME } },
  })
  const adminsGroup = (groupsQuery.data?.resources ?? []).find((g) => g.is_builtin)
  const adminsGroupId = adminsGroup?.id ?? ''
  const membersQuery = accessClient.useQuery(
    'get',
    '/groups/{group_id}/members',
    { params: { path: { group_id: adminsGroupId }, query: { limit: 100 } } },
    { enabled: !!adminsGroupId }
  )
  const adminMemberIds = useMemo(
    () => new Set((membersQuery.data?.resources ?? []).map((m) => m.id)),
    [membersQuery.data?.resources]
  )

  const [userToDisable, setUserToDisable] = useState<User | undefined>()
  const [optimisticUsers, setOptimisticEnabled] = useOptimistic(users, applyEnabledUpdate)

  const { mutateAsync: updateUser } = accessClient.useMutation('patch', '/users/{user_id}')

  const getToggleDisabledReason = useCallback(
    (user: User): string | undefined => {
      if (!permissions.canUpdate) {
        return permissions.tooltips.update
      }
      const isSelf = user.id === currentUserId
      const isInAdminsGroup = adminMemberIds.has(user.id) || !!user.is_builtin
      const isLastAdmin = isInAdminsGroup && user.is_enabled && activeAdminCount <= 1
      return computeToggleStatus(!!user.is_builtin, user.is_enabled, isSelf, isLastAdmin).statusToggleDisabledReason
    },
    [adminMemberIds, activeAdminCount, currentUserId, permissions.canUpdate, permissions.tooltips.update]
  )

  const setUserEnabled = useCallback(
    (user: User, enabled: boolean) => {
      const isSelf = user.id === currentUserId
      startTransition(async () => {
        setOptimisticEnabled({ id: user.id, is_enabled: enabled })
        try {
          await updateUser({
            params: { path: { user_id: user.id } },
            body: { is_enabled: enabled },
          })
          if (isSelf && !enabled) {
            const message = user.is_builtin ? 'Administrator disabled — signing out' : 'Account disabled — signing out'
            logoutWithAlert(logout, showAlert, message)
            return
          }
          showAlert({
            title: enabled ? 'User enabled' : 'User disabled',
            variant: 'success',
            autoDismiss: true,
          })
          await onRefetch()
        } catch (error: unknown) {
          handleMutationError({
            title: enabled ? 'Failed to enable user' : 'Failed to disable user',
          })(error)
        }
      })
    },
    [currentUserId, handleMutationError, logout, onRefetch, setOptimisticEnabled, showAlert, updateUser]
  )

  const handleToggleEnabled = useCallback(
    (user: User) => {
      if (getToggleDisabledReason(user)) return
      if (user.is_enabled) {
        setUserToDisable(user)
        return
      }
      setUserEnabled(user, true)
    },
    [getToggleDisabledReason, setUserEnabled]
  )

  const closeDisableConfirm = useCallback(() => {
    setUserToDisable(undefined)
  }, [])

  const confirmDisable = useCallback(() => {
    const user = userToDisable
    setUserToDisable(undefined)
    if (!user) return
    setUserEnabled(user, false)
  }, [setUserEnabled, userToDisable])

  return {
    users: optimisticUsers,
    getToggleDisabledReason,
    handleToggleEnabled,
    disableConfirm: {
      isOpen: !!userToDisable,
      user: userToDisable,
      close: closeDisableConfirm,
      confirm: confirmDisable,
    },
  }
}
