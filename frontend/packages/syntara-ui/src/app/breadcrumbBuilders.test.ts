import { describe, expect, it } from 'vitest'

import { AppRoute } from './AppRoute'
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

describe('breadcrumbBuilders', () => {
  it('uses page hierarchy only for project detail on the default tab, without a tab segment', () => {
    const base = '/system-administration/access-management/projects/uuid-1'
    const items = breadcrumbsProjectDetail('My project', base, 'details')
    expect(items).toEqual([
      { label: 'Access management', href: AppRoute.AccessManagement.Root },
      { label: 'Projects', href: AppRoute.AccessManagement.Projects },
      { label: 'My project' },
    ])
  })

  it('includes a tab segment when not on the default details tab', () => {
    const base = '/system-administration/access-management/projects/uuid-1'
    const items = breadcrumbsProjectDetail('My project', base, 'role-assignments')
    expect(items).toHaveLength(4)
    expect(items[2]).toEqual({ label: 'My project', href: base })
    expect(items[3]).toEqual({ label: 'Assignments' })
  })

  it('labels the project workflows tab in breadcrumbs', () => {
    const base = '/system-administration/access-management/projects/uuid-1'
    const items = breadcrumbsProjectDetail('My project', base, 'workflows')
    expect(items).toHaveLength(4)
    expect(items[2]).toEqual({ label: 'My project', href: base })
    expect(items[3]).toEqual({ label: 'Workflows' })
  })

  it('uses page hierarchy only for user, group, and identity provider detail', () => {
    expect(breadcrumbsUserDetail('alice')).toEqual([
      { label: 'Access management', href: AppRoute.AccessManagement.Root },
      { label: 'Users', href: AppRoute.AccessManagement.Users },
      { label: 'alice' },
    ])
    expect(breadcrumbsGroupDetail('g1')).toEqual([
      { label: 'Access management', href: AppRoute.AccessManagement.Root },
      { label: 'Groups', href: AppRoute.AccessManagement.Groups },
      { label: 'g1' },
    ])
    expect(breadcrumbsIdentityProviderDetail('Okta')).toEqual([
      { label: 'Identity providers', href: AppRoute.SystemAdministration.Authentication.Root },
      { label: 'Okta' },
    ])
  })

  it('uses page hierarchy only for credential and integration detail', () => {
    expect(breadcrumbsCredentialDetail('Prod key')).toEqual([
      { label: 'Configuration', href: AppRoute.Configuration.Overview },
      { label: 'Credentials', href: AppRoute.Configuration.Credentials.Root },
      { label: 'Prod key' },
    ])
    expect(breadcrumbsIntegrationDetail('GitHub')).toEqual([
      { label: 'Configuration', href: AppRoute.Configuration.Overview },
      { label: 'Integrations', href: AppRoute.Configuration.Integrations.Root },
      { label: 'GitHub' },
    ])
  })

  it('uses page hierarchy only for service account detail', () => {
    expect(breadcrumbsServiceAccountDetail('ci-bot')).toEqual([
      { label: 'Access management', href: AppRoute.AccessManagement.Root },
      { label: 'Service Accounts', href: AppRoute.AccessManagement.ServiceAccounts },
      { label: 'ci-bot' },
    ])
  })

  it('covers hub, forms, settings, integrations, approvals, and loading shells', () => {
    expect(breadcrumbsAccessManagementHub()).toEqual([
      { label: 'Access management', href: AppRoute.AccessManagement.Root },
    ])
    expect(breadcrumbsIdentityProvidersPage()).toEqual([{ label: 'Identity providers' }])
    expect(breadcrumbsCreateUser()).toHaveLength(3)
    expect(breadcrumbsEditUser('Jane', '/system-administration/access-management/users/u1')).toHaveLength(4)

    expect(breadcrumbsIdentityProviderAdd()).toHaveLength(2)
    expect(breadcrumbsIdentityProviderEdit('Auth0', '/path')).toHaveLength(3)

    expect(breadcrumbsSettingsPage()).toEqual([{ label: 'Settings', href: AppRoute.SystemAdministration.Settings }])

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
