import type { FormsAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { usersFetchClient } from '../../../client'
import { useAuthStore } from '../../../stores/useAuthStore'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'

type ResponderConfig = Partial<
  Pick<FormsAPI.components['schemas']['FormPromptRead'], 'responder_users' | 'responder_groups'>
>

type GroupMembership = { id?: string }

/**
 * UX-only check that the current user is a configured responder.
 * Backend enforces authorization on submit.
 */
export function useCanSubmitFormPrompt(prompt: ResponderConfig | undefined): {
  canSubmit: boolean
  isLoading: boolean
  isError: boolean
  refetch: () => Promise<unknown>
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

  const groupsQuery = useQuery({
    queryKey: ['users', currentUserId, 'groups', 'membership'],
    enabled: needsGroupCheck,
    queryFn: () =>
      fetchAllPages<GroupMembership>((cursor) =>
        usersFetchClient.GET('/users/{user_id}/groups', {
          params: {
            path: { user_id: currentUserId ?? '' },
            query: { limit: MAX_PAGE_SIZE, cursor },
          },
        })
      ),
  })

  return useMemo(() => {
    if (!prompt) {
      return { canSubmit: false, isLoading: false, isError: false, refetch: groupsQuery.refetch }
    }

    if (!('responder_users' in prompt) && !('responder_groups' in prompt)) {
      return { canSubmit: false, isLoading: false, isError: false, refetch: groupsQuery.refetch }
    }

    if (!hasResponders) {
      return { canSubmit: true, isLoading: false, isError: false, refetch: groupsQuery.refetch }
    }

    if (isDirectMatch) {
      return { canSubmit: true, isLoading: false, isError: false, refetch: groupsQuery.refetch }
    }

    if (!needsGroupCheck) {
      return { canSubmit: false, isLoading: false, isError: false, refetch: groupsQuery.refetch }
    }

    if (groupsQuery.isLoading) {
      return { canSubmit: false, isLoading: true, isError: false, refetch: groupsQuery.refetch }
    }

    if (groupsQuery.isError) {
      return { canSubmit: false, isLoading: false, isError: true, refetch: groupsQuery.refetch }
    }

    const userGroupIds = new Set(
      (groupsQuery.data ?? []).map((g) => g.id).filter((id): id is string => typeof id === 'string')
    )
    const isGroupMember = responderGroups?.some((group: { id: string }) => userGroupIds.has(group.id)) ?? false

    return { canSubmit: isGroupMember, isLoading: false, isError: false, refetch: groupsQuery.refetch }
  }, [
    prompt,
    hasResponders,
    isDirectMatch,
    needsGroupCheck,
    groupsQuery.isLoading,
    groupsQuery.isError,
    groupsQuery.data,
    groupsQuery.refetch,
    responderGroups,
  ])
}
