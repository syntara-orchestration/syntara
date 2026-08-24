import { Button, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiArrowLeftIcon, RhUiSearchIcon } from '@patternfly/react-icons'
import { useNavigate, useParams, useRouterState } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { useEffect, useRef } from 'react'

import { AppRoute } from '../../../../app/AppRoute'
import { EmptyStateAccessDenied } from '../../../../components/EmptyStateAccessDenied'
import { SynPage, SynPageBody } from '../../../../components/layout/SynPage'
import { SynPageHeader } from '../../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../../components/layout/SynPanel'
import { SynPageTitle } from '../../../../components/SynPageTitle'
import { useCanI } from '../../../../hooks/useCanI'
import { detachPromise } from '../../../../utils/detachPromise'

import { GroupMappingFormEditor } from './GroupMappingFormEditor'
import { useGroupMappingFormMetadata } from './useGroupMappingForm'

function GroupMappingPageShell({
  title,
  breadcrumbs,
  children,
}: Readonly<{
  title: string
  breadcrumbs: ReturnType<typeof useGroupMappingFormMetadata>['breadcrumbs']
  children: ReactNode
}>) {
  return (
    <SynPage>
      <SynPageTitle segments={[title, 'Identity Providers']} />
      <SynPageHeader title={title} breadcrumbs={breadcrumbs} />
      <SynPageBody>
        <SynPanel isFullHeight>{children}</SynPanel>
      </SynPageBody>
    </SynPage>
  )
}

export function EditGroupMapping() {
  const navigate = useNavigate()
  const { providerId }: { providerId: string } = useParams({ strict: false })
  const search = useRouterState({ select: (s) => s.location.searchStr.replace(/^\?/, '') })
  const metadata = useGroupMappingFormMetadata(providerId, search)
  const { allowed: canUpdate, isChecking: isCheckingPermission } = useCanI('update', 'identity-provider', {
    enabled: metadata.isValidId,
  })

  const discoverStartedRef = useRef(false)
  const openTestSignInRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (
      !metadata.openDiscoverOnMount ||
      !metadata.isReady ||
      !canUpdate ||
      discoverStartedRef.current ||
      !openTestSignInRef.current
    ) {
      return
    }
    discoverStartedRef.current = true
    detachPromise(Promise.resolve(openTestSignInRef.current()))
  }, [metadata.openDiscoverOnMount, metadata.isReady, canUpdate])

  const navigateToAuthentication = () => {
    detachPromise(navigate({ to: AppRoute.SystemAdministration.Authentication.Root }))
  }

  if (!metadata.isValidId) {
    return (
      <GroupMappingPageShell title={metadata.pageTitle} breadcrumbs={metadata.breadcrumbs}>
        <EmptyState headingLevel="h2" titleText="Invalid identity provider" icon={RhUiSearchIcon} isFullHeight>
          <EmptyStateBody>The identity provider ID in the URL is not valid.</EmptyStateBody>
        </EmptyState>
      </GroupMappingPageShell>
    )
  }

  if (metadata.isNotFound) {
    return (
      <GroupMappingPageShell title={metadata.pageTitle} breadcrumbs={metadata.breadcrumbs}>
        <EmptyState headingLevel="h2" titleText="Identity provider not found" icon={RhUiSearchIcon} isFullHeight>
          <EmptyStateBody>
            The identity provider may have been deleted. Go back to Authentication to view configured providers.
          </EmptyStateBody>
          <EmptyStateFooter>
            <EmptyStateActions>
              <Button variant="primary" icon={<RhUiArrowLeftIcon />} onClick={navigateToAuthentication}>
                Back to identity providers
              </Button>
            </EmptyStateActions>
          </EmptyStateFooter>
        </EmptyState>
      </GroupMappingPageShell>
    )
  }

  if (metadata.queryState) {
    return (
      <GroupMappingPageShell title={metadata.pageTitle} breadcrumbs={metadata.breadcrumbs}>
        {metadata.queryState}
      </GroupMappingPageShell>
    )
  }

  if (isCheckingPermission) {
    return (
      <GroupMappingPageShell title={metadata.pageTitle} breadcrumbs={metadata.breadcrumbs}>
        {null}
      </GroupMappingPageShell>
    )
  }

  if (!metadata.isReady) return null

  if (!canUpdate) {
    return (
      <GroupMappingPageShell title={metadata.pageTitle} breadcrumbs={metadata.breadcrumbs}>
        <EmptyStateAccessDenied description="You don't have permission to edit group mapping. Contact your administrator to request access." />
      </GroupMappingPageShell>
    )
  }

  return <GroupMappingFormEditor metadata={metadata} openTestSignInRef={openTestSignInRef} />
}
