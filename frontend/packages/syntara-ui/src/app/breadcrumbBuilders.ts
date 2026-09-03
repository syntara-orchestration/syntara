import { AppRoute } from './AppRoute'
import type { AppBreadcrumbItem } from './breadcrumbs/appBreadcrumbItem'

const LABEL_ACCESS_MANAGEMENT = 'Access management'
const LABEL_IDENTITY_PROVIDERS = 'Identity providers'
const LABEL_CONFIGURATION = 'Configuration'
const LABEL_APPROVALS = 'Approvals'

function crumbAccessManagement(): AppBreadcrumbItem {
  return { label: LABEL_ACCESS_MANAGEMENT, href: AppRoute.AccessManagement.Root }
}

function crumbUsersList(): AppBreadcrumbItem {
  return { label: 'Users', href: AppRoute.AccessManagement.Users }
}

function crumbGroupsList(): AppBreadcrumbItem {
  return { label: 'Groups', href: AppRoute.AccessManagement.Groups }
}

function crumbProjectsList(): AppBreadcrumbItem {
  return { label: 'Projects', href: AppRoute.AccessManagement.Projects }
}

function crumbIdentityProvidersList(): AppBreadcrumbItem {
  return { label: LABEL_IDENTITY_PROVIDERS, href: AppRoute.SystemAdministration.Authentication.Root }
}

function crumbConfiguration(): AppBreadcrumbItem {
  return { label: LABEL_CONFIGURATION, href: AppRoute.Configuration.Overview }
}

function crumbIntegrations(): AppBreadcrumbItem {
  return { label: 'Integrations', href: AppRoute.Configuration.Integrations.Root }
}

function crumbCredentials(): AppBreadcrumbItem {
  return { label: 'Credentials', href: AppRoute.Configuration.Credentials.Root }
}

function crumbSettings(): AppBreadcrumbItem {
  return { label: 'Settings', href: AppRoute.SystemAdministration.Settings }
}

function crumbApprovals(): AppBreadcrumbItem {
  return { label: LABEL_APPROVALS, href: AppRoute.Approvals.Root }
}

export function breadcrumbsAccessManagementHub(): AppBreadcrumbItem[] {
  return [crumbAccessManagement()]
}

export function breadcrumbsIdentityProvidersPage(): AppBreadcrumbItem[] {
  return [{ label: LABEL_IDENTITY_PROVIDERS }]
}

export function breadcrumbsCreateUser(): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbUsersList(), { label: 'Create user' }]
}

export function breadcrumbsEditUser(displayName: string, userBasePath: string): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbUsersList(), { label: displayName, href: userBasePath }, { label: 'Edit user' }]
}

export function breadcrumbsUserDetail(displayName: string): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbUsersList(), { label: displayName }]
}

export function breadcrumbsGroupDetail(groupName: string): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbGroupsList(), { label: groupName }]
}

export function breadcrumbsProjectDetail(projectName: string): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbProjectsList(), { label: projectName }]
}

export function breadcrumbsIdentityProviderAdd(): AppBreadcrumbItem[] {
  return [crumbIdentityProvidersList(), { label: 'Add OIDC provider' }]
}

export function breadcrumbsIdentityProviderEdit(providerName: string, detailBasePath: string): AppBreadcrumbItem[] {
  return [crumbIdentityProvidersList(), { label: providerName, href: detailBasePath }, { label: 'Edit OIDC provider' }]
}

export function breadcrumbsIdentityProviderGroupMappingForm(
  providerName: string,
  detailBasePath: string,
  groupMappingTabPath: string,
  formTitle: string
): AppBreadcrumbItem[] {
  return [
    crumbIdentityProvidersList(),
    { label: providerName, href: detailBasePath },
    { label: 'Group mapping', href: groupMappingTabPath },
    { label: formTitle },
  ]
}

export function breadcrumbsIdentityProviderDetail(providerName: string): AppBreadcrumbItem[] {
  return [crumbIdentityProvidersList(), { label: providerName }]
}

/** Settings page before a category is selected or when only the page title applies. */
export function breadcrumbsSettingsPage(): AppBreadcrumbItem[] {
  return [crumbSettings()]
}

export function breadcrumbsIntegrationConfigure(): AppBreadcrumbItem[] {
  return [crumbConfiguration(), crumbIntegrations(), { label: 'Configure integration' }]
}

export function breadcrumbsIntegrationDetail(integrationName: string): AppBreadcrumbItem[] {
  return [crumbConfiguration(), crumbIntegrations(), { label: integrationName }]
}

export function breadcrumbsIntegrationDetailEarlyShell(): AppBreadcrumbItem[] {
  return [crumbConfiguration(), crumbIntegrations(), { label: 'Integration details' }]
}

export function breadcrumbsIntegrationEdit(integrationName: string, detailBasePath: string): AppBreadcrumbItem[] {
  return [
    crumbConfiguration(),
    crumbIntegrations(),
    { label: integrationName, href: detailBasePath },
    { label: 'Edit integration' },
  ]
}

export function breadcrumbsCredentialDetail(credentialName: string): AppBreadcrumbItem[] {
  return [crumbConfiguration(), crumbCredentials(), { label: credentialName }]
}

export function breadcrumbsCredentialEarlyShell(currentLabel: string): AppBreadcrumbItem[] {
  return [crumbConfiguration(), crumbCredentials(), { label: currentLabel }]
}

/** Generic two-item trail: parent link + current page label (e.g. loading / error titles). */
export function breadcrumbsApprovalsPage(currentLabel: string): AppBreadcrumbItem[] {
  return [crumbApprovals(), { label: currentLabel }]
}

export function breadcrumbsUserFormLoading(currentLabel: string): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbUsersList(), { label: currentLabel }]
}

export function breadcrumbsUserDetailEarlyShell(): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbUsersList(), { label: 'User details' }]
}

function crumbServiceAccountsList(): AppBreadcrumbItem {
  return { label: 'Service Accounts', href: AppRoute.AccessManagement.ServiceAccounts }
}

export function breadcrumbsServiceAccountDetail(name: string): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbServiceAccountsList(), { label: name }]
}

export function breadcrumbsServiceAccountDetailEarlyShell(): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbServiceAccountsList(), { label: 'Service account details' }]
}

export function breadcrumbsGroupDetailEarlyShell(): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbGroupsList(), { label: 'Group details' }]
}

export function breadcrumbsProjectDetailEarlyShell(): AppBreadcrumbItem[] {
  return [crumbAccessManagement(), crumbProjectsList(), { label: 'Project details' }]
}

export function breadcrumbsIdentityProviderFormLoading(currentLabel: string): AppBreadcrumbItem[] {
  return [crumbIdentityProvidersList(), { label: currentLabel }]
}

export function breadcrumbsIdentityProviderDetailEarlyShell(): AppBreadcrumbItem[] {
  return [crumbIdentityProvidersList(), { label: 'Identity provider details' }]
}
