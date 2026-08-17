import { useParams } from '@tanstack/react-router'
import { useMemo } from 'react'

import { useAuthStore } from '../../../stores/useAuthStore'
import { isValidUUID } from '../../../utils/generateUUID'
import { getUserIdFromToken } from '../../../utils/jwtUtils'
import { accessClient } from '../../access/accessClient'
import { AUTH_TYPE_FEDERATED } from '../adminConstants'
import type { UserFormData } from '../userFormSchema'

function useStableFormValues(
  userData:
    | { username: string; first_name: string; last_name?: string | null; email?: string | null; is_enabled: boolean }
    | undefined
): UserFormData | undefined {
  const username = userData?.username
  const firstName = userData?.first_name ?? ''
  const lastName = userData?.last_name ?? ''
  const email = userData?.email ?? ''
  const isEnabledVal = userData?.is_enabled

  return useMemo(
    () =>
      username !== undefined && isEnabledVal !== undefined
        ? { username, first_name: firstName, last_name: lastName, email, password: '', is_enabled: isEnabledVal }
        : undefined,
    [username, firstName, lastName, email, isEnabledVal]
  )
}

export function useUserFormData(isEdit: boolean) {
  const { userId }: { userId: string } = useParams({ strict: false })
  const isValidId = !!userId && isValidUUID(userId)

  const userQuery = accessClient.useQuery(
    'get',
    '/users/{user_id}',
    { params: { path: { user_id: userId ?? '' } } },
    { enabled: isEdit && isValidId, retry: false }
  )

  const userData = userQuery.data
  const isBuiltinUser = !!userData?.is_builtin
  const isFederatedUser = userData?.auth_type === AUTH_TYPE_FEDERATED

  const accessToken = useAuthStore((s) => s.accessToken)
  const currentUserId = getUserIdFromToken(accessToken)
  const isSelf = isEdit && userId === currentUserId

  // Depend on scalar values instead of the userData ref so background refetches
  // that return identical data don't produce a new formValues object and reset the form.
  const formValues = useStableFormValues(userData)

  return {
    userId: userId ?? '',
    isValidId,
    userQuery,
    userData,
    isBuiltinUser,
    isFederatedUser,
    isSelf,
    formValues,
  }
}
