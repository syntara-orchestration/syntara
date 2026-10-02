import type { FormsAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import { usersClient } from '../../../client'
import { useAuthStore } from '../../../stores/useAuthStore'

type ResponderConfig = Partial<
  Pick<FormsAPI.components['schemas']['FormPromptRead'], 'responder_users' | 'responder_groups'>
>

/**
 * UX-only check that the current user is a configured responder.
 * Backend enforces authorization on submit.
 */
export function useCanSubmitFormPrompt(prompt: ResponderConfig | undefined): {
  canSubmit: boolean
  isLoading: boolean
  isError: boolean
} {
  const currentUserId = useAuthStore((state) => state.userId)

  const responderUsers = prompt?.responder_users
  const responderGroups = prompt?.responder_groups

  const hasResponders = (responderUsers && responderUsers.length > 0) || (responderGroups && responderGroups.length > 0)
  const isDirectMatch = Boolean(
    currentUserId && responderUsers?.some((user: { id: string }) => user.id === currentUserId)
  )
  const needsGroupCheck =
    hasResponders && !isDirectMatch && responderGroups && responderGroups.length > 0 && Boolean(currentUserId)

  const groupsQuery = usersClient.useQuery('get', '/users/{user_id}/groups', {
    params: { path: { user_id: currentUserId ?? '' } },
    enabled: needsGroupCheck,
  })

  return useMemo(() => {
    if (!prompt) {
      return { canSubmit: false, isLoading: false, isError: false }
    }

    if (!('responder_users' in prompt) && !('responder_groups' in prompt)) {
      return { canSubmit: false, isLoading: false, isError: false }
    }

    if (!hasResponders) {
      return { canSubmit: true, isLoading: false, isError: false }
    }

    if (isDirectMatch) {
      return { canSubmit: true, isLoading: false, isError: false }
    }

    if (!needsGroupCheck) {
      return { canSubmit: false, isLoading: false, isError: false }
    }

    if (groupsQuery.isLoading) {
      return { canSubmit: false, isLoading: true, isError: false }
    }

    if (groupsQuery.isError) {
      return { canSubmit: false, isLoading: false, isError: true }
    }

    const userGroups = groupsQuery.data?.resources ?? []
    const userGroupIds = new Set(userGroups.map((g) => g.id))
    const isGroupMember = responderGroups?.some((group: { id: string }) => userGroupIds.has(group.id)) ?? false

    return { canSubmit: isGroupMember, isLoading: false, isError: false }
  }, [
    prompt,
    hasResponders,
    isDirectMatch,
    needsGroupCheck,
    groupsQuery.isLoading,
    groupsQuery.isError,
    groupsQuery.data,
    responderGroups,
  ])
}
