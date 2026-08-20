import { useCallback, useState } from 'react'

import { breadcrumbsIdentityProvidersPage } from '../../../app/breadcrumbBuilders'
import { EmptyStateAccessDenied } from '../../../components/EmptyStateAccessDenied'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { NxListPanel } from '../../../components/panels/list/NxListPanel'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { useCanI } from '../../../hooks/useCanI'
import { useDocLink } from '../../../utils/docs/useDocLink'

import { IdentityProvidersPageToolbar } from './IdentityProvidersPageToolbar'
import { IdentityProvidersTab, type IdentityProvidersHeaderToolbarState } from './IdentityProvidersTab'

export default function Authentication() {
  const { allowed: canRead, isChecking } = useCanI('read', 'identity-provider')
  const identityProvidersDocLink = useDocLink('identityProviders')
  const [headerToolbarState, setHeaderToolbarState] = useState<IdentityProvidersHeaderToolbarState | null>(null)

  const handleHeaderToolbarStateChange = useCallback((state: IdentityProvidersHeaderToolbarState | null) => {
    setHeaderToolbarState((prev) => {
      if (state === null) return null
      if (prev == null) return state
      if (
        prev.showToolbar === state.showToolbar &&
        prev.showAapButton === state.showAapButton &&
        prev.openAapSetup === state.openAapSetup &&
        prev.permissions.canCreate === state.permissions.canCreate &&
        prev.permissions.tooltips.create === state.permissions.tooltips.create
      ) {
        return prev
      }
      return state
    })
  }, [])

  if (isChecking) {
    return (
      <SynPage>
        <SynPageTitle segments={['Identity Providers']} />
        <SynPageHeader title="Identity Providers" breadcrumbs={breadcrumbsIdentityProvidersPage()} />
        <SynPageBody>
          <SynPanel isFullHeight />
        </SynPageBody>
      </SynPage>
    )
  }

  if (!canRead) {
    return (
      <SynPage>
        <SynPageTitle segments={['Identity Providers']} />
        <SynPageHeader title="Identity Providers" breadcrumbs={breadcrumbsIdentityProvidersPage()} />
        <SynPageBody>
          <SynPanel isFullHeight>
            <EmptyStateAccessDenied description="You don't have permission to view identity providers. Contact your administrator to request access." />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  return (
    <SynPage>
      <SynPageTitle segments={['Identity Providers']} />
      <SynPageHeader
        title="Identity Providers"
        docLink={identityProvidersDocLink}
        breadcrumbs={breadcrumbsIdentityProvidersPage()}
        toolbar={
          headerToolbarState?.showToolbar ? (
            <IdentityProvidersPageToolbar
              permissions={headerToolbarState.permissions}
              showAapButton={headerToolbarState.showAapButton}
              onAapSetup={headerToolbarState.openAapSetup}
            />
          ) : undefined
        }
      />
      <SynPageBody>
        <NxListPanel>
          <IdentityProvidersTab onHeaderToolbarStateChange={handleHeaderToolbarStateChange} />
        </NxListPanel>
      </SynPageBody>
    </SynPage>
  )
}
