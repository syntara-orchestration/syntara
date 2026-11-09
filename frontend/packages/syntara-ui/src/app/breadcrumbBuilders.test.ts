import { describe, expect, it } from 'vitest'

import {
  breadcrumbsAccessManagementHub,
  breadcrumbsApprovalsPage,
  breadcrumbsCreateUser,
  breadcrumbsCredentialEarlyShell,
  breadcrumbsEditUser,
  breadcrumbsGroupDetailEarlyShell,
  breadcrumbsIdentityProviderAdd,
  breadcrumbsIdentityProviderDetailEarlyShell,
  breadcrumbsIdentityProviderEdit,
  breadcrumbsIdentityProviderFormLoading,
  breadcrumbsIdentityProvidersPage,
  breadcrumbsIntegrationConfigure,
  breadcrumbsIdentityProviderDetail,
  breadcrumbsProjectDetailEarlyShell,
  breadcrumbsCredentialDetail,
  breadcrumbsGroupDetail,
  breadcrumbsProjectDetail,
  breadcrumbsSettingsPage,
  breadcrumbsUserDetail,
  breadcrumbsUserDetailEarlyShell,
  breadcrumbsUserFormLoading,
  breadcrumbsIntegrationDetail,
  breadcrumbsServiceAccountDetail,
} from './breadcrumbBuilders'
import * as routeRefs from './routes/routeReferences'

describe('breadcrumbBuilders', () => {
  it('uses page hierarchy only for project detail on the default tab, without a tab segment', () => {
    const items = breadcrumbsProjectDetail('My project', 'uuid-1', 'details')
    expect(items).toEqual([
      { label: 'Access management', destination: { to: routeRefs.accessManagementRoute.fullPath } },
      { label: 'Projects', destination: { to: routeRefs.accessManagementProjectsRoute.fullPath } },
      { label: 'My project' },
    ])
  })

  it('includes a tab segment when not on the default details tab', () => {
    const items = breadcrumbsProjectDetail('My project', 'uuid-1', 'role-assignments')
    expect(items).toHaveLength(4)
    expect(items[2]).toEqual({
      label: 'My project',
      destination: { to: routeRefs.projectDetailRoute.fullPath, params: { projectId: 'uuid-1' } },
    })
    expect(items[3]).toEqual({ label: 'Assignments' })
  })

  it('labels the project workflows tab in breadcrumbs', () => {
    const items = breadcrumbsProjectDetail('My project', 'uuid-1', 'workflows')
    expect(items).toHaveLength(4)
    expect(items[2]).toEqual({
      label: 'My project',
      destination: { to: routeRefs.projectDetailRoute.fullPath, params: { projectId: 'uuid-1' } },
    })
    expect(items[3]).toEqual({ label: 'Workflows' })
  })

  it('uses page hierarchy only for user, group, and identity provider detail', () => {
    expect(breadcrumbsUserDetail('alice')).toEqual([
      { label: 'Access management', destination: { to: routeRefs.accessManagementRoute.fullPath } },
      { label: 'Users', destination: { to: routeRefs.accessManagementUsersRoute.fullPath } },
      { label: 'alice' },
    ])
    expect(breadcrumbsGroupDetail('g1')).toEqual([
      { label: 'Access management', destination: { to: routeRefs.accessManagementRoute.fullPath } },
      { label: 'Groups', destination: { to: routeRefs.accessManagementGroupsRoute.fullPath } },
      { label: 'g1' },
    ])
    expect(breadcrumbsIdentityProviderDetail('Okta')).toEqual([
      { label: 'Identity providers', destination: { to: routeRefs.authenticationRootRoute.fullPath } },
      { label: 'Okta' },
    ])
  })

  it('uses page hierarchy only for credential and integration detail', () => {
    expect(breadcrumbsCredentialDetail('Prod key')).toEqual([
      { label: 'Configuration', destination: { to: routeRefs.configurationOverviewRoute.fullPath } },
      { label: 'Credentials', destination: { to: routeRefs.credentialsRoute.fullPath } },
      { label: 'Prod key' },
    ])
    expect(breadcrumbsIntegrationDetail('GitHub')).toEqual([
      { label: 'Configuration', destination: { to: routeRefs.configurationOverviewRoute.fullPath } },
      { label: 'Integrations', destination: { to: routeRefs.integrationsRoute.fullPath } },
      { label: 'GitHub' },
    ])
  })

  it('uses page hierarchy only for service account detail', () => {
    expect(breadcrumbsServiceAccountDetail('ci-bot')).toEqual([
      { label: 'Access management', destination: { to: routeRefs.accessManagementRoute.fullPath } },
      { label: 'Service Accounts', destination: { to: routeRefs.accessManagementServiceAccountsRoute.fullPath } },
      { label: 'ci-bot' },
    ])
  })

  it('covers hub, forms, settings, integrations, approvals, and loading shells', () => {
    expect(breadcrumbsAccessManagementHub()).toEqual([
      { label: 'Access management', destination: { to: routeRefs.accessManagementRoute.fullPath } },
    ])
    expect(breadcrumbsIdentityProvidersPage()).toEqual([{ label: 'Identity providers' }])
    expect(breadcrumbsCreateUser()).toHaveLength(3)
    expect(breadcrumbsEditUser('Jane', 'u1')).toHaveLength(4)

    expect(breadcrumbsIdentityProviderAdd()).toHaveLength(2)
    expect(breadcrumbsIdentityProviderEdit('Auth0', 'provider-1')).toHaveLength(3)

    expect(breadcrumbsSettingsPage()).toEqual([
      { label: 'Settings', destination: { to: routeRefs.settingsRoute.fullPath } },
    ])

    expect(breadcrumbsApprovalsPage('Loading')).toHaveLength(2)

    expect(breadcrumbsIntegrationConfigure()).toHaveLength(3)

    expect(breadcrumbsCredentialEarlyShell('…')).toHaveLength(3)

    expect(breadcrumbsUserFormLoading('Saving')).toHaveLength(3)
    expect(breadcrumbsUserDetailEarlyShell()).toHaveLength(3)
    expect(breadcrumbsGroupDetailEarlyShell()).toHaveLength(3)
    expect(breadcrumbsProjectDetailEarlyShell()).toHaveLength(3)
    expect(breadcrumbsIdentityProviderFormLoading('…')).toHaveLength(2)
    expect(breadcrumbsIdentityProviderDetailEarlyShell()).toHaveLength(2)
  })
})
