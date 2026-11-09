import { Tab } from '@patternfly/react-core'
import { Outlet, useNavigate, useRouterState } from '@tanstack/react-router'
import { useCallback, useLayoutEffect, useMemo } from 'react'

import { breadcrumbsAccessManagementHub } from '../../app/breadcrumbBuilders'
import * as routeRefs from '../../app/routes/routeReferences'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynListPanel, SynListPanelTabs } from '../../components/panels/list/SynListPanel'
import { SynEmptyStateAccessDenied } from '../../components/states/SynEmptyStateAccessDenied'
import { SynPageTitle } from '../../components/SynPageTitle'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import { useAccessManagementPermissions } from './useAccessManagementPermissions'

type AccessTab =
  | 'users'
  | 'groups'
  | 'projects'
  | 'policies'
  | 'roles'
  | 'service-accounts'
  | 'assignments'
  | 'check-access'
  | 'token-revocation'

type TabDef = { key: AccessTab; label: string }

const allTabDefs: TabDef[] = [
  { key: 'users', label: 'Users' },
  { key: 'groups', label: 'Groups' },
  { key: 'projects', label: 'Projects' },
  { key: 'policies', label: 'Policies' },
  { key: 'roles', label: 'Roles' },
  { key: 'service-accounts', label: 'Service accounts' },
  { key: 'assignments', label: 'Assignments' },
  { key: 'check-access', label: 'Check access' },
  { key: 'token-revocation', label: 'Token revocation' },
]

const basePath = routeRefs.accessManagementRoute.fullPath

export function AccessManagement() {
  const accessDocLink = useDocLink('accessControl')
  const location = useRouterState({ select: (s) => s.location.pathname })
  const navigate = useNavigate()
  const {
    canReadUsers,
    canReadGroups,
    canReadProjects,
    canReadAssignments,
    canReadServiceAccounts,
    canReadRoles,
    canReadPolicies,
    canQueryAuthz,
    canReadTokenRevocation,
    canAccessPage,
    isLoading,
  } = useAccessManagementPermissions()

  const validTabDefs = useMemo<TabDef[]>(() => {
    if (isLoading) return allTabDefs
    const hiddenKeys = new Set<AccessTab>()
    if (!canReadUsers) hiddenKeys.add('users')
    if (!canReadGroups) hiddenKeys.add('groups')
    if (!canReadProjects) hiddenKeys.add('projects')
    if (!canReadServiceAccounts) hiddenKeys.add('service-accounts')
    if (!canReadAssignments) hiddenKeys.add('assignments')
    if (!canReadPolicies) hiddenKeys.add('policies')
    if (!canReadRoles) hiddenKeys.add('roles')
    if (!canQueryAuthz) hiddenKeys.add('check-access')
    if (!canReadTokenRevocation) hiddenKeys.add('token-revocation')
    if (hiddenKeys.size === 0) return allTabDefs
    return allTabDefs.filter((tab) => !hiddenKeys.has(tab.key))
  }, [
    canReadUsers,
    canReadGroups,
    canReadProjects,
    canReadServiceAccounts,
    canReadAssignments,
    canReadPolicies,
    canReadRoles,
    canQueryAuthz,
    canReadTokenRevocation,
    isLoading,
  ])

  const validTabKeys = useMemo(() => validTabDefs.map((t) => t.key), [validTabDefs])
  const defaultTab = validTabDefs[0]?.key ?? 'users'

  const onTabChange = useCallback(
    (tab: AccessTab, options?: { replace?: boolean }) => {
      switch (tab) {
        case 'users':
          detachPromise(navigate({ to: routeRefs.accessManagementUsersRoute.fullPath, ...options }))
          break
        case 'groups':
          detachPromise(navigate({ to: routeRefs.accessManagementGroupsRoute.fullPath, ...options }))
          break
        case 'projects':
          detachPromise(navigate({ to: routeRefs.accessManagementProjectsRoute.fullPath, ...options }))
          break
        case 'policies':
          detachPromise(navigate({ to: routeRefs.accessManagementPoliciesRoute.fullPath, ...options }))
          break
        case 'roles':
          detachPromise(navigate({ to: routeRefs.accessManagementRolesRoute.fullPath, ...options }))
          break
        case 'service-accounts':
          detachPromise(navigate({ to: routeRefs.accessManagementServiceAccountsRoute.fullPath, ...options }))
          break
        case 'assignments':
          detachPromise(navigate({ to: routeRefs.accessManagementAssignmentsRoute.fullPath, ...options }))
          break
        case 'check-access':
          detachPromise(navigate({ to: routeRefs.accessManagementCheckAccessRoute.fullPath, ...options }))
          break
        case 'token-revocation':
          detachPromise(navigate({ to: routeRefs.accessManagementTokenRevocationRoute.fullPath, ...options }))
          break
      }
    },
    [navigate]
  )

  // Redirect from the bare base path to the first allowed tab so the URL always has a tab segment.
  // SynUrlTabs handles restricted-path redirects via its own useEffect.
  useLayoutEffect(() => {
    if (isLoading || !canAccessPage) return
    if (location === basePath) {
      onTabChange(defaultTab, { replace: true })
    }
  }, [location, canAccessPage, isLoading, defaultTab, onTabChange])

  if (!isLoading && !canAccessPage) {
    return (
      <SynPage>
        <SynPageTitle segments={['Access Management']} />
        <SynPageHeader title="Access Management" breadcrumbs={[{ label: 'Access Management' }]} />
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynEmptyStateAccessDenied description="You don't have permission to view access management. Contact your administrator to request access." />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  const hubBreadcrumbs = breadcrumbsAccessManagementHub()

  return (
    <SynPage>
      <SynPageTitle segments={['Access Management']} />
      <SynPageHeader title="Access Management" docLink={accessDocLink} breadcrumbs={hubBreadcrumbs} />
      <SynPageBody>
        <SynListPanel>
          <SynListPanelTabs
            basePath={basePath}
            defaultTab={defaultTab}
            validTabs={validTabKeys}
            onTabChange={onTabChange}
          >
            {validTabDefs.map((tab) => (
              <Tab key={tab.key} eventKey={tab.key} title={tab.label} />
            ))}
          </SynListPanelTabs>
          <Outlet />
        </SynListPanel>
      </SynPageBody>
    </SynPage>
  )
}
