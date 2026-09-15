import { useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'

import { detachPromise } from '../../../../utils/detachPromise'
import { useAllGroups } from '../../../access/useAllGroups'
import { excludeAuthenticatedGroup } from '../../adminConstants'

import { EmptyMappingState, ReadOnlyView } from './GroupMappingComponents'
import { toFormEntries, type GroupMappingConfig } from './groupMappingUtils'
import { identityProviderGroupMappingEditPath } from './identityProviderPaths'

type GroupMappingTabProps = {
  providerId: string
  groupMapping: GroupMappingConfig | null | undefined
  /** When true, editing controls are hidden (user has read but not update permission). */
  readOnly?: boolean
}

export function GroupMappingTab({ providerId, groupMapping, readOnly = false }: Readonly<GroupMappingTabProps>) {
  const navigate = useNavigate()
  const { groups: allGroupsRaw } = useAllGroups()
  const mappedGroups = useMemo(() => excludeAuthenticatedGroup(allGroupsRaw), [allGroupsRaw])

  const entries = useMemo(() => toFormEntries(groupMapping), [groupMapping])
  const hasEntries = entries.length > 0

  const navigateToEdit = (search?: string) => {
    const path = identityProviderGroupMappingEditPath(providerId)
    detachPromise(navigate({ to: search ? `${path}?${search}` : path }))
  }

  if (!hasEntries) {
    return (
      <EmptyMappingState
        onTestSignIn={readOnly ? undefined : () => navigateToEdit('discover=1')}
        onAddManually={readOnly ? undefined : () => navigateToEdit('new=1')}
      />
    )
  }

  return (
    <ReadOnlyView
      entries={entries}
      mappedGroups={mappedGroups}
      onEditMapping={readOnly ? undefined : () => navigateToEdit()}
    />
  )
}
