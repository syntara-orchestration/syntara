import type { ReactElement, ReactNode } from 'react'

import { breadcrumbsUserDetailEarlyShell } from '../../../app/breadcrumbBuilders'
import { SynLoadingState } from '../../../components/states/SynLoadingState'
import { detachPromise } from '../../../utils/detachPromise'
import { DetailPageShell } from '../DetailPageShell'

import { UserNotFoundState } from './UserNotFoundState'

export function renderUserDetailEarlyShell({
  isMyProfile,
  isMeQueryPending,
  hasUserQueryError,
  queryState,
  navigateBack,
  refetchUser,
}: Readonly<{
  isMyProfile: boolean
  isMeQueryPending: boolean
  hasUserQueryError: boolean
  queryState: ReactNode
  navigateBack: () => void
  refetchUser: () => Promise<unknown>
}>): ReactElement | null {
  if (isMyProfile && isMeQueryPending) {
    return (
      <DetailPageShell title="My Profile" breadcrumbs={[]}>
        <SynLoadingState />
      </DetailPageShell>
    )
  }

  const shellTitle = isMyProfile ? 'My Profile' : 'User'
  const shellBreadcrumbs = isMyProfile ? [] : breadcrumbsUserDetailEarlyShell()

  if (hasUserQueryError) {
    return (
      <DetailPageShell title={shellTitle} breadcrumbs={shellBreadcrumbs}>
        <UserNotFoundState
          onBack={navigateBack}
          backLabel={isMyProfile ? 'Back to workflows' : undefined}
          onRetry={() => {
            detachPromise(refetchUser())
          }}
        />
      </DetailPageShell>
    )
  }

  if (queryState) {
    return (
      <DetailPageShell title={shellTitle} breadcrumbs={shellBreadcrumbs}>
        {queryState}
      </DetailPageShell>
    )
  }

  return null
}
