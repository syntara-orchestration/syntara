import { breadcrumbsIdentityProvidersPage } from '../../../app/breadcrumbBuilders'
import { EmptyStateAccessDenied } from '../../../components/EmptyStateAccessDenied'
import { NxPage, NxPageBody } from '../../../components/layout/NxPage'
import { NxPageHeader } from '../../../components/layout/NxPageHeader'
import { NxPanel } from '../../../components/layout/NxPanel'
import { NxPageTitle } from '../../../components/NxPageTitle'
import { NxListPanel } from '../../../components/panels/list/NxListPanel'
import { useCanI } from '../../../hooks/useCanI'
import { useDocLink } from '../../../utils/docs/useDocLink'

import { IdentityProvidersTab } from './IdentityProvidersTab'

export default function Authentication() {
  const { allowed: canRead, isChecking } = useCanI('read', 'identity-provider')
  const identityProvidersDocLink = useDocLink('identityProviders')

  if (isChecking) {
    return (
      <NxPage>
        <NxPageTitle segments={['Identity Providers']} />
        <NxPageHeader title="Identity Providers" breadcrumbs={breadcrumbsIdentityProvidersPage()} />
        <NxPageBody>
          <NxPanel isFullHeight />
        </NxPageBody>
      </NxPage>
    )
  }

  if (!canRead) {
    return (
      <NxPage>
        <NxPageTitle segments={['Identity Providers']} />
        <NxPageHeader title="Identity Providers" breadcrumbs={breadcrumbsIdentityProvidersPage()} />
        <NxPageBody>
          <NxPanel isFullHeight>
            <EmptyStateAccessDenied description="You don't have permission to view identity providers. Contact your administrator to request access." />
          </NxPanel>
        </NxPageBody>
      </NxPage>
    )
  }

  return (
    <NxPage>
      <NxPageTitle segments={['Identity Providers']} />
      <NxPageHeader
        title="Identity Providers"
        docLink={identityProvidersDocLink}
        breadcrumbs={breadcrumbsIdentityProvidersPage()}
      />
      <NxPageBody>
        <NxListPanel>
          <IdentityProvidersTab />
        </NxListPanel>
      </NxPageBody>
    </NxPage>
  )
}
